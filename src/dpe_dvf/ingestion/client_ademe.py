"""Client de lecture des jeux de données ADEME exposés par l'API Data Fair."""

import logging
import random
import time
from collections.abc import Callable, Iterator
from typing import Any, Self

import httpx

from dpe_dvf.config import Settings
from dpe_dvf.ingestion.exceptions import (
    AdemeApiError,
    RateLimitError,
    TransientAdemeError,
    UnexpectedResponseError,
)

logger = logging.getLogger(__name__)

Ligne = dict[str, Any]
Params = dict[str, str | int]

USER_AGENT = "dpe-dvf-platform (projet portfolio open source)"


class AdemeClient:
    """Lit les lignes d'un jeu de données Data Fair, page par page."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._http = http_client or httpx.Client(
            timeout=settings.timeout_seconds,
            headers={"User-Agent": USER_AGENT},
        )

    # --- Gestion du cycle de vie -------------------------------------------

    def close(self) -> None:
        """Ferme les connexions HTTP ouvertes."""
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # --- Appel d'une page --------------------------------------------------

    def fetch_page(self, url: str, params: Params | None = None) -> dict[str, Any]:
        """Récupère une page et la renvoie décodée.

        Traduit toute erreur HTTP ou réseau en exception du domaine.
        """
        try:
            response = self._http.get(url, params=params)
        except httpx.TimeoutException as e:
            raise TransientAdemeError(f"Délai dépassé pour {url}") from e
        except httpx.TransportError as e:
            raise TransientAdemeError(f"Erreur réseau pour {url} : {e}") from e

        status = response.status_code
        content_type = response.headers.get("content-type", "")

        if status == 429:
            raise RateLimitError(
                "Limite de débit de l'API atteinte",
                retry_after=_lire_retry_after(response),
            )
        if status >= 500:
            raise TransientAdemeError(f"Erreur serveur {status}", status_code=status)
        if status >= 400:
            raise AdemeApiError(
                f"Requête refusée ({status}, {content_type}) : {url}",
                status_code=status,
            )

        if "application/json" not in content_type:
            raise UnexpectedResponseError(
                f"Réponse non JSON reçue ({content_type})", status_code=status
            )
        try:
            payload = response.json()
        except ValueError as e:
            raise UnexpectedResponseError("JSON invalide", status_code=status) from e

        if not isinstance(payload, dict) or "results" not in payload:
            raise UnexpectedResponseError(
                "Structure inattendue : clé 'results' absente", status_code=status
            )
        return payload

    def _fetch_avec_reessais(self, url: str, params: Params | None) -> dict[str, Any]:
        """Appelle `fetch_page` en réessayant les erreurs transitoires."""
        nb_tentatives = self._settings.max_retries + 1
        for tentative in range(1, nb_tentatives + 1):
            try:
                return self.fetch_page(url, params)
            except TransientAdemeError as erreur:
                if tentative == nb_tentatives:
                    logger.error("Abandon après %d tentatives : %s", tentative, erreur)
                    raise
                delai = self._delai_avant_reessai(tentative, erreur)
                logger.warning(
                    "Tentative %d/%d échouée (%s) : nouvel essai dans %.1f s",
                    tentative,
                    nb_tentatives,
                    erreur,
                    delai,
                )
                self._sleep(delai)

    def _delai_avant_reessai(self, tentative: int, erreur: TransientAdemeError) -> float:
        """Calcule l'attente : Retry-After si fourni, sinon backoff exponentiel avec jitter."""
        if isinstance(erreur, RateLimitError) and erreur.retry_after is not None:
            return erreur.retry_after
        exponentiel = self._settings.backoff_base_seconds * 2.0 ** (tentative - 1)
        plafonne = min(exponentiel, self._settings.backoff_max_seconds)
        return plafonne * random.uniform(0.5, 1.0)

    # --- Parcours complet --------------------------------------------------

    def iter_pages(self, dataset_id: str, params: Params | None = None) -> Iterator[list[Ligne]]:
        """Parcourt toutes les pages d'un jeu de données en suivant le curseur `next`.

        Produit une page (liste de lignes) à la fois : la mémoire reste constante.
        """
        url: str | None = f"{self._settings.ademe_base_url}/{dataset_id}/lines"
        page_params: Params | None = {"size": self._settings.page_size, **(params or {})}
        numero_page = 0
        nb_lignes = 0
        total: int | None = None

        logger.info("Début de la lecture du jeu de données %s", dataset_id)

        while url is not None:
            payload = self._fetch_avec_reessais(url, page_params)
            if total is None:
                total = payload.get("total")  # seule la première page le fournit
            lignes: list[Ligne] = payload["results"]
            numero_page += 1
            nb_lignes += len(lignes)
            logger.debug(
                "Page %d : %d lignes (cumul %d sur %s)", numero_page, len(lignes), nb_lignes, total
            )
            if lignes:
                yield lignes

            url = payload.get("next")
            page_params = None  # `next` contient déjà tous les paramètres

        logger.info(
            "Fin de la lecture de %s : %d lignes en %d pages", dataset_id, nb_lignes, numero_page
        )
        if total is not None and nb_lignes != total:
            logger.warning(
                "Nombre de lignes lues (%d) différent du total annoncé (%d) pour %s",
                nb_lignes,
                total,
                dataset_id,
            )


def _lire_retry_after(response: httpx.Response) -> float | None:
    """Lit l'en-tête Retry-After, exprimé en secondes, s'il est présent."""
    valeur = response.headers.get("retry-after")
    if valeur is None:
        return None
    try:
        return float(valeur)
    except ValueError:
        return None
