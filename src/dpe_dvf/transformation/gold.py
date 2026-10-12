"""Matérialisation de gold : exécute les requêtes de sql/gold/ dans Athena
et écrit leurs résultats en Parquet dans le bucket gold."""

import logging
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import boto3

from dpe_dvf.config import Settings

logger = logging.getLogger(__name__)

ETATS_FINAUX = {"SUCCEEDED", "FAILED", "CANCELLED"}
NB_MAX_VERIFICATIONS = 300  # 300 × 2 s = 10 minutes maximum par requête


class GoldError(Exception):
    """Échec de la matérialisation d'une table gold."""


class ClientAthena(Protocol):
    def start_query_execution(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_query_execution(self, **kwargs: Any) -> dict[str, Any]: ...


class ClientS3(Protocol):
    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]: ...
    def delete_objects(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ResultatGold:
    """Bilan de la matérialisation d'une table."""

    table: str
    octets_lus: int
    duree_ms: int


def construire_requete_unload(requete: str, bucket: str, table: str) -> str:
    """Enveloppe une requête SELECT dans un UNLOAD vers le dossier de la table."""
    select = requete.strip().rstrip(";")
    return (
        f"UNLOAD (SELECT * FROM (\n{select}\n))\n"
        f"TO 's3://{bucket}/{table}/'\n"
        "WITH (format = 'PARQUET', compression = 'SNAPPY')"
    )


def vider_prefixe(s3: ClientS3, bucket: str, prefixe: str) -> int:
    """Supprime tous les objets sous un préfixe. Renvoie le nombre d'objets supprimés."""
    nb_supprimes = 0
    jeton: str | None = None
    while True:
        params: dict[str, Any] = {"Bucket": bucket, "Prefix": prefixe}
        if jeton is not None:
            params["ContinuationToken"] = jeton
        reponse = s3.list_objects_v2(**params)
        objets = [{"Key": objet["Key"]} for objet in reponse.get("Contents", [])]
        if objets:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": objets})
            nb_supprimes += len(objets)
        if not reponse.get("IsTruncated"):
            return nb_supprimes
        jeton = reponse["NextContinuationToken"]


def executer_requete(
    athena: ClientAthena,
    requete: str,
    groupe_de_travail: str,
    attendre: Callable[[float], None] = time.sleep,
    intervalle: float = 2.0,
) -> dict[str, Any]:
    """Lance une requête Athena et attend qu'elle se termine."""
    execution_id = athena.start_query_execution(QueryString=requete, WorkGroup=groupe_de_travail)[
        "QueryExecutionId"
    ]

    for _ in range(NB_MAX_VERIFICATIONS):
        execution: dict[str, Any] = athena.get_query_execution(QueryExecutionId=execution_id)[
            "QueryExecution"
        ]
        etat = execution["Status"]["State"]
        if etat in ETATS_FINAUX:
            break
        attendre(intervalle)
    else:
        raise GoldError(f"Requête {execution_id} toujours en cours après le délai maximal")

    if etat != "SUCCEEDED":
        raison = execution["Status"].get("StateChangeReason", "raison inconnue")
        raise GoldError(f"Requête {execution_id} en état {etat} : {raison}")
    return execution


def materialiser_table(
    fichier_sql: Path,
    bucket: str,
    groupe_de_travail: str,
    athena: ClientAthena,
    s3: ClientS3,
    attendre: Callable[[float], None] = time.sleep,
) -> ResultatGold:
    """Recalcule une table gold : vide son dossier, puis y écrit le résultat de sa requête."""
    table = fichier_sql.stem
    nb_supprimes = vider_prefixe(s3, bucket, f"{table}/")
    requete = construire_requete_unload(fichier_sql.read_text(encoding="utf-8"), bucket, table)
    execution = executer_requete(athena, requete, groupe_de_travail, attendre)

    statistiques = execution.get("Statistics", {})
    resultat = ResultatGold(
        table=table,
        octets_lus=statistiques.get("DataScannedInBytes", 0),
        duree_ms=statistiques.get("TotalExecutionTimeInMillis", 0),
    )
    logger.info(
        "Table %s matérialisée : %.1f Mo lus en %d ms (%d anciens fichiers supprimés)",
        table,
        resultat.octets_lus / 1e6,
        resultat.duree_ms,
        nb_supprimes,
    )
    return resultat


def main(argv: Sequence[str] | None = None) -> int:
    """Matérialise toutes les tables de sql/gold/. Renvoie 0 en cas de succès."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s : %(message)s",
    )
    settings = Settings()
    if not settings.bucket_gold:
        logger.error("La variable DPE_DVF_BUCKET_GOLD n'est pas définie")
        return 1

    fichiers = sorted(settings.dossier_sql_gold.glob("*.sql"))
    if not fichiers:
        logger.error("Aucune requête trouvée dans %s", settings.dossier_sql_gold)
        return 1

    athena = boto3.client("athena")
    s3 = boto3.client("s3")
    try:
        resultats = [
            materialiser_table(
                fichier, settings.bucket_gold, settings.athena_groupe_de_travail, athena, s3
            )
            for fichier in fichiers
        ]
    except GoldError:
        logger.exception("Échec de la matérialisation de gold")
        return 1

    total = sum(r.octets_lus for r in resultats)
    logger.info("Gold terminé : %d tables, %.1f Mo lus au total", len(resultats), total / 1e6)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
