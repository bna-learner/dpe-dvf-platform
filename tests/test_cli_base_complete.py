from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from dpe_dvf.base_complete import cli
from dpe_dvf.base_complete.cli import executer_chaine, instantane_precedent
from dpe_dvf.base_complete.extraction import ExtractionError

JOUR = date(2026, 11, 24)
Journal = list[tuple[str, dict[str, Any]]]


def creer_instantane(dossier: Path, nom: str, avec_fichier: bool = True) -> Path:
    chemin = dossier / nom
    chemin.mkdir(parents=True)
    if avec_fichier:
        (chemin / "part-0.parquet").write_bytes(b"")
    return chemin


def enregistreur(journal: Journal, nom: str) -> Callable[..., None]:
    """Doublure : enregistre ses arguments nommés au lieu d'exécuter la vraie fonction."""

    def fonction(**arguments: Any) -> None:
        journal.append((nom, arguments))

    return fonction


@pytest.fixture
def appels(monkeypatch: pytest.MonkeyPatch) -> Journal:
    journal: Journal = []
    monkeypatch.setattr(cli, "extraire_instantane", enregistreur(journal, "extraction"))
    monkeypatch.setattr(cli, "comparer_instantanes", enregistreur(journal, "comparaison"))
    monkeypatch.setattr(cli, "transformer_photographie", enregistreur(journal, "silver"))
    return journal


def test_aucune_photographie_precedente(tmp_path: Path) -> None:
    assert instantane_precedent(tmp_path / "absent", JOUR) is None


def test_la_plus_recente_avant_le_jour(tmp_path: Path) -> None:
    for jour in ("2026-11-10", "2026-11-17", "2026-11-24", "2026-12-01"):
        creer_instantane(tmp_path, f"date_instantane={jour}")

    assert instantane_precedent(tmp_path, JOUR) == tmp_path / "date_instantane=2026-11-17"


def test_ignore_les_dossiers_temporaires_vides_ou_mal_nommes(tmp_path: Path) -> None:
    creer_instantane(tmp_path, "date_instantane=2026-11-10")
    creer_instantane(tmp_path, "date_instantane=2026-11-17.tmp")
    creer_instantane(tmp_path, "date_instantane=2026-11-18", avec_fichier=False)
    creer_instantane(tmp_path, "date_instantane=pas-une-date")

    assert instantane_precedent(tmp_path, JOUR) == tmp_path / "date_instantane=2026-11-10"


def test_chargement_initial(tmp_path: Path, appels: Journal) -> None:
    executer_chaine(JOUR, tmp_path, "base.duckdb")

    assert [nom for nom, _ in appels] == ["extraction", "comparaison", "silver"]
    assert appels[1][1]["ancien"] is None


def test_comparaison_a_la_photographie_precedente(tmp_path: Path, appels: Journal) -> None:
    creer_instantane(tmp_path / "bronze" / "instantanes", "date_instantane=2026-11-17")

    executer_chaine(JOUR, tmp_path, "base.duckdb")

    extraction, comparaison, silver = (arguments for _, arguments in appels)
    nouveau = tmp_path / "bronze" / "instantanes" / "date_instantane=2026-11-24"
    assert extraction["sortie"] == nouveau
    assert comparaison["ancien"] == str(
        tmp_path / "bronze" / "instantanes" / "date_instantane=2026-11-17" / "*.parquet"
    )
    assert comparaison["sortie"] == (
        tmp_path / "bronze" / "changements" / "date_instantane=2026-11-24" / "changements.parquet"
    )
    assert silver["photographie"] == str(nouveau / "*.parquet")
    assert silver["racine_silver"] == tmp_path / "silver"


def test_main_transmet_la_date_et_la_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal: Journal = []
    monkeypatch.setattr(cli, "executer_chaine", enregistreur(journal, "chaine"))
    monkeypatch.setenv("DPE_DVF_DOSSIER_BASE_COMPLETE", str(tmp_path))

    assert cli.main(["--date", "2026-11-24"]) == 0
    assert journal[0][1]["jour"] == JOUR
    assert journal[0][1]["racine"] == tmp_path


def test_main_renvoie_1_si_la_chaine_echoue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def echec(**arguments: Any) -> None:
        raise ExtractionError("source indisponible")

    monkeypatch.setattr(cli, "executer_chaine", echec)
    monkeypatch.setenv("DPE_DVF_DOSSIER_BASE_COMPLETE", str(tmp_path))

    assert cli.main(["--date", "2026-11-24"]) == 1
