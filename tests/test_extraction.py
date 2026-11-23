from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq
import pytest

from dpe_dvf.base_complete.extraction import (
    ExtractionError,
    extraire_instantane,
    lister_fichiers,
)

PREFIXES = "01"
CLES = {
    "dpe": "id",
    "dpe_administratif": "dpe_id",
    "dpe_caracteristique_generale": "dpe_id",
    "dpe_ep_conso": "dpe_id",
    "dpe_emission_ges": "dpe_id",
    "dpe_geolocalisation": "administratif_id",
    "dpe_t_adresse": "id",
}


def uuid(prefixe: str, numero: int) -> str:
    return f"{prefixe}{numero:07x}-0000-4000-8000-000000000000"


A, B, C, T = uuid("0", 1), uuid("1", 2), uuid("0", 3), uuid("1", 4)
ADR_A, ADR_B, ADR_C, ADR_T = uuid("1", 10), uuid("0", 11), uuid("1", 12), uuid("0", 13)


def fausse_base(dossier: Path, sans_ep_pour: str | None = None, geo_en_double: bool = False) -> str:
    """Base DuckDB imitant celle de l'ADEME : vues sur des fichiers part-0 et part-1."""
    con = duckdb.connect()
    con.execute(f"""
        CREATE TABLE dpe AS
        SELECT *, TIMESTAMP '2024-03-01 23:30:00' AS date_etablissement_dpe,
               TIMESTAMP '2024-03-01 23:30:00' AS date_reception_dpe,
               TIMESTAMP '2024-03-02 08:00:00' AS date_derniere_modification
        FROM (VALUES
            ('{A}'::UUID, 'DPE-A', false, false, NULL::VARCHAR, NULL::UUID),
            ('{B}'::UUID, 'DPE-B', false, false, NULL, NULL),
            ('{C}'::UUID, 'DPE-C', true, false, NULL, '{B}'::UUID),
            ('{T}'::UUID, 'DPE-T', false, false, NULL, NULL)
        ) AS t(id, identifiant_dpe, desactive, suppression_en_cours, statut, dpe_remplacant_id)
    """)
    con.execute(f"""
        CREATE TABLE dpe_administratif AS SELECT * FROM (VALUES
            ('{A}'::UUID, 1), ('{B}'::UUID, 2), ('{C}'::UUID, 1), ('{T}'::UUID, 4)
        ) AS t(dpe_id, enum_modele_dpe_id)
    """)
    con.execute(f"""
        CREATE TABLE dpe_caracteristique_generale AS SELECT * FROM (VALUES
            ('{A}'::UUID, 1950, 85.65::DOUBLE, 1, 2),
            ('{B}'::UUID, 2023, 60.0, 2, 10),
            ('{C}'::UUID, 1950, 85.65, 1, 2),
            ('{T}'::UUID, 1990, 500.0, 1, 10)
        ) AS t(dpe_id, annee_construction, surface_habitable_logement,
               enum_methode_application_dpe_log_id, enum_periode_construction_id)
    """)
    con.execute(f"""
        CREATE TABLE dpe_ep_conso AS SELECT * FROM (VALUES
            ('{A}'::UUID, 'F', 30000.878::DOUBLE, 350.27::DOUBLE),
            ('{B}'::UUID, 'A', 3000.0, 50.0),
            ('{C}'::UUID, 'G', 40000.0, 467.0),
            ('{T}'::UUID, 'D', 90000.0, 180.0)
        ) AS t(dpe_id, classe_bilan_dpe, ep_conso_5_usages, ep_conso_5_usages_m2)
    """)
    if sans_ep_pour is not None:
        con.execute(f"DELETE FROM dpe_ep_conso WHERE dpe_id = '{sans_ep_pour}'::UUID")
    con.execute(f"""
        CREATE TABLE dpe_emission_ges AS SELECT * FROM (VALUES
            ('{A}'::UUID, 'C'), ('{B}'::UUID, 'A'), ('{C}'::UUID, 'C'), ('{T}'::UUID, 'D')
        ) AS t(dpe_id, classe_emission_ges)
    """)
    con.execute(f"""
        CREATE TABLE dpe_geolocalisation AS SELECT * FROM (VALUES
            ('{A}'::UUID, '{ADR_A}'::UUID), ('{B}'::UUID, '{ADR_B}'::UUID),
            ('{C}'::UUID, '{ADR_C}'::UUID), ('{T}'::UUID, '{ADR_T}'::UUID)
        ) AS t(administratif_id, adresse_bien_id)
    """)
    if geo_en_double:
        con.execute(f"INSERT INTO dpe_geolocalisation VALUES ('{A}'::UUID, '{ADR_A}'::UUID)")
    con.execute(f"""
        CREATE TABLE dpe_t_adresse AS SELECT * FROM (VALUES
            ('{ADR_A}'::UUID, ' 1 rue A', 'Guéret', '23000', '23096_a', 0.976::DOUBLE, 1,
             '23000', '23096', '23', '75', 600000.0::DOUBLE, 6560000.0::DOUBLE),
            ('{ADR_B}'::UUID, ' 2 rue B', 'Lyon', '69001', '69381_b', 0.9, 1,
             '69001', '69381', '69', '84', 840000.0, 6520000.0),
            ('{ADR_C}'::UUID, ' 1 rue A', 'Guéret', '23000', '23096_a', 0.976, 1,
             '23000', '23096', '23', '75', 600000.0, 6560000.0),
            ('{ADR_T}'::UUID, ' 4 rue T', 'Paris', '75001', '75101_t', 0.95, 1,
             '75001', '75101', '75', '11', 650000.0, 6860000.0)
        ) AS t(id, adresse_brut, nom_commune_brut, code_postal_brut, ban_id, ban_score,
               enum_statut_geocodage_ban_id, ban_postcode, ban_citycode, ban_departement,
               ban_region, ban_x, ban_y)
    """)
    con.execute("""
        CREATE TABLE dpe_enum_methode_application_dpe_log AS
        SELECT * FROM (VALUES (1, 'maison'), (2, 'appartement')) AS t(id, type_batiment)
    """)
    con.execute("""
        CREATE TABLE dpe_enum_periode_construction AS
        SELECT * FROM (VALUES (2, '1948-1974'), (10, 'après 2021')) AS t(id, lib)
    """)
    con.execute("""
        CREATE TABLE dpe_enum_statut_geocodage_ban AS
        SELECT * FROM (VALUES (1, 'adresse géocodée ban à l''adresse')) AS t(id, lib)
    """)

    parts = dossier / "parts"
    base = dossier / "base.duckdb"
    con.execute(f"ATTACH '{base}' AS base")
    for table, cle in CLES.items():
        (parts / table).mkdir(parents=True)
        chemins = []
        for p in PREFIXES:
            chemin = parts / table / f"part-{p}.parquet"
            con.execute(f"""
                COPY (SELECT * FROM {table} WHERE left(CAST({cle} AS VARCHAR), 1) = '{p}')
                TO '{chemin}' (FORMAT parquet)
            """)
            chemins.append(f"'{chemin}'")
        con.execute(
            f"CREATE VIEW base.{table} AS SELECT * FROM read_parquet([{', '.join(chemins)}])"
        )
    for referentiel in (
        "dpe_enum_methode_application_dpe_log",
        "dpe_enum_periode_construction",
        "dpe_enum_statut_geocodage_ban",
    ):
        con.execute(f"CREATE TABLE base.{referentiel} AS SELECT * FROM {referentiel}")
    con.close()
    return str(base)


def lire(dossier: Path) -> dict[str, dict[str, Any]]:
    return {ligne["numero_dpe"]: ligne for ligne in pq.read_table(dossier).to_pylist()}


def test_une_ligne_par_dpe_de_logement(tmp_path: Path) -> None:
    sortie = tmp_path / "instantane"

    bilan = extraire_instantane(fausse_base(tmp_path), sortie, prefixes=PREFIXES)

    assert (bilan.nb_dpe, bilan.nb_actifs, bilan.nb_remplaces) == (3, 2, 1)
    assert set(lire(sortie)) == {"DPE-A", "DPE-B", "DPE-C"}


def test_valeurs_brutes_et_adresse_redistribuee(tmp_path: Path) -> None:
    sortie = tmp_path / "instantane"
    extraire_instantane(fausse_base(tmp_path), sortie, prefixes=PREFIXES)

    a = lire(sortie)["DPE-A"]
    assert a["type_batiment"] == "maison"
    assert a["periode_construction"] == "1948-1974"
    assert a["adresse_brut"] == " 1 rue A"
    assert a["ban_departement"] == "23"
    assert a["surface_habitable_logement"] == 85.65
    assert a["ep_conso_5_usages"] == 30000.878
    assert a["date_reception_dpe"] == datetime(2024, 3, 1, 23, 30)


def test_le_remplacant_est_traduit_en_numero(tmp_path: Path) -> None:
    sortie = tmp_path / "instantane"
    extraire_instantane(fausse_base(tmp_path), sortie, prefixes=PREFIXES)

    c = lire(sortie)["DPE-C"]
    assert c["desactive"] is True
    assert c["numero_dpe_remplacant"] == "DPE-B"


@pytest.mark.parametrize(
    ("options", "message"),
    [({"geo_en_double": True}, "double"), ({"sans_ep_pour": B}, "incomplets")],
)
def test_une_photographie_incoherente_n_est_jamais_ecrite(
    tmp_path: Path, options: dict[str, Any], message: str
) -> None:
    sortie = tmp_path / "instantane"

    with pytest.raises(ExtractionError, match=message):
        extraire_instantane(fausse_base(tmp_path, **options), sortie, prefixes=PREFIXES)

    assert not sortie.exists()
    assert not (tmp_path / "instantane.tmp").exists()


def test_une_vue_absente_arrete_l_extraction(tmp_path: Path) -> None:
    base = tmp_path / "vide.duckdb"
    duckdb.connect(str(base)).close()

    with pytest.raises(ExtractionError, match="absente"):
        extraire_instantane(str(base), tmp_path / "instantane", prefixes=PREFIXES)


def test_lister_fichiers_associe_chaque_prefixe() -> None:
    definition = (
        "SELECT * FROM read_parquet(['https://x/part-0.parquet', 'https://x/part-1.parquet'])"
    )

    assert lister_fichiers(definition, "01") == {
        "0": "https://x/part-0.parquet",
        "1": "https://x/part-1.parquet",
    }


@pytest.mark.parametrize(
    "definition",
    [
        "SELECT * FROM read_parquet(['https://x/part-0.parquet'])",
        "SELECT * FROM read_parquet(['https://x/part-0.parquet', 'https://y/part-0.parquet'])",
        "SELECT * FROM read_parquet('https://x/dpe.parquet')",
    ],
)
def test_lister_fichiers_refuse_un_decoupage_inattendu(definition: str) -> None:
    with pytest.raises(ExtractionError, match="attendus"):
        lister_fichiers(definition, "01")


def test_les_nombres_a_virgule_restent_des_double(tmp_path: Path) -> None:
    sortie = tmp_path / "instantane"
    extraire_instantane(fausse_base(tmp_path), sortie, prefixes=PREFIXES)

    schema = pq.read_schema(next(sortie.glob("*.parquet")))
    for colonne in ("surface_habitable_logement", "ep_conso_5_usages", "ban_score", "ban_x"):
        assert str(schema.field(colonne).type) == "double", colonne
