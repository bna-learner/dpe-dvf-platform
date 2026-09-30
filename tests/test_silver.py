import json
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from dpe_dvf.ingestion.bronze import NOM_MANIFESTE, chemin_lot, ecrire_lot
from dpe_dvf.ingestion.fenetres import Fenetre
from dpe_dvf.ingestion.models import DPE
from dpe_dvf.transformation.silver import (
    COLONNES_PROVENANCE,
    SCHEMA_SILVER,
    lots_complets,
    transformer_lot,
)

FENETRE = Fenetre(date(2026, 8, 1), date(2026, 9, 1))

LIGNES_BRUTES: list[dict[str, Any]] = [
    {
        "numero_dpe": "A",
        "etiquette_dpe": "C",
        "date_reception_dpe": "2026-08-12",
        "surface_habitable_logement": 50.0,
        "champ_inconnu": "ignoré",
    },
    {"numero_dpe": "B", "surface_habitable_logement": -5},  # invalide
    {"numero_dpe": "C"},  # minimal mais valide
]


def creer_lot_bronze(racine: Path) -> Path:
    dossier = chemin_lot(racine, "dpe02neuf", FENETRE, date(2026, 9, 29))
    metadonnees = {
        "dataset": "dpe02neuf",
        "date_ingestion": "2026-09-29",
        "fenetre_debut": "2026-08-01",
        "fenetre_fin": "2026-09-01",
    }
    ecrire_lot([LIGNES_BRUTES], dossier, metadonnees)
    return dossier


def test_le_schema_suit_le_modele() -> None:
    attendues = list(DPE.model_fields) + COLONNES_PROVENANCE
    assert sorted(SCHEMA_SILVER.names) == sorted(attendues)


def test_seuls_les_lots_termines_sont_retenus(tmp_path: Path) -> None:
    termine = creer_lot_bronze(tmp_path)
    interrompu = tmp_path / "source=api_ademe/dataset=x/date_ingestion=2026-09-29/fenetre=y"
    interrompu.mkdir(parents=True)  # pas de manifeste

    assert lots_complets(tmp_path) == [termine]


def test_valides_et_rejets_sont_separes(tmp_path: Path) -> None:
    lot = creer_lot_bronze(tmp_path / "bronze")

    resultat = transformer_lot(lot, tmp_path / "silver")

    assert resultat.nb_valides == 2
    assert resultat.nb_rejets == 1


def test_le_parquet_respecte_le_schema(tmp_path: Path) -> None:
    lot = creer_lot_bronze(tmp_path / "bronze")

    resultat = transformer_lot(lot, tmp_path / "silver")
    table = pq.read_table(resultat.fichier)

    assert table.schema.equals(SCHEMA_SILVER)
    lignes = table.to_pylist()
    assert lignes[0]["numero_dpe"] == "A"
    assert lignes[0]["etiquette_dpe"] == "C"
    assert lignes[0]["date_reception_dpe"] == date(2026, 8, 12)
    assert lignes[0]["dataset"] == "dpe02neuf"
    assert lignes[1]["surface_habitable_logement"] is None  # clé absente → nulle


def test_les_rejets_indiquent_la_raison(tmp_path: Path) -> None:
    lot = creer_lot_bronze(tmp_path / "bronze")
    racine_silver = tmp_path / "silver"

    transformer_lot(lot, racine_silver)

    fichiers = list((racine_silver / "rejets_dpe").rglob("rejets.jsonl"))
    rejets = [json.loads(line) for line in fichiers[0].read_text(encoding="utf-8").splitlines()]
    assert rejets[0]["numero_dpe"] == "B"
    assert rejets[0]["erreurs"][0]["loc"] == ["surface_habitable_logement"]


def test_un_manifeste_silver_est_ecrit(tmp_path: Path) -> None:
    lot = creer_lot_bronze(tmp_path / "bronze")

    resultat = transformer_lot(lot, tmp_path / "silver")

    manifeste = json.loads((resultat.fichier.parent / NOM_MANIFESTE).read_text())
    assert manifeste["nb_valides"] == 2
    assert manifeste["nb_rejets"] == 1


def test_relancer_la_transformation_donne_le_meme_resultat(tmp_path: Path) -> None:
    lot = creer_lot_bronze(tmp_path / "bronze")

    premier = transformer_lot(lot, tmp_path / "silver")
    second = transformer_lot(lot, tmp_path / "silver")

    assert pq.read_table(premier.fichier).num_rows == 2
    assert pq.read_table(second.fichier).num_rows == 2
