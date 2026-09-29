"""Écriture de la couche bronze : copie fidèle des lignes renvoyées par l'API."""

import gzip
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from dpe_dvf.ingestion.fenetres import Fenetre

logger = logging.getLogger(__name__)

NOM_MANIFESTE = "_manifest.json"


@dataclass(frozen=True)
class ResultatLot:
    """Bilan de l'écriture d'un lot bronze."""

    dossier: Path
    nb_fichiers: int
    nb_lignes: int


def chemin_lot(racine: Path, dataset_id: str, fenetre: Fenetre, date_ingestion: date) -> Path:
    """Construit le dossier d'un lot, partitionné par source, jeu, date d'ingestion et fenêtre."""
    return (
        racine
        / "source=api_ademe"
        / f"dataset={dataset_id}"
        / f"date_ingestion={date_ingestion.isoformat()}"
        / f"fenetre={fenetre.debut.isoformat()}_{fenetre.fin.isoformat()}"
    )


def ecrire_lot(
    pages: Iterable[list[dict[str, Any]]],
    dossier: Path,
    metadonnees: dict[str, str],
) -> ResultatLot:
    """Écrit un lot bronze : un fichier JSON Lines gzip par page, puis le manifeste.

    Relancer l'écriture d'un même lot le remplace entièrement (idempotence).
    """
    if dossier.exists():
        for ancien in dossier.iterdir():
            ancien.unlink()
    dossier.mkdir(parents=True, exist_ok=True)

    nb_fichiers = 0
    nb_lignes = 0
    for numero, lignes in enumerate(pages, start=1):
        cible = dossier / f"part-{numero:05d}.jsonl.gz"
        temporaire = cible.with_name(cible.name + ".tmp")
        with gzip.open(temporaire, "wt", encoding="utf-8") as fichier:
            for ligne in lignes:
                fichier.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        temporaire.replace(cible)  # renommage atomique
        nb_fichiers += 1
        nb_lignes += len(lignes)
        logger.debug("Fichier %s écrit : %d lignes", cible.name, len(lignes))

    manifeste: dict[str, object] = {
        **metadonnees,
        "nb_fichiers": nb_fichiers,
        "nb_lignes": nb_lignes,
        "termine_le": datetime.now(UTC).isoformat(),
    }
    (dossier / NOM_MANIFESTE).write_text(
        json.dumps(manifeste, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Lot bronze terminé : %s (%d lignes, %d fichiers)", dossier, nb_lignes, nb_fichiers)
    return ResultatLot(dossier, nb_fichiers, nb_lignes)
