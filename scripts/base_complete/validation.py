"""Compare les DPE reconstruits depuis la base complète à ceux de l'API (silver)."""

import time

import duckdb

con = duckdb.connect("data/base_ademe/opendata.duckdb", read_only=True)
debut = time.perf_counter()

# Les DPE de l'API, dédoublonnés comme dans la vue silver_dpe_courant.
con.execute("""
    CREATE TEMP TABLE api AS
    SELECT * EXCLUDE (rang) FROM (
        SELECT *, row_number() OVER (
            PARTITION BY numero_dpe
            ORDER BY date_derniere_modification_dpe DESC NULLS LAST, date_ingestion DESC
        ) AS rang
        FROM read_parquet('data/silver_s3/dpe/**/dpe.parquet', hive_partitioning = false)
    )
    WHERE rang = 1
""")

# Les mêmes DPE, reconstruits depuis la base complète, avec tous les candidats.
con.execute("""
    CREATE TEMP TABLE base AS
    SELECT
        d.identifiant_dpe AS numero_dpe,
        CAST((d.date_etablissement_dpe AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Paris' AS DATE)
            AS date_etablissement_dpe,
        CAST((d.date_reception_dpe AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Paris' AS DATE)
            AS date_reception_dpe,
        CAST((d.date_derniere_modification AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Paris' AS DATE)
            AS modif_dpe,
        CAST(
            (adm.date_derniere_modification AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Paris' AS DATE
            ) AS modif_administratif,
        ep.classe_bilan_dpe,
        ep.nouvelle_classe_bilan_dpe_pef,
        ep.ancienne_classe_bilan_dpe,
        ep.nouvelle_classe_energie_dpe,
        ges.classe_emission_ges,
        ep.ep_conso_5_usages,
        ep.ep_conso_5_usages_m2,
        methode.type_batiment,
        periode.lib AS periode_construction,
        cg.annee_construction,
        cg.surface_habitable_logement,
        cg.surface_habitable_immeuble,
        ad.adresse_brut,
        ad.label_brut,
        ad.label_brut_avec_complement,
        ad.nom_commune_brut,
        ad.code_postal_brut,
        ad.ban_id,
        ad.ban_id_ban_adresse,
        ad.ban_score,
        statut.lib AS statut_geocodage,
        ad.ban_postcode,
        ad.ban_citycode,
        ad.ban_departement,
        ad.ban_region,
        ad.ban_x,
        ad.ban_y
    FROM dpe AS d
    JOIN dpe_administratif AS adm ON adm.dpe_id = d.id
    JOIN dpe_caracteristique_generale AS cg ON cg.dpe_id = d.id
    JOIN dpe_ep_conso AS ep ON ep.dpe_id = d.id
    JOIN dpe_emission_ges AS ges ON ges.dpe_id = d.id
    JOIN dpe_geolocalisation AS geo ON geo.administratif_id = d.id
    LEFT JOIN dpe_t_adresse AS ad ON ad.id = geo.adresse_bien_id
    LEFT JOIN dpe_enum_methode_application_dpe_log AS methode
        ON methode.id = cg.enum_methode_application_dpe_log_id
    LEFT JOIN dpe_enum_periode_construction AS periode
        ON periode.id = cg.enum_periode_construction_id
    LEFT JOIN dpe_enum_statut_geocodage_ban AS statut ON statut.id = ad.enum_statut_geocodage_ban_id
    WHERE adm.enum_modele_dpe_id IN (1, 2, 3)
      AND NOT d.desactive
      AND NOT d.suppression_en_cours
      AND d.identifiant_dpe IN (SELECT numero_dpe FROM api)
""")

print(
    con.sql("""
    SELECT
        (SELECT count(*) FROM api) AS dpe_api,
        (SELECT count(*) FROM base) AS dpe_reconstruits,
        (SELECT count(DISTINCT numero_dpe) FROM base) AS dpe_reconstruits_distincts
""")
)

# (champ de l'API, expression reconstruite, tolérance numérique ou None)
COMPARAISONS = [
    ("date_etablissement_dpe", "b.date_etablissement_dpe", None),
    ("date_reception_dpe", "b.date_reception_dpe", None),
    ("date_derniere_modification_dpe", "b.modif_dpe", None),
    ("date_derniere_modification_dpe", "b.modif_administratif", None),
    ("etiquette_dpe", "b.classe_bilan_dpe", None),
    ("etiquette_dpe", "b.nouvelle_classe_bilan_dpe_pef", None),
    ("etiquette_dpe", "b.ancienne_classe_bilan_dpe", None),
    ("etiquette_dpe", "b.nouvelle_classe_energie_dpe", None),
    ("etiquette_ges", "b.classe_emission_ges", None),
    ("conso_5_usages_ep", "b.ep_conso_5_usages", 0.01),
    ("conso_5_usages_par_m2_ep", "b.ep_conso_5_usages_m2", 0.01),
    ("type_batiment", "b.type_batiment", None),
    ("periode_construction", "b.periode_construction", None),
    ("annee_construction", "b.annee_construction", None),
    ("surface_habitable_logement", "b.surface_habitable_logement", 0.01),
    ("adresse_brut", "b.adresse_brut", None),
    ("nom_commune_brut", "b.nom_commune_brut", None),
    ("code_postal_brut", "lpad(b.code_postal_brut, 5, '0')", None),
    ("identifiant_ban", "b.ban_id", None),
    ("identifiant_ban", "b.ban_id_ban_adresse", None),
    ("score_ban", "b.ban_score", 0.0001),
    ("statut_geocodage", "b.statut_geocodage", None),
    ("code_postal_ban", "b.ban_postcode", None),
    ("code_insee_ban", "b.ban_citycode", None),
    ("code_departement_ban", "b.ban_departement", None),
    ("code_region_ban", "b.ban_region", None),
    ("coordonnee_cartographique_x_ban", "b.ban_x", 0.01),
    ("coordonnee_cartographique_y_ban", "b.ban_y", 0.01),
    ("surface_habitable_logement", "b.surface_habitable_immeuble", 0.01),
    ("adresse_brut", "b.label_brut", None),
    ("adresse_brut", "b.label_brut_avec_complement", None),
]

print(f"\n{'champ API':34} {'candidat':42} {'global':>9} {'non modifiés':>13}")
for champ, expression, tolerance in COMPARAISONS:
    if tolerance is None:
        egal = f"a.{champ} IS NOT DISTINCT FROM {expression}"
    else:
        egal = (
            f"(a.{champ} IS NULL AND {expression} IS NULL) "
            f"OR abs(a.{champ} - {expression}) <= {tolerance}"
        )
    taux, taux_non_modifies = con.execute(f"""
        SELECT
            avg(CASE WHEN {egal} THEN 1.0 ELSE 0.0 END),
            avg(CASE WHEN {egal} THEN 1.0 ELSE 0.0 END)
                FILTER (WHERE a.date_derniere_modification_dpe = b.modif_dpe)
        FROM api AS a JOIN base AS b USING (numero_dpe)
    """).fetchone()
    print(f"{champ:34} {expression:42} {taux:9.2%} {taux_non_modifies:13.2%}")

con.execute("COPY api TO 'data/base_ademe/api.parquet' (FORMAT parquet)")
con.execute("COPY base TO 'data/base_ademe/base.parquet' (FORMAT parquet)")
print(f"\nValidation en {time.perf_counter() - debut:.0f} s")
con.close()
