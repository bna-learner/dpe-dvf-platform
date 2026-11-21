"""Vérifie les règles de format déduites du diagnostic."""

import duckdb

con = duckdb.connect()
con.execute("CREATE VIEW api AS SELECT * FROM 'data/base_ademe/api.parquet'")
con.execute("CREATE VIEW base AS SELECT * FROM 'data/base_ademe/base.parquet'")

REGLES = [
    ("conso_5_usages_ep", "round(CAST(b.ep_conso_5_usages AS DECIMAL(18, 6)), 1)"),
    (
        "surface_habitable_logement",
        "round(CAST(b.surface_habitable_logement AS DECIMAL(18, 6)), 1)",
    ),
    ("conso_5_usages_par_m2_ep", "trunc(b.ep_conso_5_usages_m2 * 10) / 10"),
    ("score_ban", "round(b.ban_score, 2)"),
    ("adresse_brut", "trim(b.adresse_brut)"),
    ("nom_commune_brut", "trim(b.nom_commune_brut)"),
]

print(f"{'champ':30} {'règle':45} {'concordance':>12} {'écart max':>10}")
for champ, regle in REGLES:
    numerique = not champ.endswith("_brut")
    ecart_max = f"max(abs(a.{champ} - {regle}))" if numerique else "NULL"
    egal = (
        f"(a.{champ} IS NULL AND {regle} IS NULL) OR abs(a.{champ} - {regle}) < 1e-9"
        if numerique
        else f"a.{champ} IS NOT DISTINCT FROM {regle}"
    )
    taux, maximum = con.execute(f"""
        SELECT avg(CASE WHEN {egal} THEN 1.0 ELSE 0.0 END), {ecart_max}
        FROM api AS a JOIN base AS b USING (numero_dpe)
    """).fetchall()[0]
    print(f"{champ:30} {regle:45} {taux:12.4%} {maximum if maximum is not None else '':>10}")

print("\nScore BAN : écarts au-delà de l'arrondi")
con.sql("""
    SELECT
        count_if(abs(a.score_ban - round(b.ban_score, 2)) > 0.005) AS nb_ecarts,
        max(abs(a.score_ban - round(b.ban_score, 2))) AS ecart_max
    FROM api AS a JOIN base AS b USING (numero_dpe)
""").show()
