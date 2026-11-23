"""Transformation d'une photographie de la base complète vers silver.

Applique les règles du dictionnaire de correspondance (docs/correspondance-base-complete.md)
pour que les DPE de la base complète aient exactement le format de ceux de l'API, puis les
valide avec le modèle DPE, comme les lots de l'API.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from dpe_dvf.transformation.silver import BilanValidation, valider_et_ecrire

TAILLE_PAQUET = 50_000


def _litteral(texte: str) -> str:
    """Chaîne SQL entre apostrophes, avec les apostrophes internes doublées."""
    return "'" + texte.replace("'", "''") + "'"


def _date_paris(colonne: str) -> str:
    """Horodatage UTC de la base complète → date à l'heure de Paris, comme l'API."""
    return f"CAST(({colonne} AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Paris' AS DATE)"


def _fini(colonne: str) -> str:
    """NaN et infinis deviennent vides, comme dans l'API : le JSON ne sait pas les représenter."""
    return f"CASE WHEN isfinite({colonne}) THEN {colonne} END"


def _arrondi(colonne: str, decimales: int) -> str:
    """Arrondi calculé en décimal exact : en DOUBLE, 35,65 s'arrondirait à 35,6."""
    return f"CAST(round(CAST({_fini(colonne)} AS DECIMAL(38, 6)), {decimales}) AS DOUBLE)"


def _requete(photographie: str) -> str:
    return f"""
        SELECT
            numero_dpe,
            CASE modele_dpe_id WHEN 1 THEN 'dpe03existant' ELSE 'dpe02neuf' END AS dataset,
            CAST(? AS DATE) AS date_ingestion,
            {_date_paris("date_etablissement_dpe")} AS date_etablissement_dpe,
            {_date_paris("date_reception_dpe")} AS date_reception_dpe,
            {_date_paris("date_derniere_modification")} AS date_derniere_modification_dpe,
            classe_bilan_dpe AS etiquette_dpe,
            classe_emission_ges AS etiquette_ges,
            {_arrondi("ep_conso_5_usages", 1)} AS conso_5_usages_ep,
            CAST(trunc(CAST({_fini("ep_conso_5_usages_m2")} AS DECIMAL(38, 6)) * 10) / 10
                AS DOUBLE) AS conso_5_usages_par_m2_ep,
            type_batiment,
            periode_construction,
            annee_construction,
            {_arrondi("surface_habitable_logement", 1)} AS surface_habitable_logement,
            trim(adresse_brut) AS adresse_brut,
            trim(nom_commune_brut) AS nom_commune_brut,
            code_postal_brut,
            ban_id AS identifiant_ban,
            {_arrondi("ban_score", 2)} AS score_ban,
            statut_geocodage,
            ban_postcode AS code_postal_ban,
            ban_citycode AS code_insee_ban,
            ban_departement AS code_departement_ban,
            ban_region AS code_region_ban,
            {_fini("ban_x")} AS coordonnee_cartographique_x_ban,
            {_fini("ban_y")} AS coordonnee_cartographique_y_ban
        FROM read_parquet({_litteral(photographie)}, hive_partitioning = false)
        WHERE NOT desactive AND NOT suppression_en_cours
    """


def lignes_au_format_api(
    photographie: str, date_instantane: date, taille_paquet: int = TAILLE_PAQUET
) -> Iterator[dict[str, Any]]:
    """Lit une photographie et renvoie, un par un, ses DPE actifs au format de l'API."""
    con = duckdb.connect()
    try:
        curseur = con.execute(_requete(photographie), [date_instantane])
        colonnes = [description[0] for description in curseur.description]
        while paquet := curseur.fetchmany(taille_paquet):
            for valeurs in paquet:
                yield dict(zip(colonnes, valeurs, strict=True))
    finally:
        con.close()


def transformer_photographie(
    photographie: str, date_instantane: date, racine_silver: Path
) -> BilanValidation:
    """Transforme une photographie de la base complète en silver."""
    partition = f"date_instantane={date_instantane.isoformat()}"
    return valider_et_ecrire(
        lignes_au_format_api(photographie, date_instantane),
        racine_silver / "dpe_base_complete" / partition / "dpe.parquet",
        racine_silver / "rejets_dpe_base_complete" / partition / "rejets.jsonl",
        photographie,
    )
