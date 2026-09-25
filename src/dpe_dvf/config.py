from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration de la plateforme, lue depuis l'environnement.

    Chaque champ peut être surchargé par une variable d'environnement
    préfixée par DPE_DVF_ (ex. DPE_DVF_PAGE_SIZE), ou dans un fichier .env.
    """

    model_config = SettingsConfigDict(env_prefix="DPE_DVF_", env_file=".env", extra="ignore")
    ademe_base_url: str = "https://data.ademe.fr/data-fair/api/v1/datasets"
    dataset_logement_neuf: str = "dpe02neuf"
    dataset_logement_existant: str = "dpe03existant"
    page_size: int = Field(default=1000, gt=0, le=10000)
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=5, ge=0)  # 6 tentatives au total
    backoff_base_seconds: float = Field(default=2.0, gt=0)
    backoff_max_seconds: float = Field(default=60.0, gt=0)
