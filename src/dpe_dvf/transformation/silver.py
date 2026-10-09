"""Transformation bronze → silver : validation, typage et écriture en Parquet."""

import gzip
import json
import logging
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import ValidationError

from dpe_dvf.config import Settings
from dpe_dvf.ingestion.bronze import NOM_MANIFESTE
from dpe_dvf.ingestion.models import DPE
from dpe_dvf.transformation.geographie import departement_depuis_code_postal

logger = logging.getLogger(__name__)

TAILLE_TAMPON = 50_000  # lignes écrites d'un coup dans le Parquet

COLONNES_PROVENANCE = ["dataset", "date_ingestion"]

SCHEMA_SILVER = pa.schema(
    [
        ("numero_dpe", pa.string()),
        ("date_etablissement_dpe", pa.date32()),
        ("date_reception_dpe", pa.date32()),
        ("date_derniere_modification_dpe", pa.date32()),
        ("etiquette_dpe", pa.string()),
        ("etiquette_ges", pa.string()),
        ("type_batiment", pa.string()),
        ("periode_construction", pa.string()),
        ("annee_construction", pa.int32()),
        ("surface_habitable_logement", pa.float64()),
        ("conso_5_usages_ep", pa.float64()),
        ("conso_5_usages_par_m2_ep", pa.float64()),
        ("identifiant_ban", pa.string()),
        ("score_ban", pa.float64()),
        ("statut_geocodage", pa.string()),
        ("adresse_brut", pa.string()),
        ("nom_commune_brut", pa.string()),
        ("code_postal_ban", pa.string()),
        ("code_insee_ban", pa.string()),
        ("code_departement_ban", pa.string()),
        ("code_region_ban", pa.string()),
        ("code_postal_brut", pa.string()),
        ("code_departement", pa.string()),
        ("source_departement", pa.string()),
        ("coordonnee_cartographique_x_ban", pa.float64()),
        ("coordonnee_cartographique_y_ban", pa.float64()),
        # Provenance : d'où vient chaque ligne
        ("dataset", pa.string()),
        ("date_ingestion", pa.date32()),
    ]
)


@dataclass(frozen=True)
class ResultatSilver:
    """Bilan de la transformation d'un lot."""

    fichier: Path
    nb_valides: int
    nb_rejets: int


def lots_complets(racine_bronze: Path) -> list[Path]:
    """Liste les lots bronze terminés, c'est-à-dire ceux qui ont un manifeste."""
    motif = f"source=*/dataset=*/date_ingestion=*/fenetre=*/{NOM_MANIFESTE}"
    return sorted(manifeste.parent for manifeste in racine_bronze.glob(motif))


def lire_lignes_bronze(dossier: Path) -> Iterator[dict[str, Any]]:
    """Relit, une à une, toutes les lignes d'un lot bronze."""
    for fichier in sorted(dossier.glob("part-*.jsonl.gz")):
        with gzip.open(fichier, "rt", encoding="utf-8") as f:
            for ligne in f:
                yield json.loads(ligne)


def _partition(manifeste: dict[str, str]) -> Path:
    return (
        Path(f"dataset={manifeste['dataset']}")
        / f"date_ingestion={manifeste['date_ingestion']}"
        / f"fenetre={manifeste['fenetre_debut']}_{manifeste['fenetre_fin']}"
    )


COLONNES_DERIVEES = ["code_departement", "source_departement"]


def _departement(dpe: DPE) -> dict[str, str | None]:
    """Département retenu : celui de la BAN, sinon celui déduit du code postal saisi."""
    if dpe.code_departement_ban is not None:
        return {"code_departement": dpe.code_departement_ban, "source_departement": "ban"}
    deduit = departement_depuis_code_postal(dpe.code_postal_brut)
    if deduit is not None:
        return {"code_departement": deduit, "source_departement": "code_postal"}
    return {"code_departement": None, "source_departement": None}


def transformer_lot(dossier_bronze: Path, racine_silver: Path) -> ResultatSilver:
    """Valide un lot bronze et l'écrit en Parquet ; les lignes invalides vont en quarantaine."""
    manifeste = json.loads((dossier_bronze / NOM_MANIFESTE).read_text(encoding="utf-8"))
    provenance = {
        "dataset": manifeste["dataset"],
        "date_ingestion": date.fromisoformat(manifeste["date_ingestion"]),
    }
    partition = _partition(manifeste)

    dossier_cible = racine_silver / "dpe" / partition
    dossier_rejets = racine_silver / "rejets_dpe" / partition
    dossier_cible.mkdir(parents=True, exist_ok=True)
    dossier_rejets.mkdir(parents=True, exist_ok=True)

    cible = dossier_cible / "dpe.parquet"
    cible_tmp = cible.with_name(cible.name + ".tmp")
    rejets = dossier_rejets / "rejets.jsonl"
    rejets_tmp = rejets.with_name(rejets.name + ".tmp")

    nb_valides = 0
    nb_rejets = 0
    valeurs_ecartees: Counter[str] = Counter()
    tampon: list[dict[str, Any]] = []

    with (
        pq.ParquetWriter(cible_tmp, SCHEMA_SILVER) as writer,
        rejets_tmp.open("w", encoding="utf-8") as fichier_rejets,
    ):
        for brut in lire_lignes_bronze(dossier_bronze):
            try:
                dpe = DPE(**brut)
            except ValidationError as erreur:
                nb_rejets += 1
                rejet = {
                    "numero_dpe": brut.get("numero_dpe"),
                    "erreurs": json.loads(erreur.json(include_url=False)),
                }
                fichier_rejets.write(json.dumps(rejet, ensure_ascii=False) + "\n")
                continue

            for champ in DPE.model_fields:
                if brut.get(champ) is not None and getattr(dpe, champ) is None:
                    valeurs_ecartees[champ] += 1

            tampon.append({**dpe.model_dump(), **provenance, **_departement(dpe)})
            nb_valides += 1
            if len(tampon) >= TAILLE_TAMPON:
                writer.write_table(pa.Table.from_pylist(tampon, schema=SCHEMA_SILVER))
                tampon.clear()

        if tampon:
            writer.write_table(pa.Table.from_pylist(tampon, schema=SCHEMA_SILVER))

    cible_tmp.replace(cible)
    rejets_tmp.replace(rejets)

    bilan = {
        "source": str(dossier_bronze),
        "nb_valides": nb_valides,
        "nb_rejets": nb_rejets,
        "valeurs_ecartees": dict(valeurs_ecartees),
    }
    (dossier_cible / NOM_MANIFESTE).write_text(json.dumps(bilan, indent=2), encoding="utf-8")

    total = nb_valides + nb_rejets
    taux = nb_rejets / total if total else 0.0
    niveau = logging.WARNING if taux > 0.01 else logging.INFO
    logger.log(
        niveau,
        "Lot %s : %d lignes valides, %d rejets (%.2f %%)",
        partition,
        nb_valides,
        nb_rejets,
        taux * 100,
    )

    if valeurs_ecartees:
        logger.warning("Lot %s : valeurs écartées %s", partition, dict(valeurs_ecartees))
    return ResultatSilver(cible, nb_valides, nb_rejets)


def main(argv: Sequence[str] | None = None) -> int:
    """Transforme tous les lots bronze terminés en silver (recalcul complet)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s : %(message)s",
    )
    settings = Settings()
    lots = lots_complets(settings.dossier_bronze)
    logger.info("%d lots bronze terminés à transformer", len(lots))

    resultats = [transformer_lot(lot, settings.dossier_silver) for lot in lots]

    valides = sum(r.nb_valides for r in resultats)
    rejets = sum(r.nb_rejets for r in resultats)
    logger.info("Silver terminé : %d lignes valides, %d rejets", valides, rejets)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
