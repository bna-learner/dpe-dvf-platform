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

## Structure du projet

```
dpe-dvf-platform/
├── src/dpe_dvf/          # Code Python de la plateforme
│   └── ingestion/        # Ingestion des sources DPE et DVF
├── tests/                # Tests automatisés (pytest)
├── infra/                # Infrastructure as Code (Terraform)
├── docs/adr/             # Décisions d'architecture (ADR)
├── .github/workflows/    # Pipelines CI/CD (GitHub Actions)
├── pyproject.toml        # Dépendances et configuration des outils
└── uv.lock               # Versions exactes des dépendances
```
