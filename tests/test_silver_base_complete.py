from datetime import date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from dpe_dvf.base_complete.silver import transformer_photographie
from dpe_dvf.transformation.silver import BilanValidation

JOUR = date(2026, 11, 23)

SCHEMA_PHOTOGRAPHIE = pa.schema(
    [
        ("numero_dpe", pa.string()),
        ("modele_dpe_id", pa.int32()),
        ("desactive", pa.bool_()),
        ("suppression_en_cours", pa.bool_()),
        ("statut", pa.string()),
        ("date_etablissement_dpe", pa.timestamp("us")),
        ("date_reception_dpe", pa.timestamp("us")),
        ("date_derniere_modification", pa.timestamp("us")),
        ("classe_bilan_dpe", pa.string()),
        ("classe_emission_ges", pa.string()),
        ("ep_conso_5_usages", pa.float64()),
        ("ep_conso_5_usages_m2", pa.float64()),
        ("type_batiment", pa.string()),
        ("periode_construction", pa.string()),
        ("annee_construction", pa.int32()),
        ("surface_habitable_logement", pa.float64()),
        ("numero_dpe_remplacant", pa.string()),
        ("adresse_brut", pa.string()),
        ("nom_commune_brut", pa.string()),
        ("code_postal_brut", pa.string()),
        ("ban_id", pa.string()),
        ("ban_score", pa.float64()),
        ("statut_geocodage", pa.string()),
        ("ban_postcode", pa.string()),
        ("ban_citycode", pa.string()),
        ("ban_departement", pa.string()),
        ("ban_region", pa.string()),
        ("ban_x", pa.float64()),
        ("ban_y", pa.float64()),
    ]
)


def dpe(numero: str, **valeurs: Any) -> dict[str, Any]:
    """Une ligne de photographie, avec des valeurs par défaut réalistes."""
    ligne: dict[str, Any] = {
        "numero_dpe": numero,
        "modele_dpe_id": 1,
        "desactive": False,
        "suppression_en_cours": False,
        "statut": None,
        "date_etablissement_dpe": datetime(2024, 3, 1, 10, 0),
        "date_reception_dpe": datetime(2024, 3, 1, 10, 0),
        "date_derniere_modification": datetime(2024, 3, 1, 10, 0),
        "classe_bilan_dpe": "D",
        "classe_emission_ges": "C",
        "ep_conso_5_usages": 20000.0,
        "ep_conso_5_usages_m2": 200.0,
        "type_batiment": "maison",
        "periode_construction": "1948-1974",
        "annee_construction": 1960,
        "surface_habitable_logement": 100.0,
        "numero_dpe_remplacant": None,
        "adresse_brut": "1 rue A",
        "nom_commune_brut": "Guéret",
        "code_postal_brut": "23000",
        "ban_id": "23096_a",
        "ban_score": 0.9,
        "statut_geocodage": "adresse géocodée ban à l'adresse",
        "ban_postcode": "23000",
        "ban_citycode": "23096",
        "ban_departement": "23",
        "ban_region": "75",
        "ban_x": 600000.0,
        "ban_y": 6560000.0,
    }
    return {**ligne, **valeurs}


def transformer(
    tmp_path: Path, lignes: list[dict[str, Any]]
) -> tuple[BilanValidation, dict[str, dict[str, Any]]]:
    photographie = tmp_path / "photographie.parquet"
    pq.write_table(pa.Table.from_pylist(lignes, schema=SCHEMA_PHOTOGRAPHIE), photographie)
    bilan = transformer_photographie(str(photographie), JOUR, tmp_path / "silver")
    cible = tmp_path / "silver" / "dpe_base_complete" / f"date_instantane={JOUR}" / "dpe.parquet"
    return bilan, {ligne["numero_dpe"]: ligne for ligne in pq.read_table(cible).to_pylist()}


def test_seuls_les_dpe_actifs_sont_retenus(tmp_path: Path) -> None:
    _, silver = transformer(
        tmp_path, [dpe("A"), dpe("D", desactive=True), dpe("S", suppression_en_cours=True)]
    )

    assert set(silver) == {"A"}


def test_jeu_de_donnees_et_date_d_ingestion(tmp_path: Path) -> None:
    _, silver = transformer(tmp_path, [dpe("A", modele_dpe_id=1), dpe("N", modele_dpe_id=3)])

    assert silver["A"]["dataset"] == "dpe03existant"
    assert silver["N"]["dataset"] == "dpe02neuf"
    assert silver["A"]["date_ingestion"] == JOUR


@pytest.mark.parametrize(
    ("reception_utc", "date_attendue"),
    [
        (datetime(2024, 3, 1, 23, 30), date(2024, 3, 2)),  # hiver : UTC + 1
        (datetime(2024, 7, 1, 21, 30), date(2024, 7, 1)),  # été : UTC + 2, 23 h 30
        (datetime(2024, 7, 1, 22, 30), date(2024, 7, 2)),  # été : 0 h 30 le lendemain
    ],
)
def test_dates_a_l_heure_de_paris(
    tmp_path: Path, reception_utc: datetime, date_attendue: date
) -> None:
    _, silver = transformer(tmp_path, [dpe("A", date_reception_dpe=reception_utc)])

    assert silver["A"]["date_reception_dpe"] == date_attendue


@pytest.mark.parametrize(
    ("colonne_photographie", "colonne_silver", "brute", "attendue"),
    [
        ("surface_habitable_logement", "surface_habitable_logement", 35.65, 35.7),
        ("ep_conso_5_usages", "conso_5_usages_ep", 8354.877639, 8354.9),
        ("ep_conso_5_usages_m2", "conso_5_usages_par_m2_ep", 148.496941, 148.4),
        ("ep_conso_5_usages_m2", "conso_5_usages_par_m2_ep", 256.665517, 256.6),
        ("ban_score", "score_ban", 0.976977, 0.98),
    ],
)
def test_arrondis_de_l_api(
    tmp_path: Path, colonne_photographie: str, colonne_silver: str, brute: float, attendue: float
) -> None:
    _, silver = transformer(tmp_path, [dpe("A", **{colonne_photographie: brute})])

    assert silver["A"][colonne_silver] == attendue


def test_espaces_de_debut_et_de_fin_supprimes(tmp_path: Path) -> None:
    _, silver = transformer(
        tmp_path, [dpe("A", adresse_brut=" 1 rue A ", nom_commune_brut=" Guéret ")]
    )

    assert silver["A"]["adresse_brut"] == "1 rue A"
    assert silver["A"]["nom_commune_brut"] == "Guéret"


def test_le_modele_dpe_s_applique_comme_pour_l_api(tmp_path: Path) -> None:
    bilan, silver = transformer(
        tmp_path,
        [dpe("A", annee_construction=2028, code_postal_brut="1000", ban_departement=None)],
    )

    assert silver["A"]["annee_construction"] is None
    assert silver["A"]["code_postal_brut"] == "01000"
    assert silver["A"]["code_departement"] == "01"
    assert silver["A"]["source_departement"] == "code_postal"
    assert bilan.valeurs_ecartees == {"annee_construction": 1}


def test_un_dpe_invalide_va_en_quarantaine(tmp_path: Path) -> None:
    bilan, silver = transformer(tmp_path, [dpe("A"), dpe("Z", surface_habitable_logement=0.0)])

    assert (bilan.nb_valides, bilan.nb_rejets) == (1, 1)
    assert set(silver) == {"A"}
    rejets = tmp_path / "silver" / "rejets_dpe_base_complete" / f"date_instantane={JOUR}"
    assert "Z" in (rejets / "rejets.jsonl").read_text(encoding="utf-8")


@pytest.mark.parametrize("valeur", [float("nan"), float("inf")])
def test_une_valeur_non_finie_devient_vide(tmp_path: Path, valeur: float) -> None:
    _, silver = transformer(
        tmp_path, [dpe("A", ep_conso_5_usages=valeur, ep_conso_5_usages_m2=valeur, ban_x=valeur)]
    )

    assert silver["A"]["conso_5_usages_ep"] is None
    assert silver["A"]["conso_5_usages_par_m2_ep"] is None
    assert silver["A"]["coordonnee_cartographique_x_ban"] is None
