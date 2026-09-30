from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

ANNEE_CONSTRUCTION_MIN = 1000


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
    date_derniere_modification_dpe: date | None = None
    date_reception_dpe: date | None = None

    # Bilan DPE
    etiquette_dpe: ClasseDPE | None = None
    etiquette_ges: ClasseDPE | None = None

    # Caractéristiques bâtiments
    periode_construction: str | None = None
    annee_construction: int | None = None
    surface_habitable_logement: float | None = Field(default=None, gt=0)
    type_batiment: str | None = None

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
    code_departement_ban: str | None = None
    code_region_ban: str | None = None

    @field_validator("annee_construction")
    @classmethod
    def _ecarter_annee_impossible(cls, annee: int | None) -> int | None:
        """Une année antérieure à 1000 ou
        future est une erreur de saisie : la valeur est écartée."""
        if annee is not None and not ANNEE_CONSTRUCTION_MIN <= annee <= date.today().year:
            return None
        return annee
