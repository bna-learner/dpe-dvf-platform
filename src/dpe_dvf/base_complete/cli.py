"""Chaîne hebdomadaire de la base complète : extraction, comparaison, silver (ADR-0005).

Travaille uniquement sur des dossiers locaux ; les échanges avec S3 sont faits par le
workflow GitHub Actions. Organisation sous la racine :

    bronze/instantanes/date_instantane=AAAA-MM-JJ/part-X.parquet
    bronze/changements/date_instantane=AAAA-MM-JJ/changements.parquet
    silver/dpe_base_complete/date_instantane=AAAA-MM-JJ/dpe.parquet
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from dpe_dvf.base_complete.comparaison import ComparaisonError, comparer_instantanes
from dpe_dvf.base_complete.extraction import ExtractionError, extraire_instantane
from dpe_dvf.base_complete.silver import transformer_photographie
from dpe_dvf.config import Settings

logger = logging.getLogger(__name__)

PARTITION = "date_instantane="


def instantane_precedent(dossier_instantanes: Path, jour: date) -> Path | None:
    """Photographie la plus récente antérieure à `jour`, ou None (chargement initial).

    Ignore les dossiers temporaires (suffixe .tmp), vides, ou mal nommés.
    """
    candidats: list[tuple[date, Path]] = []
    for dossier in dossier_instantanes.glob(f"{PARTITION}*"):
        try:
            date_dossier = date.fromisoformat(dossier.name.removeprefix(PARTITION))
        except ValueError:
            continue
        if date_dossier < jour and any(dossier.glob("*.parquet")):
            candidats.append((date_dossier, dossier))
    return max(candidats)[1] if candidats else None


def executer_chaine(jour: date, racine: Path, base: str, memoire_max: str = "8GB") -> None:
    """Extrait la photographie du jour, la compare à la précédente, puis produit silver."""
    instantanes = racine / "bronze" / "instantanes"
    precedent = instantane_precedent(instantanes, jour)
    nouveau = instantanes / f"{PARTITION}{jour.isoformat()}"
    logger.info(
        "Photographie du %s, comparée à %s",
        jour,
        precedent.name if precedent else "aucune (chargement initial)",
    )

    extraire_instantane(base=base, sortie=nouveau, memoire_max=memoire_max)
    comparer_instantanes(
        nouveau=str(nouveau / "*.parquet"),
        ancien=str(precedent / "*.parquet") if precedent else None,
        sortie=racine / "bronze" / "changements" / nouveau.name / "changements.parquet",
        date_instantane=jour,
    )
    transformer_photographie(
        photographie=str(nouveau / "*.parquet"),
        date_instantane=jour,
        racine_silver=racine / "silver",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée de la commande dpe-base-complete. Renvoie 0 en cas de succès."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s : %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Photographie hebdomadaire de la base complète des DPE."
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Date de la photographie (AAAA-MM-JJ). Par défaut : aujourd'hui, en UTC.",
    )
    args = parser.parse_args(argv)
    jour: date = args.date or datetime.now(UTC).date()

    settings = Settings()
    try:
        executer_chaine(
            jour=jour,
            racine=settings.dossier_base_complete,
            base=settings.base_complete_url,
            memoire_max=settings.duckdb_memoire_max,
        )
    except (ExtractionError, ComparaisonError):
        logger.exception("Chaîne de la base complète interrompue")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
