"""Comparaison de deux photographies de la base complète des DPE.

Chaque DPE de la nouvelle photographie est comparé à sa version dans l'ancienne, grâce à
une empreinte de sa ligne entière. Seuls les DPE ajoutés, modifiés ou disparus sont écrits.
"""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


class ComparaisonError(Exception):
    """Comparaison impossible, ou résultat jugé incohérent."""


@dataclass(frozen=True)
class BilanComparaison:
    """Taille des deux photographies et nombre de changements de chaque type."""

    nb_dpe_ancien: int
    nb_dpe_nouveau: int
    nb_ajouts: int
    nb_modifications: int
    nb_disparitions: int

    @property
    def nb_changements(self) -> int:
        return self.nb_ajouts + self.nb_modifications + self.nb_disparitions

    @property
    def part_disparitions(self) -> float:
        """Part des DPE de l'ancienne photographie absents de la nouvelle."""
        return self.nb_disparitions / self.nb_dpe_ancien if self.nb_dpe_ancien else 0.0


def _litteral(texte: str) -> str:
    """Chaîne SQL entre apostrophes, avec les apostrophes internes doublées."""
    return "'" + texte.replace("'", "''") + "'"


def _schema(con: duckdb.DuckDBPyConnection, vue: str) -> list[tuple[str, str]]:
    return [(nom, type_) for nom, type_, *_ in con.execute(f"DESCRIBE {vue}").fetchall()]


def _nb_dpe_uniques(con: duckdb.DuckDBPyConnection, table: str, nom: str) -> int:
    """Nombre de DPE de la photographie ; erreur si un DPE y figure plusieurs fois."""
    nb_lignes, nb_dpe = con.execute(
        f"SELECT count(*), count(DISTINCT numero_dpe) FROM {table}"
    ).fetchall()[0]
    if nb_lignes != nb_dpe:
        raise ComparaisonError(f"Photographie {nom} : {nb_lignes - nb_dpe} lignes en double")
    return int(nb_dpe)


def comparer_instantanes(
    nouveau: str,
    ancien: str | None,
    sortie: Path,
    date_instantane: date,
    seuil_disparitions: float = 0.01,
) -> BilanComparaison:
    """Écrit dans `sortie` les DPE ajoutés, modifiés ou disparus entre deux photographies.

    `nouveau` et `ancien` sont des chemins ou des motifs de fichiers Parquet. Sans ancienne
    photographie (chargement initial), tous les DPE sont des ajouts.

    Lève ComparaisonError si une photographie contient un DPE en double, si les deux
    photographies n'ont pas le même schéma, ou si la part de DPE disparus dépasse
    `seuil_disparitions` : la nouvelle photographie est alors probablement incomplète.
    """
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order = false")
    con.execute(f"CREATE VIEW nouveau AS SELECT * FROM read_parquet({_litteral(nouveau)})")
    if ancien is None:
        con.execute("CREATE VIEW ancien AS SELECT * FROM nouveau WHERE false")
    else:
        con.execute(f"CREATE VIEW ancien AS SELECT * FROM read_parquet({_litteral(ancien)})")
        if _schema(con, "ancien") != _schema(con, "nouveau"):
            raise ComparaisonError("Les deux photographies n'ont pas le même schéma")

    for vue in ("nouveau", "ancien"):
        con.execute(f"""
            CREATE TEMP TABLE empreintes_{vue} AS
            SELECT numero_dpe, md5(CAST(ligne AS VARCHAR)) AS empreinte
            FROM {vue} AS ligne
        """)
    nb_dpe_nouveau = _nb_dpe_uniques(con, "empreintes_nouveau", "nouvelle")
    nb_dpe_ancien = _nb_dpe_uniques(con, "empreintes_ancien", "ancienne")

    con.execute("""
        CREATE TEMP TABLE changements AS
        SELECT
            coalesce(n.numero_dpe, a.numero_dpe) AS numero_dpe,
            CASE
                WHEN a.numero_dpe IS NULL THEN 'ajout'
                WHEN n.numero_dpe IS NULL THEN 'disparition'
                ELSE 'modification'
            END AS type_changement
        FROM empreintes_nouveau AS n
        FULL OUTER JOIN empreintes_ancien AS a ON a.numero_dpe = n.numero_dpe
        WHERE a.numero_dpe IS NULL
           OR n.numero_dpe IS NULL
           OR a.empreinte <> n.empreinte
    """)
    comptes = dict(
        con.execute("SELECT type_changement, count(*) FROM changements GROUP BY 1").fetchall()
    )
    bilan = BilanComparaison(
        nb_dpe_ancien=nb_dpe_ancien,
        nb_dpe_nouveau=nb_dpe_nouveau,
        nb_ajouts=comptes.get("ajout", 0),
        nb_modifications=comptes.get("modification", 0),
        nb_disparitions=comptes.get("disparition", 0),
    )
    if bilan.part_disparitions > seuil_disparitions:
        raise ComparaisonError(
            f"{bilan.nb_disparitions} DPE disparus ({bilan.part_disparitions:.2%}), au-delà "
            f"du seuil de {seuil_disparitions:.2%} : photographie probablement incomplète"
        )

    sortie.parent.mkdir(parents=True, exist_ok=True)
    temporaire = sortie.with_name(sortie.name + ".tmp")
    con.execute(f"""
        COPY (
            SELECT
                c.type_changement,
                DATE '{date_instantane.isoformat()}' AS date_instantane,
                c.numero_dpe,
                n.* EXCLUDE (numero_dpe)
            FROM changements AS c
            LEFT JOIN nouveau AS n ON n.numero_dpe = c.numero_dpe
        ) TO {_litteral(str(temporaire))} (FORMAT parquet, COMPRESSION zstd)
    """)
    con.close()
    temporaire.replace(sortie)

    logger.info(
        "Comparaison du %s : %d ajouts, %d modifications, %d disparitions (%d DPE)",
        date_instantane,
        bilan.nb_ajouts,
        bilan.nb_modifications,
        bilan.nb_disparitions,
        bilan.nb_dpe_nouveau,
    )
    return bilan
