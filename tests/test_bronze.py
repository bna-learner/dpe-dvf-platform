import gzip
import json
from datetime import date
from pathlib import Path

from dpe_dvf.ingestion.bronze import NOM_MANIFESTE, chemin_lot, ecrire_lot
from dpe_dvf.ingestion.fenetres import Fenetre

PAGES = [
    [{"numero_dpe": "A", "nom_commune_brut": "Évry"}, {"numero_dpe": "B"}],
    [{"numero_dpe": "C"}],
]


def lire_lignes(fichier: Path) -> list[dict[str, object]]:
    with gzip.open(fichier, "rt", encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f]


def test_chemin_partitionne() -> None:
    fenetre = Fenetre(date(2026, 6, 1), date(2026, 7, 1))
    chemin = chemin_lot(Path("bronze"), "dpe03existant", fenetre, date(2026, 9, 29))
    assert chemin == Path(
        "bronze/source=api_ademe/dataset=dpe03existant/"
        "date_ingestion=2026-09-29/fenetre=2026-06-01_2026-07-01"
    )


def test_un_fichier_par_page(tmp_path: Path) -> None:
    resultat = ecrire_lot(PAGES, tmp_path / "lot", {"dataset": "test"})

    assert resultat.nb_fichiers == 2
    assert resultat.nb_lignes == 3
    noms = sorted(p.name for p in (tmp_path / "lot").glob("part-*.jsonl.gz"))
    assert noms == ["part-00001.jsonl.gz", "part-00002.jsonl.gz"]


def test_contenu_relu_a_l_identique(tmp_path: Path) -> None:
    ecrire_lot(PAGES, tmp_path / "lot", {"dataset": "test"})

    relues = lire_lignes(tmp_path / "lot" / "part-00001.jsonl.gz")
    assert relues == PAGES[0]  # accents compris


def test_manifeste_decrit_le_lot(tmp_path: Path) -> None:
    ecrire_lot(PAGES, tmp_path / "lot", {"dataset": "dpe03existant"})

    manifeste = json.loads((tmp_path / "lot" / NOM_MANIFESTE).read_text(encoding="utf-8"))
    assert manifeste["dataset"] == "dpe03existant"
    assert manifeste["nb_lignes"] == 3
    assert "termine_le" in manifeste


def test_relancer_un_lot_le_remplace(tmp_path: Path) -> None:
    ecrire_lot(PAGES, tmp_path / "lot", {"dataset": "test"})
    ecrire_lot([[{"numero_dpe": "Z"}]], tmp_path / "lot", {"dataset": "test"})

    fichiers = sorted(p.name for p in (tmp_path / "lot").iterdir())
    assert fichiers == [NOM_MANIFESTE, "part-00001.jsonl.gz"]
    assert lire_lignes(tmp_path / "lot" / "part-00001.jsonl.gz") == [{"numero_dpe": "Z"}]


def test_aucun_fichier_temporaire_ne_reste(tmp_path: Path) -> None:
    ecrire_lot(PAGES, tmp_path / "lot", {"dataset": "test"})
    assert not list((tmp_path / "lot").glob("*.tmp"))
