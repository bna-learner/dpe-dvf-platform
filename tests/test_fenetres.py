from datetime import date

import pytest

from dpe_dvf.ingestion.fenetres import Fenetre, decouper_par_mois


def test_fenetre_inversee_rejetee() -> None:
    with pytest.raises(ValueError, match="inversée"):
        Fenetre(date(2026, 9, 1), date(2026, 8, 1))


def test_fenetre_vide_rejetee() -> None:
    with pytest.raises(ValueError):
        Fenetre(date(2026, 9, 1), date(2026, 9, 1))


def test_traduction_en_filtres_api() -> None:
    fenetre = Fenetre(date(2026, 8, 1), date(2026, 9, 1))
    assert fenetre.en_params("date_reception_dpe") == {
        "date_reception_dpe_gte": "2026-08-01",
        "date_reception_dpe_lt": "2026-09-01",
    }


def test_decoupage_avec_debut_et_fin_en_milieu_de_mois() -> None:
    fenetre = Fenetre(date(2026, 6, 15), date(2026, 9, 10))
    assert list(decouper_par_mois(fenetre)) == [
        Fenetre(date(2026, 6, 15), date(2026, 7, 1)),
        Fenetre(date(2026, 7, 1), date(2026, 8, 1)),
        Fenetre(date(2026, 8, 1), date(2026, 9, 1)),
        Fenetre(date(2026, 9, 1), date(2026, 9, 10)),
    ]


def test_decoupage_passe_le_changement_d_annee() -> None:
    fenetre = Fenetre(date(2025, 12, 1), date(2026, 2, 1))
    assert list(decouper_par_mois(fenetre)) == [
        Fenetre(date(2025, 12, 1), date(2026, 1, 1)),
        Fenetre(date(2026, 1, 1), date(2026, 2, 1)),
    ]
