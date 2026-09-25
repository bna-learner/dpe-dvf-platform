import pytest
from pydantic import ValidationError

from dpe_dvf.config import Settings


def test_valeurs_par_defaut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DPE_DVF_PAGE_SIZE", raising=False)
    settings = Settings(_env_file=None)
    assert settings.page_size == 1000
    assert settings.dataset_logement_existant == "dpe03existant"
    assert settings.dataset_logement_neuf == "dpe02neuf"


def test_page_size_lue_depuis_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DPE_DVF_PAGE_SIZE", "500")
    settings = Settings(_env_file=None)
    assert settings.page_size == 500


def test_page_size_nulle_rejetee(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DPE_DVF_PAGE_SIZE", "0")
    with pytest.raises(ValidationError, match="page_size"):
        Settings(_env_file=None)


def test_page_size_au_dela_du_max_rejetee(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DPE_DVF_PAGE_SIZE", "10001")
    with pytest.raises(ValidationError, match="page_size"):
        Settings(_env_file=None)
