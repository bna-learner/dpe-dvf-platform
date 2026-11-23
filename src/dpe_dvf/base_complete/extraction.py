"""Extraction d'une photographie de la base complète des DPE (ADR-0005).

Une ligne par DPE de logement (modèles 1, 2 et 3), désactivés compris, avec des valeurs
brutes. Les tables rattachées au DPE sont co-partitionnées en fichiers part-0 à part-f
selon le premier caractère de l'identifiant du DPE ; les adresses le sont selon leur propre
identifiant. L'extraction se fait donc en deux étapes, pour tenir en mémoire :

- étape A : jointure fichier par fichier des tables rattachées au DPE ;
- étape B : redistribution par identifiant d'adresse, puis jointure avec les adresses.
"""

import logging
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

PREFIXES = "0123456789abcdef"
TABLES_PARTITIONNEES = (
    "dpe",
    "dpe_administratif",
    "dpe_caracteristique_generale",
    "dpe_ep_conso",
    "dpe_emission_ges",
    "dpe_geolocalisation",
    "dpe_t_adresse",
)
MODELES_LOGEMENT = "1, 2, 3"


class ExtractionError(Exception):
    """Extraction impossible, ou photographie incohérente."""


@dataclass(frozen=True)
class BilanExtraction:
    """Contenu de la photographie extraite."""

    nb_dpe: int
    nb_actifs: int
    nb_remplaces: int
    taille_octets: int
    duree_secondes: float


def _litteral(texte: str) -> str:
    """Chaîne SQL entre apostrophes, avec les apostrophes internes doublées."""
    return "'" + texte.replace("'", "''") + "'"


def lister_fichiers(definition: str, prefixes: str = PREFIXES) -> dict[str, str]:
    """Associe chaque préfixe au fichier part-X d'une vue, d'après sa définition SQL.

    Lève ExtractionError si les fichiers ne correspondent pas exactement aux préfixes
    attendus : un changement de découpage de la source rendrait les jointures fausses.
    """
    trouves = re.findall(r"'([^']*part-([0-9a-f])\.parquet)'", definition)
    fichiers = {prefixe: chemin for chemin, prefixe in trouves}
    if len(trouves) != len(prefixes) or sorted(fichiers) != sorted(prefixes):
        attendus = ", ".join(prefixes)
        obtenus = ", ".join(prefixe for _, prefixe in trouves) or "aucun"
        raise ExtractionError(f"Fichiers part-X attendus : {attendus} ; trouvés : {obtenus}")
    return fichiers


def _definition(con: duckdb.DuckDBPyConnection, table: str) -> str:
    lignes = con.execute(
        "SELECT sql FROM duckdb_views() WHERE database_name = 'ademe' AND view_name = ?",
        [table],
    ).fetchall()
    if not lignes:
        raise ExtractionError(f"Vue {table} absente de la base")
    return str(lignes[0][0])


def _etape_a(
    con: duckdb.DuckDBPyConnection,
    fichiers: dict[str, dict[str, str]],
    dossier: Path,
    prefixes: str,
) -> None:
    """Jointure, fichier par fichier, des tables co-partitionnées par identifiant de DPE."""
    for p in prefixes:
        f = {table: _litteral(fichiers[table][p]) for table in TABLES_PARTITIONNEES}
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
                FROM read_parquet({f["dpe"]}) AS d
                JOIN read_parquet({f["dpe_administratif"]}) AS a ON a.dpe_id = d.id
                LEFT JOIN read_parquet({f["dpe_caracteristique_generale"]}) AS c
                    ON c.dpe_id = d.id
                LEFT JOIN read_parquet({f["dpe_ep_conso"]}) AS e ON e.dpe_id = d.id
                LEFT JOIN read_parquet({f["dpe_emission_ges"]}) AS g ON g.dpe_id = d.id
                LEFT JOIN read_parquet({f["dpe_geolocalisation"]}) AS l
                    ON l.administratif_id = d.id
                LEFT JOIN ademe.dpe_enum_methode_application_dpe_log AS methode
                    ON methode.id = c.enum_methode_application_dpe_log_id
                LEFT JOIN ademe.dpe_enum_periode_construction AS periode
                    ON periode.id = c.enum_periode_construction_id
                WHERE a.enum_modele_dpe_id IN ({MODELES_LOGEMENT})
            ) TO {_litteral(str(dossier / f"part-{p}.parquet"))} (FORMAT parquet)
        """)
        logger.info("Étape A : fichier part-%s joint", p)


def _remplacants(con: duckdb.DuckDBPyConnection, etape_a: Path, sortie: Path) -> None:
    """Correspondance entre identifiant interne et numéro des DPE remplaçants."""
    con.execute(f"""
        COPY (
            SELECT d.id, d.identifiant_dpe
            FROM ademe.dpe AS d
            WHERE d.id IN (
                SELECT DISTINCT dpe_remplacant_id
                FROM read_parquet({_litteral(str(etape_a / "*.parquet"))})
                WHERE dpe_remplacant_id IS NOT NULL
            )
        ) TO {_litteral(str(sortie))} (FORMAT parquet)
    """)


def _etape_b(
    con: duckdb.DuckDBPyConnection,
    adresses: dict[str, str],
    etape_a: Path,
    remplacants: Path,
    sortie: Path,
    prefixes: str,
) -> None:
    """Redistribution par identifiant d'adresse, puis jointure fichier par fichier."""
    for q in prefixes:
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
                FROM read_parquet({_litteral(str(etape_a / "*.parquet"))}) AS x
                LEFT JOIN read_parquet({_litteral(adresses[q])}) AS ad
                    ON ad.id = x.adresse_bien_id
                LEFT JOIN read_parquet({_litteral(str(remplacants))}) AS r
                    ON r.id = x.dpe_remplacant_id
                LEFT JOIN ademe.dpe_enum_statut_geocodage_ban AS statut
                    ON statut.id = ad.enum_statut_geocodage_ban_id
                WHERE coalesce(left(CAST(x.adresse_bien_id AS VARCHAR), 1), '{prefixes[0]}')
                    = '{q}'
            ) TO {_litteral(str(sortie / f"part-{q}.parquet"))} (FORMAT parquet, COMPRESSION zstd)
        """)
        logger.info("Étape B : fichier part-%s joint", q)


def _controler(con: duckdb.DuckDBPyConnection, dossier: Path) -> tuple[int, int, int]:
    """Vérifie la photographie ; renvoie le nombre de DPE, d'actifs et de remplacés."""
    nb_lignes, nb_dpe, nb_actifs, nb_incomplets, nb_remplaces = con.execute(f"""
        SELECT
            count(*),
            count(DISTINCT numero_dpe),
            count_if(NOT desactive AND NOT suppression_en_cours),
            count_if(NOT desactive AND NOT suppression_en_cours
                     AND (classe_bilan_dpe IS NULL OR classe_emission_ges IS NULL
                          OR type_batiment IS NULL OR statut_geocodage IS NULL)),
            count_if(numero_dpe_remplacant IS NOT NULL)
        FROM read_parquet({_litteral(str(dossier / "*.parquet"))}, hive_partitioning = false)
    """).fetchall()[0]
    if nb_lignes == 0:
        raise ExtractionError("Photographie vide")
    if nb_lignes != nb_dpe:
        raise ExtractionError(f"{nb_lignes - nb_dpe} lignes en double dans la photographie")
    if nb_incomplets:
        raise ExtractionError(f"{nb_incomplets} DPE actifs incomplets : jointure à vérifier")
    return int(nb_dpe), int(nb_actifs), int(nb_remplaces)


def extraire_instantane(
    base: str,
    sortie: Path,
    memoire_max: str = "8GB",
    prefixes: str = PREFIXES,
) -> BilanExtraction:
    """Extrait une photographie de la base complète dans le dossier `sortie`.

    `base` est le chemin ou l'URL d'une base DuckDB exposant les tables de l'ADEME sous
    forme de vues sur des fichiers part-X. La photographie est écrite dans un dossier
    temporaire, contrôlée, puis renommée : une extraction en échec ne laisse rien.
    """
    debut = time.perf_counter()
    sortie.parent.mkdir(parents=True, exist_ok=True)
    temporaire = sortie.with_name(sortie.name + ".tmp")
    shutil.rmtree(temporaire, ignore_errors=True)
    temporaire.mkdir()
    try:
        with tempfile.TemporaryDirectory(dir=sortie.parent) as travail:
            etape_a = Path(travail) / "etape_a"
            etape_a.mkdir()
            remplacants = Path(travail) / "remplacants.parquet"

            con = duckdb.connect()
            try:
                con.execute(f"SET memory_limit = {_litteral(memoire_max)}")
                con.execute(f"SET temp_directory = {_litteral(str(Path(travail) / 'duckdb'))}")
                con.execute("SET preserve_insertion_order = false")
                con.execute(f"ATTACH {_litteral(base)} AS ademe (READ_ONLY)")

                fichiers = {
                    table: lister_fichiers(_definition(con, table), prefixes)
                    for table in TABLES_PARTITIONNEES
                }
                _etape_a(con, fichiers, etape_a, prefixes)
                _remplacants(con, etape_a, remplacants)
                _etape_b(con, fichiers["dpe_t_adresse"], etape_a, remplacants, temporaire, prefixes)
                nb_dpe, nb_actifs, nb_remplaces = _controler(con, temporaire)
            finally:
                con.close()
    except BaseException:
        shutil.rmtree(temporaire, ignore_errors=True)
        raise

    shutil.rmtree(sortie, ignore_errors=True)
    temporaire.rename(sortie)

    bilan = BilanExtraction(
        nb_dpe=nb_dpe,
        nb_actifs=nb_actifs,
        nb_remplaces=nb_remplaces,
        taille_octets=sum(f.stat().st_size for f in sortie.glob("*.parquet")),
        duree_secondes=time.perf_counter() - debut,
    )
    logger.info(
        "Photographie extraite : %d DPE dont %d actifs, %.2f Go en %.0f s",
        bilan.nb_dpe,
        bilan.nb_actifs,
        bilan.taille_octets / 1e9,
        bilan.duree_secondes,
    )
    return bilan
