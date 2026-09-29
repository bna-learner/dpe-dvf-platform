from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from dpe_dvf.config import Settings
from dpe_dvf.ingestion.bronze import NOM_MANIFESTE
from dpe_dvf.ingestion.cli import ingerer, main, resoudre_datasets
from dpe_dvf.ingestion.client_ademe import Ligne, Params
from dpe_dvf.ingestion.fenetres import Fenetre


class FausseSource:
    """Renvoie une page par appel et enregistre les appels reçus."""

    def __init__(self) -> None:
        self.appels: list[tuple[str, Params | None]] = []

    def iter_pages(self, dataset_id: str, params: Params | None = None) -> Iterator[list[Ligne]]:
        self.appels.append((dataset_id, params))
        yield [{"numero_dpe": f"{dataset_id}-{len(self.appels)}"}]


def test_un_lot_par_mois(tmp_path: Path) -> None:
    source = FausseSource()
    fenetre = Fenetre(date(2026, 6, 15), date(2026, 8, 1))

    resultats = ingerer(source, ["dpe02neuf"], fenetre, tmp_path, date(2026, 9, 29))

    assert len(resultats) == 2
    assert all((r.dossier / NOM_MANIFESTE).exists() for r in resultats)


def test_les_filtres_de_date_sont_transmis(tmp_path: Path) -> None:
    source = FausseSource()
    fenetre = Fenetre(date(2026, 8, 1), date(2026, 9, 1))

    ingerer(source, ["dpe02neuf"], fenetre, tmp_path, date(2026, 9, 29))

    assert source.appels == [
        (
            "dpe02neuf",
            {"date_reception_dpe_gte": "2026-08-01", "date_reception_dpe_lt": "2026-09-01"},
        )
    ]


def test_tous_les_jeux_de_donnees() -> None:
    settings = Settings(_env_file=None)
    assert resoudre_datasets("tous", settings) == ["dpe03existant", "dpe02neuf"]


def test_fenetre_inversee_refusee_proprement() -> None:
    with pytest.raises(SystemExit) as info:
        main(["--debut", "2026-09-01", "--fin", "2026-08-01"])
    assert info.value.code == 2  # code d'erreur d'usage d'argparse
