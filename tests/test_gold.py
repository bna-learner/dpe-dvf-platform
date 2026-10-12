from pathlib import Path
from typing import Any

import pytest

from dpe_dvf.transformation.gold import (
    GoldError,
    construire_requete_unload,
    executer_requete,
    materialiser_table,
    vider_prefixe,
)


class FauxAthena:
    """Renvoie une suite d'états prévue, et enregistre les requêtes reçues."""

    def __init__(self, etats: list[str], raison: str = "") -> None:
        self._etats = list(etats)
        self._raison = raison
        self.requetes: list[str] = []

    def start_query_execution(self, **kwargs: Any) -> dict[str, Any]:
        self.requetes.append(kwargs["QueryString"])
        return {"QueryExecutionId": "requete-1"}

    def get_query_execution(self, **kwargs: Any) -> dict[str, Any]:
        etat = self._etats.pop(0)
        return {
            "QueryExecution": {
                "Status": {"State": etat, "StateChangeReason": self._raison},
                "Statistics": {"DataScannedInBytes": 11_000_000, "TotalExecutionTimeInMillis": 900},
            }
        }


class FauxS3:
    """Simule un préfixe contenant des objets, répartis en pages."""

    def __init__(self, pages: list[list[str]]) -> None:
        self._pages = pages
        self.supprimes: list[str] = []

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        index = int(kwargs.get("ContinuationToken", 0))
        reponse: dict[str, Any] = {"Contents": [{"Key": cle} for cle in self._pages[index]]}
        if index + 1 < len(self._pages):
            reponse["IsTruncated"] = True
            reponse["NextContinuationToken"] = str(index + 1)
        return reponse

    def delete_objects(self, **kwargs: Any) -> dict[str, Any]:
        self.supprimes.extend(objet["Key"] for objet in kwargs["Delete"]["Objects"])
        return {}


def test_requete_unload_vers_le_dossier_de_la_table() -> None:
    requete = construire_requete_unload("SELECT 1 AS x;\n", "mon-bucket", "gold_test")
    assert "TO 's3://mon-bucket/gold_test/'" in requete
    assert "format = 'PARQUET'" in requete
    assert ";" not in requete


def test_attend_la_fin_de_la_requete() -> None:
    athena = FauxAthena(["QUEUED", "RUNNING", "SUCCEEDED"])
    attentes: list[float] = []

    executer_requete(athena, "SELECT 1", "groupe", attendre=attentes.append)

    assert len(attentes) == 2


def test_une_requete_en_echec_leve_une_erreur() -> None:
    athena = FauxAthena(["RUNNING", "FAILED"], raison="COLUMN_NOT_FOUND")

    with pytest.raises(GoldError, match="COLUMN_NOT_FOUND"):
        executer_requete(athena, "SELECT 1", "groupe", attendre=lambda _: None)


def test_vide_toutes_les_pages_du_prefixe() -> None:
    s3 = FauxS3([["t/a", "t/b"], ["t/c"]])

    nb = vider_prefixe(s3, "bucket", "t/")

    assert nb == 3
    assert s3.supprimes == ["t/a", "t/b", "t/c"]


def test_materialiser_une_table(tmp_path: Path) -> None:
    fichier = tmp_path / "gold_test.sql"
    fichier.write_text("-- commentaire\nSELECT 1 AS x\nORDER BY 1\n", encoding="utf-8")
    athena = FauxAthena(["SUCCEEDED"])
    s3 = FauxS3([["gold_test/ancien"]])

    resultat = materialiser_table(fichier, "bucket", "groupe", athena, s3, attendre=lambda _: None)

    assert resultat.table == "gold_test"
    assert resultat.octets_lus == 11_000_000
    assert s3.supprimes == ["gold_test/ancien"]
    assert "TO 's3://bucket/gold_test/'" in athena.requetes[0]
