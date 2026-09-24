from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ClasseDPE(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    G = "G"


class DPE(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Administratif
    numero_dpe: str
    date_etablissement_dpe: date | None = None
    date_reception_dpe: date | None = None

    # Bilan DPE
    etiquette_dpe: ClasseDPE | None = None
    etiquette_ges: ClasseDPE | None = None

    # Caractéristiques bâtiments
    periode_construction: str | None = None
    annee_construction: int | None = Field(default=None, ge=1000, le=2026)
    surface_habitable_logement: float | None = Field(default=None, gt=0)

    # Consommation énergie primaire (ep)
    conso_5_usages_ep: float | None = Field(default=None, gt=0)
    conso_5_usages_par_m2_ep: float | None = Field(default=None, gt=0)

    # Localisation
    identifiant_ban: str | None = None
    score_ban: float | None = Field(default=None, ge=0, le=1)
    nom_commune_brut: str | None = None
    adresse_brut: str | None = None
    code_postal_ban: str | None = None
    code_insee_ban: str | None = None
    statut_geocodage: str | None = None
    coordonnee_cartographique_x_ban: float | None = None
    coordonnee_cartographique_y_ban: float | None = None
