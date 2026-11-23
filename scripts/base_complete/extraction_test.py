"""Prototype d'extraction : une ligne par DPE de logement, depuis la base complète.

Étape A : jointure des tables co-partitionnées par identifiant de DPE (part-0 à part-f).
Remplaçants : correspondance entre identifiant interne et numéro des DPE remplaçants.
Étape B : redistribution par identifiant d'adresse, puis jointure avec dpe_t_adresse.
"""

import re
import shutil
import time
from pathlib import Path

import duckdb

PREFIXES = "0123456789abcdef"
DOSSIER = Path("data/base_ademe/instantane_test")
ETAPE_A = DOSSIER / "etape_a"
REMPLACANTS = DOSSIER / "remplacants.parquet"
SORTIE = DOSSIER / "dpe"

shutil.rmtree(DOSSIER, ignore_errors=True)
ETAPE_A.mkdir(parents=True)
SORTIE.mkdir()
Path("data/base_ademe/tmp").mkdir(parents=True, exist_ok=True)

con = duckdb.connect()
con.execute("SET memory_limit = '8GB'")
con.execute("SET temp_directory = 'data/base_ademe/tmp'")
con.execute("SET preserve_insertion_order = false")
con.execute("ATTACH 'data/base_ademe/opendata.duckdb' AS ademe (READ_ONLY)")


def fichiers(table: str) -> dict[str, str]:
    """Associe chaque préfixe (0 à f) à l'URL du fichier part-X de la table."""
    (definition,) = con.execute(
        "SELECT sql FROM duckdb_views() WHERE database_name = 'ademe' AND view_name = ?",
        [table],
    ).fetchall()[0]
    urls = {
        prefixe: url
        for url, prefixe in re.findall(r"'(https://[^']+part-([0-9a-f])\.parquet)'", definition)
    }
    if sorted(urls) != list(PREFIXES):
        raise ValueError(f"{table} : fichiers part-0 à part-f attendus, trouvés {sorted(urls)}")
    return urls


dpe = fichiers("dpe")
adm = fichiers("dpe_administratif")
cg = fichiers("dpe_caracteristique_generale")
ep = fichiers("dpe_ep_conso")
ges = fichiers("dpe_emission_ges")
geo = fichiers("dpe_geolocalisation")
adresse = fichiers("dpe_t_adresse")

# --- Étape A : jointure co-partitionnée par identifiant de DPE ---------------
debut = time.perf_counter()
for p in PREFIXES:
    con.execute(f"""
        COPY (
            SELECT
                d.identifiant_dpe AS numero_dpe,
                a.enum_modele_dpe_id AS modele_dpe_id,
                d.desactive,
                d.suppression_en_cours,
                d.statut,
                d.dpe_remplacant_id,
                d.date_etablissement_dpe,
                d.date_reception_dpe,
                d.date_derniere_modification,
                e.classe_bilan_dpe,
                g.classe_emission_ges,
                e.ep_conso_5_usages,
                e.ep_conso_5_usages_m2,
                methode.type_batiment,
                periode.lib AS periode_construction,
                c.annee_construction,
                c.surface_habitable_logement,
                l.adresse_bien_id
            FROM read_parquet('{dpe[p]}') AS d
            JOIN read_parquet('{adm[p]}') AS a ON a.dpe_id = d.id
            LEFT JOIN read_parquet('{cg[p]}') AS c ON c.dpe_id = d.id
            LEFT JOIN read_parquet('{ep[p]}') AS e ON e.dpe_id = d.id
            LEFT JOIN read_parquet('{ges[p]}') AS g ON g.dpe_id = d.id
            LEFT JOIN read_parquet('{geo[p]}') AS l ON l.administratif_id = d.id
            LEFT JOIN ademe.dpe_enum_methode_application_dpe_log AS methode
                ON methode.id = c.enum_methode_application_dpe_log_id
            LEFT JOIN ademe.dpe_enum_periode_construction AS periode
                ON periode.id = c.enum_periode_construction_id
            WHERE a.enum_modele_dpe_id IN (1, 2, 3)
        ) TO '{ETAPE_A}/part-{p}.parquet' (FORMAT parquet)
    """)
    print(f"Étape A, part-{p} : {time.perf_counter() - debut:.0f} s")

# --- Remplaçants : numéro des DPE qui en remplacent un autre -----------------
debut = time.perf_counter()
con.execute(f"""
    COPY (
        SELECT d.id, d.identifiant_dpe
        FROM ademe.dpe AS d
        WHERE d.id IN (
            SELECT DISTINCT dpe_remplacant_id
            FROM '{ETAPE_A}/*.parquet'
            WHERE dpe_remplacant_id IS NOT NULL
        )
    ) TO '{REMPLACANTS}' (FORMAT parquet)
""")
print(f"Remplaçants : {time.perf_counter() - debut:.0f} s")

# --- Étape B : redistribution par identifiant d'adresse ----------------------
debut = time.perf_counter()
for q in PREFIXES:
    con.execute(f"""
        COPY (
            SELECT
                x.* EXCLUDE (dpe_remplacant_id, adresse_bien_id),
                r.identifiant_dpe AS numero_dpe_remplacant,
                ad.adresse_brut,
                ad.nom_commune_brut,
                ad.code_postal_brut,
                ad.ban_id,
                ad.ban_score,
                statut.lib AS statut_geocodage,
                ad.ban_postcode,
                ad.ban_citycode,
                ad.ban_departement,
                ad.ban_region,
                ad.ban_x,
                ad.ban_y
            FROM '{ETAPE_A}/*.parquet' AS x
            LEFT JOIN read_parquet('{adresse[q]}') AS ad ON ad.id = x.adresse_bien_id
            LEFT JOIN '{REMPLACANTS}' AS r ON r.id = x.dpe_remplacant_id
            LEFT JOIN ademe.dpe_enum_statut_geocodage_ban AS statut
                ON statut.id = ad.enum_statut_geocodage_ban_id
            WHERE coalesce(left(CAST(x.adresse_bien_id AS VARCHAR), 1), '0') = '{q}'
        ) TO '{SORTIE}/part-{q}.parquet' (FORMAT parquet, COMPRESSION zstd)
    """)
    print(f"Étape B, part-{q} : {time.perf_counter() - debut:.0f} s")

# --- Contrôles ---------------------------------------------------------------
con.sql(f"""
    SELECT
        count(*) AS nb_lignes,
        count(DISTINCT numero_dpe) AS nb_dpe,
        count_if(NOT desactive AND NOT suppression_en_cours) AS nb_actifs,
        count_if(NOT desactive AND NOT suppression_en_cours
                 AND (classe_bilan_dpe IS NULL OR classe_emission_ges IS NULL
                      OR type_batiment IS NULL OR statut_geocodage IS NULL))
            AS actifs_incomplets,
        count_if(numero_dpe_remplacant IS NOT NULL) AS nb_remplaces
    FROM '{SORTIE}/*.parquet'
""").show()
taille = sum(f.stat().st_size for f in SORTIE.glob("*.parquet"))
print(f"Taille de la photographie : {taille / 1e9:.2f} Go")
