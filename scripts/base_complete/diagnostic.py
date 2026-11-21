"""Montre la nature des écarts entre l'API et la base complète, champ par champ."""

import duckdb

con = duckdb.connect()
con.execute("CREATE VIEW api AS SELECT * FROM 'data/base_ademe/api.parquet'")
con.execute("CREATE VIEW base AS SELECT * FROM 'data/base_ademe/base.parquet'")

NUMERIQUES = [
    ("conso_5_usages_ep", "ep_conso_5_usages"),
    ("conso_5_usages_par_m2_ep", "ep_conso_5_usages_m2"),
    ("surface_habitable_logement", "surface_habitable_logement"),
    ("score_ban", "ban_score"),
]
for champ_api, champ_base in NUMERIQUES:
    print(f"\n=== {champ_api}")
    con.sql(f"""
        SELECT
            approx_quantile(abs(a.{champ_api} - b.{champ_base}), [0.5, 0.9, 0.99, 1.0])
                AS ecart_mediane_p90_p99_max,
            count_if(a.{champ_api} IS NULL) AS nuls_api,
            count_if(b.{champ_base} IS NULL) AS nuls_base
        FROM api AS a JOIN base AS b USING (numero_dpe)
    """).show()
    con.sql(f"""
        SELECT a.{champ_api} AS valeur_api, b.{champ_base} AS valeur_base, b.type_batiment
        FROM api AS a JOIN base AS b USING (numero_dpe)
        WHERE abs(a.{champ_api} - b.{champ_base}) > 0.01
        LIMIT 8
    """).show()

print("\n=== surface habitable, concordance par type de bâtiment")
con.sql("""
    SELECT
        b.type_batiment,
        count(*) AS nb_dpe,
        avg(CASE WHEN abs(a.surface_habitable_logement - b.surface_habitable_logement) <= 0.01
                 THEN 1.0 ELSE 0.0 END) AS avec_surface_logement,
        avg(CASE WHEN abs(a.surface_habitable_logement - b.surface_habitable_immeuble) <= 0.01
                 THEN 1.0 ELSE 0.0 END) AS avec_surface_immeuble
    FROM api AS a JOIN base AS b USING (numero_dpe)
    GROUP BY 1
""").show()

print("\n=== adresse brute : exemples d'écarts")
con.sql("""
    SELECT a.adresse_brut AS api, b.adresse_brut AS base, b.label_brut
    FROM api AS a JOIN base AS b USING (numero_dpe)
    WHERE a.adresse_brut IS DISTINCT FROM b.adresse_brut
    LIMIT 8
""").show(max_width=250)
