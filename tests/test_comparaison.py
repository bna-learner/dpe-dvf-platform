from datetime import date
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from dpe_dvf.base_complete.comparaison import ComparaisonError, comparer_instantanes

SCHEMA = pa.schema(
    [
        ("numero_dpe", pa.string()),
        ("etiquette_dpe", pa.string()),
        ("conso", pa.float64()),
        ("desactive", pa.bool_()),
    ]
)
JOUR = date(2026, 11, 23)


def dpe(
    numero: str, etiquette: str | None = "D", conso: float = 200.0, desactive: bool = False
) -> dict[str, Any]:
    return {
        "numero_dpe": numero,
        "etiquette_dpe": etiquette,
        "conso": conso,
        "desactive": desactive,
    }


def ecrire(chemin: Path, lignes: list[dict[str, Any]], schema: pa.Schema = SCHEMA) -> str:
    pq.write_table(pa.Table.from_pylist(lignes, schema=schema), chemin)
    return str(chemin)


def lire(chemin: Path) -> dict[str, dict[str, Any]]:
    return {ligne["numero_dpe"]: ligne for ligne in pq.read_table(chemin).to_pylist()}


def test_chargement_initial_tous_les_dpe_sont_des_ajouts(tmp_path: Path) -> None:
    nouveau = ecrire(tmp_path / "n.parquet", [dpe("A"), dpe("B"), dpe("C")])

    bilan = comparer_instantanes(nouveau, None, tmp_path / "c.parquet", JOUR)

    assert (bilan.nb_ajouts, bilan.nb_modifications, bilan.nb_disparitions) == (3, 0, 0)
    assert {ligne["type_changement"] for ligne in lire(tmp_path / "c.parquet").values()} == {
        "ajout"
    }


def test_photographies_identiques_aucun_changement(tmp_path: Path) -> None:
    lignes = [dpe("A"), dpe("B")]
    ancien = ecrire(tmp_path / "a.parquet", lignes)
    nouveau = ecrire(tmp_path / "n.parquet", lignes)

    bilan = comparer_instantanes(nouveau, ancien, tmp_path / "c.parquet", JOUR)

    assert bilan.nb_changements == 0
    assert lire(tmp_path / "c.parquet") == {}


def test_ajout_modification_et_disparition(tmp_path: Path) -> None:
    ancien = ecrire(tmp_path / "a.parquet", [dpe("A"), dpe("B"), dpe("C")])
    nouveau = ecrire(
        tmp_path / "n.parquet", [dpe("A"), dpe("B", etiquette="C", conso=150.0), dpe("D")]
    )

    bilan = comparer_instantanes(
        nouveau, ancien, tmp_path / "c.parquet", JOUR, seuil_disparitions=0.5
    )

    assert (bilan.nb_ajouts, bilan.nb_modifications, bilan.nb_disparitions) == (1, 1, 1)
    changements = lire(tmp_path / "c.parquet")
    assert set(changements) == {"B", "C", "D"}
    assert changements["B"]["type_changement"] == "modification"
    assert changements["B"]["etiquette_dpe"] == "C"
    assert changements["C"]["type_changement"] == "disparition"
    assert changements["C"]["etiquette_dpe"] is None
    assert changements["D"]["type_changement"] == "ajout"
    assert changements["D"]["date_instantane"] == JOUR


def test_une_desactivation_est_une_modification(tmp_path: Path) -> None:
    ancien = ecrire(tmp_path / "a.parquet", [dpe("A")])
    nouveau = ecrire(tmp_path / "n.parquet", [dpe("A", desactive=True)])

    bilan = comparer_instantanes(nouveau, ancien, tmp_path / "c.parquet", JOUR)

    assert bilan.nb_modifications == 1
    assert lire(tmp_path / "c.parquet")["A"]["desactive"] is True


def test_une_valeur_vide_qui_devient_renseignee_est_detectee(tmp_path: Path) -> None:
    ancien = ecrire(tmp_path / "a.parquet", [dpe("A", etiquette=None)])
    nouveau = ecrire(tmp_path / "n.parquet", [dpe("A", etiquette="E")])

    bilan = comparer_instantanes(nouveau, ancien, tmp_path / "c.parquet", JOUR)

    assert bilan.nb_modifications == 1


def test_un_dpe_en_double_arrete_la_comparaison(tmp_path: Path) -> None:
    nouveau = ecrire(tmp_path / "n.parquet", [dpe("A"), dpe("A", etiquette="E")])

    with pytest.raises(ComparaisonError, match="double"):
        comparer_instantanes(nouveau, None, tmp_path / "c.parquet", JOUR)


def test_des_schemas_differents_arretent_la_comparaison(tmp_path: Path) -> None:
    schema_etendu = SCHEMA.append(pa.field("surface", pa.float64()))
    ancien = ecrire(tmp_path / "a.parquet", [dpe("A")])
    nouveau = ecrire(tmp_path / "n.parquet", [{**dpe("A"), "surface": 50.0}], schema=schema_etendu)

    with pytest.raises(ComparaisonError, match="schéma"):
        comparer_instantanes(nouveau, ancien, tmp_path / "c.parquet", JOUR)


def test_trop_de_disparitions_arrete_avant_ecriture(tmp_path: Path) -> None:
    ancien = ecrire(tmp_path / "a.parquet", [dpe(str(i)) for i in range(100)])
    nouveau = ecrire(tmp_path / "n.parquet", [dpe(str(i)) for i in range(90)])

    with pytest.raises(ComparaisonError, match="disparus"):
        comparer_instantanes(nouveau, ancien, tmp_path / "c.parquet", JOUR)

    assert not (tmp_path / "c.parquet").exists()
