# dpe_dvf_platform
Plateforme data sur AWS croisant les données DPE (logements neufs et logements existants) de l'ADEME ainsi que les demandes de valeurs foncières (DVF), pour du reporting et cas d'IA générative (recommandations de rénovation énergétique pour augmenter la valeur d'un logement).

## Prérequis
- [uv](https://docs.astral.sh/uv/)

## Démarrage
```bash
uv sync
uv run pre-commit install
uv run pytest
```
