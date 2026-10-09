import pytest

from dpe_dvf.transformation.geographie import departement_depuis_code_postal


@pytest.mark.parametrize(
    ("code_postal", "departement_attendu"),
    [
        ("75011", "75"),  # cas général
        ("01000", "01"),  # zéro initial conservé
        ("20000", "2A"),  # Ajaccio
        ("20137", "2A"),  # Porto-Vecchio
        ("20200", "2B"),  # Bastia
        ("20250", "2B"),  # Corte
        ("97400", "974"),  # La Réunion
        ("97100", "971"),  # Guadeloupe
        ("98000", None),  # Monaco : pas un département français
        ("7501", None),  # longueur invalide
        ("ABCDE", None),  # pas des chiffres
        (None, None),
    ],
)
def test_departement_depuis_code_postal(
    code_postal: str | None, departement_attendu: str | None
) -> None:
    assert departement_depuis_code_postal(code_postal) == departement_attendu
