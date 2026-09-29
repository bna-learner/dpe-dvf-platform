"""Point d'entrée en ligne de commande de l'ingestion des DPE vers la couche bronze."""

import argparse
import logging
import sys
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol

from dpe_dvf.config import Settings
from dpe_dvf.ingestion.bronze import ResultatLot, chemin_lot, ecrire_lot
from dpe_dvf.ingestion.client_ademe import AdemeClient, Ligne, Params
from dpe_dvf.ingestion.exceptions import AdemeApiError
from dpe_dvf.ingestion.fenetres import Fenetre, decouper_par_mois

logger = logging.getLogger(__name__)

CHAMP_DATE_PAR_DEFAUT = "date_reception_dpe"


class SourcePages(Protocol):
    """Tout objet capable de produire les pages d'un jeu de données."""

    def iter_pages(
        self, dataset_id: str, params: Params | None = None
    ) -> Iterator[list[Ligne]]: ...


def resoudre_datasets(choix: str, settings: Settings) -> list[str]:
    """Traduit le choix de l'utilisateur en identifiants de jeux de données."""
    correspondance = {
        "existant": [settings.dataset_logement_existant],
        "neuf": [settings.dataset_logement_neuf],
        "tous": [settings.dataset_logement_existant, settings.dataset_logement_neuf],
    }
    return correspondance[choix]


def ingerer(
    source: SourcePages,
    dataset_ids: Sequence[str],
    fenetre: Fenetre,
    racine: Path,
    date_ingestion: date,
    champ_date: str = CHAMP_DATE_PAR_DEFAUT,
) -> list[ResultatLot]:
    """Ingère chaque jeu de données, mois par mois, vers un lot bronze par mois."""
    resultats = []
    for dataset_id in dataset_ids:
        for mois in decouper_par_mois(fenetre):
            logger.info("Lot %s du %s au %s (exclu)", dataset_id, mois.debut, mois.fin)
            pages = source.iter_pages(dataset_id, params=mois.en_params(champ_date))
            metadonnees = {
                "source": "api_ademe",
                "dataset": dataset_id,
                "champ_date": champ_date,
                "fenetre_debut": mois.debut.isoformat(),
                "fenetre_fin": mois.fin.isoformat(),
                "date_ingestion": date_ingestion.isoformat(),
            }
            dossier = chemin_lot(racine, dataset_id, mois, date_ingestion)
            resultats.append(ecrire_lot(pages, dossier, metadonnees))
    return resultats


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingère les DPE de l'ADEME vers la couche bronze.")
    parser.add_argument(
        "--dataset",
        choices=["existant", "neuf", "tous"],
        default="tous",
        help="Jeu(x) de données à ingérer (défaut : tous).",
    )
    parser.add_argument(
        "--debut",
        type=date.fromisoformat,
        required=True,
        help="Premier jour inclus, au format AAAA-MM-JJ.",
    )
    parser.add_argument(
        "--fin",
        type=date.fromisoformat,
        default=None,
        help=(
            "Premier jour exclu, au format AAAA-MM-JJ (défaut : demain, pour inclure aujourd'hui)."
        ),
    )
    parser.add_argument(
        "--champ-date",
        default=CHAMP_DATE_PAR_DEFAUT,
        help="Champ de date sur lequel filtrer (défaut : date_reception_dpe).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Lance l'ingestion. Renvoie 0 en cas de succès, 1 en cas d'échec."""
    parser = _parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s : %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    aujourd_hui = datetime.now(UTC).date()
    fin = args.fin or aujourd_hui + timedelta(days=1)
    try:
        fenetre = Fenetre(args.debut, fin)
    except ValueError as e:
        parser.error(str(e))

    settings = Settings()
    dataset_ids = resoudre_datasets(args.dataset, settings)

    try:
        with AdemeClient(settings) as client:
            resultats = ingerer(
                client, dataset_ids, fenetre, settings.dossier_bronze, aujourd_hui, args.champ_date
            )
    except AdemeApiError:
        logger.exception("Ingestion interrompue")
        return 1

    total = sum(r.nb_lignes for r in resultats)
    logger.info("Ingestion terminée : %d lignes en %d lots", total, len(resultats))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
