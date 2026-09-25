import logging

import httpx
import pytest

from dpe_dvf.config import Settings
from dpe_dvf.ingestion.client_ademe import AdemeClient
from dpe_dvf.ingestion.exceptions import (
    AdemeApiError,
    RateLimitError,
    TransientAdemeError,
    UnexpectedResponseError,
)

# --- Outillage de test ------------------------------------------------------


class FausseApi:
    """Simule l'API : renvoie les réponses prévues, dans l'ordre, et enregistre les requêtes."""

    def __init__(self, reponses: list[httpx.Response | Exception]) -> None:
        self._reponses = list(reponses)
        self.requetes: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requetes.append(request)
        reponse = self._reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse


def construire_client(api: FausseApi, settings: Settings, delais: list[float]) -> AdemeClient:
    """Crée un client branché sur la fausse API, qui note les attentes au lieu de dormir."""
    http = httpx.Client(transport=httpx.MockTransport(api))
    return AdemeClient(settings, http_client=http, sleep=delais.append)


def page(
    lignes: list[str], total: int | None = None, next_url: str | None = None
) -> httpx.Response:
    """Fabrique une réponse 200 au format Data Fair."""
    contenu: dict[str, object] = {"results": [{"numero_dpe": n} for n in lignes]}
    if total is not None:
        contenu["total"] = total
    if next_url is not None:
        contenu["next"] = next_url
    return httpx.Response(200, json=contenu)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        page_size=2,
        max_retries=2,
        backoff_base_seconds=1.0,
        backoff_max_seconds=10.0,
    )


# --- Pagination --------------------------------------------------------------


def test_suit_le_curseur_jusqu_a_la_fin(settings: Settings) -> None:
    api = FausseApi(
        [
            page(["A", "B"], total=3, next_url="https://api.test/page2"),
            page(["C"]),
        ]
    )
    client = construire_client(api, settings, [])

    pages = list(client.iter_pages("jeu-test"))

    assert [[ligne["numero_dpe"] for ligne in p] for p in pages] == [["A", "B"], ["C"]]
    assert len(api.requetes) == 2


def test_premiere_requete_porte_la_taille_de_page(settings: Settings) -> None:
    api = FausseApi([page(["A"], total=1)])
    client = construire_client(api, settings, [])

    list(client.iter_pages("jeu-test"))

    assert api.requetes[0].url.params["size"] == "2"
    assert api.requetes[0].url.path.endswith("/jeu-test/lines")


def test_alerte_si_lignes_manquantes(settings: Settings, caplog: pytest.LogCaptureFixture) -> None:
    api = FausseApi([page(["A", "B"], total=5)])
    client = construire_client(api, settings, [])

    with caplog.at_level(logging.WARNING):
        list(client.iter_pages("jeu-test"))

    assert "différent du total annoncé" in caplog.text


# --- Réessais ----------------------------------------------------------------


def test_reessaie_apres_503_puis_reussit(settings: Settings) -> None:
    delais: list[float] = []
    api = FausseApi([httpx.Response(503), page(["A"], total=1)])
    client = construire_client(api, settings, delais)

    pages = list(client.iter_pages("jeu-test"))

    assert len(pages) == 1
    assert len(api.requetes) == 2
    assert len(delais) == 1


def test_abandonne_apres_le_nombre_max_de_tentatives(settings: Settings) -> None:
    delais: list[float] = []
    api = FausseApi([httpx.Response(503)] * 3)
    client = construire_client(api, settings, delais)

    with pytest.raises(TransientAdemeError):
        list(client.iter_pages("jeu-test"))

    assert len(api.requetes) == 3  # max_retries=2 → 3 tentatives
    assert len(delais) == 2  # pas d'attente après la dernière


def test_backoff_exponentiel_avec_jitter(settings: Settings) -> None:
    delais: list[float] = []
    api = FausseApi([httpx.Response(503)] * 3)
    client = construire_client(api, settings, delais)

    with pytest.raises(TransientAdemeError):
        list(client.iter_pages("jeu-test"))

    # base 1 s : 1 s puis 2 s, chacun réduit aléatoirement entre 50 % et 100 %
    assert 0.5 <= delais[0] <= 1.0
    assert 1.0 <= delais[1] <= 2.0


def test_respecte_retry_after_sur_429(settings: Settings) -> None:
    delais: list[float] = []
    api = FausseApi(
        [
            httpx.Response(429, headers={"Retry-After": "7"}),
            page(["A"], total=1),
        ]
    )
    client = construire_client(api, settings, delais)

    list(client.iter_pages("jeu-test"))

    assert delais == [7.0]


def test_erreur_reseau_est_reessayee(settings: Settings) -> None:
    delais: list[float] = []
    api = FausseApi([httpx.ConnectError("connexion refusée"), page(["A"], total=1)])
    client = construire_client(api, settings, delais)

    pages = list(client.iter_pages("jeu-test"))

    assert len(pages) == 1
    assert len(delais) == 1


# --- Erreurs permanentes : aucun réessai ---------------------------------------


def test_404_leve_une_erreur_sans_reessai(settings: Settings) -> None:
    delais: list[float] = []
    api = FausseApi([httpx.Response(404)])
    client = construire_client(api, settings, delais)

    with pytest.raises(AdemeApiError) as info:
        list(client.iter_pages("jeu-inexistant"))

    assert not isinstance(info.value, TransientAdemeError)
    assert info.value.status_code == 404
    assert len(api.requetes) == 1
    assert delais == []


def test_reponse_html_leve_une_erreur_sans_reessai(settings: Settings) -> None:
    delais: list[float] = []
    html = httpx.Response(
        200, text="<html>Maintenance</html>", headers={"content-type": "text/html"}
    )
    api = FausseApi([html])
    client = construire_client(api, settings, delais)

    with pytest.raises(UnexpectedResponseError):
        list(client.iter_pages("jeu-test"))

    assert len(api.requetes) == 1
    assert delais == []


def test_json_sans_results_est_rejete(settings: Settings) -> None:
    api = FausseApi([httpx.Response(200, json={"message": "inattendu"})])
    client = construire_client(api, settings, [])

    with pytest.raises(UnexpectedResponseError, match="results"):
        list(client.iter_pages("jeu-test"))


def test_rate_limit_est_bien_une_erreur_429(settings: Settings) -> None:
    settings_sans_reessai = settings.model_copy(update={"max_retries": 0})
    api = FausseApi([httpx.Response(429)])
    client = construire_client(api, settings_sans_reessai, [])

    with pytest.raises(RateLimitError) as info:
        list(client.iter_pages("jeu-test"))

    assert info.value.status_code == 429


def test_timeout_est_reessaye(settings: Settings) -> None:
    delais: list[float] = []
    api = FausseApi([httpx.ReadTimeout("réponse trop lente"), page(["A"], total=1)])
    client = construire_client(api, settings, delais)

    pages = list(client.iter_pages("jeu-test"))

    assert len(pages) == 1
    assert len(delais) == 1


def test_json_invalide_est_rejete(settings: Settings) -> None:
    reponse = httpx.Response(
        200, content=b"{pas du json", headers={"content-type": "application/json"}
    )
    api = FausseApi([reponse])
    client = construire_client(api, settings, [])

    with pytest.raises(UnexpectedResponseError, match="JSON invalide"):
        list(client.iter_pages("jeu-test"))


def test_retry_after_non_numerique_utilise_le_backoff(settings: Settings) -> None:
    delais: list[float] = []
    api = FausseApi(
        [
            httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
            page(["A"], total=1),
        ]
    )
    client = construire_client(api, settings, delais)

    list(client.iter_pages("jeu-test"))

    assert 0.5 <= delais[0] <= 1.0  # premier délai du backoff, pas un plantage


def test_le_with_ferme_la_connexion(settings: Settings) -> None:
    http = httpx.Client(transport=httpx.MockTransport(FausseApi([])))

    with AdemeClient(settings, http_client=http):
        assert not http.is_closed

    assert http.is_closed
