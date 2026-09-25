from dpe_dvf.ingestion.exceptions import (
    AdemeApiError,
    RateLimitError,
    TransientAdemeError,
    UnexpectedResponseError,
)


def test_rate_limit_est_transitoire() -> None:
    assert issubclass(RateLimitError, TransientAdemeError)


def test_reponse_inattendue_n_est_pas_transitoire() -> None:
    assert not issubclass(UnexpectedResponseError, TransientAdemeError)


def test_toutes_les_erreurs_derivent_de_la_base() -> None:
    for classe in (TransientAdemeError, RateLimitError, UnexpectedResponseError):
        assert issubclass(classe, AdemeApiError)


def test_rate_limit_porte_code_et_delai() -> None:
    erreur = RateLimitError("Trop de requêtes", retry_after=12.0)
    assert erreur.status_code == 429
    assert erreur.retry_after == 12.0


def test_message_conserve() -> None:
    erreur = AdemeApiError("Jeu de données introuvable", status_code=404)
    assert str(erreur) == "Jeu de données introuvable"
    assert erreur.status_code == 404
