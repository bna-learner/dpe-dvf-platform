from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from dpe_dvf.ingestion.models import DPE


@pytest.fixture
def dpe_valide() -> dict[str, Any]:
    """DPE minimal pour tester le modèle de donnée."""
    return {
        "numero_dpe": "2675E0004081B",
        "date_etablissement_dpe": "2024-03-15",
        "etiquette_dpe": "C",
        "etiquette_ges": "B",
        "surface_habitable_logement": 85.5,
        "score_ban": 0.95,
    }


def test_dpe_valide_se_construit(dpe_valide: dict[str, Any]) -> None:
    dpe = DPE(**dpe_valide)
    assert dpe.numero_dpe == "2675E0004081B"


def test_etiquette_invalide_rejetee(dpe_valide: dict[str, Any]) -> None:
    dpe_valide["etiquette_dpe"] = "Z"
    with pytest.raises(ValidationError, match="etiquette_dpe"):
        DPE(**dpe_valide)


def test_surface_negative_rejetee(dpe_valide: dict[str, Any]) -> None:
    dpe_valide["surface_habitable_logement"] = -50
    with pytest.raises(ValidationError, match="surface_habitable_logement"):
        DPE(**dpe_valide)


def test_absence_etiquette_dpe(dpe_valide: dict[str, Any]) -> None:
    del dpe_valide["etiquette_dpe"]
    dpe = DPE(**dpe_valide)
    assert dpe.etiquette_dpe is None


def test_numero_dpe_obligatoire(dpe_valide: dict[str, Any]) -> None:
    del dpe_valide["numero_dpe"]
    with pytest.raises(ValidationError, match="numero_dpe"):
        DPE(**dpe_valide)


def test_score_ban_sup_1(dpe_valide: dict[str, Any]) -> None:
    dpe_valide["score_ban"] = 2
    with pytest.raises(ValidationError, match="score_ban"):
        DPE(**dpe_valide)


def test_annee_construction_future_ecartee(dpe_valide: dict[str, Any]) -> None:
    dpe_valide["annee_construction"] = 3000
    dpe = DPE(**dpe_valide)
    assert dpe.annee_construction is None


def test_annee_construction_trop_ancienne_ecartee(dpe_valide: dict[str, Any]) -> None:
    dpe_valide["annee_construction"] = 500
    dpe = DPE(**dpe_valide)
    assert dpe.annee_construction is None


def test_annee_construction_plausible_conservee(dpe_valide: dict[str, Any]) -> None:
    dpe_valide["annee_construction"] = 1975
    dpe = DPE(**dpe_valide)
    assert dpe.annee_construction == 1975


def test_conversion_date_reception_dpe(dpe_valide: dict[str, Any]) -> None:
    dpe_valide["date_reception_dpe"] = "2026-09-20"
    dpe = DPE(**dpe_valide)
    assert dpe.date_reception_dpe == date(2026, 9, 20)


def test_ajout_de_champ_supplementaire(dpe_valide: dict[str, Any]) -> None:
    dpe_valide["hauteur_sous_plafond"] = 12
    dpe = DPE(**dpe_valide)
    assert "hauteur_sous_plafond" not in dpe.model_dump()


@pytest.mark.parametrize(
    ("valeur_api", "attendu"),
    [(1000, "01000"), (75011, "75011"), ("75011", "75011"), ("ABCDE", None), (123, None)],
)
def test_code_postal_normalise(
    dpe_valide: dict[str, Any], valeur_api: object, attendu: str | None
) -> None:
    dpe_valide["code_postal_brut"] = valeur_api
    assert DPE(**dpe_valide).code_postal_brut == attendu
