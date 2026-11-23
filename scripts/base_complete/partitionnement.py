"""Vérifie si les fichiers part-X des tables sont répartis par identifiant de DPE."""

import re

import duckdb

CLES = {
    "dpe": ["id"],
    "dpe_ep_conso": ["dpe_id"],
    "dpe_geolocalisation": ["administratif_id", "adresse_bien_id"],
    "dpe_t_adresse": ["id"],
}

con = duckdb.connect()
con.execute("SET memory_limit = '4GB'")
con.execute("ATTACH 'data/base_ademe/opendata.duckdb' AS ademe (READ_ONLY)")

for table, cles in CLES.items():
    (definition,) = con.execute(
        "SELECT sql FROM duckdb_views() WHERE database_name = 'ademe' AND view_name = ?", [table]
    ).fetchall()[0]
    urls = re.findall(r"'(https://[^']+\.parquet)'", definition)
    for numero in (0, 3):
        for cle in cles:
            prefixes = con.execute(f"""
                SELECT left(CAST({cle} AS VARCHAR), 1) AS prefixe, count(*) AS nb
                FROM read_parquet('{urls[numero]}')
                GROUP BY 1 ORDER BY 1
            """).fetchall()
            resume = ", ".join(f"{p}:{n}" for p, n in prefixes)
            print(f"{table:22} part-{numero:x} {cle:18} {resume}")
