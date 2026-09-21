# ADR-0001 : Structure du projet et outillage Python

## Statut
Accepté

## Date
2026-09-21

## Contexte
Je construis une plateforme data qui va réunir plusieurs types de code :
ingestion Python (DPE, DVF), transformations Spark et dbt, infrastructure
Terraform, pipelines CI GitHub Actions.

Contraintes:
- Un seul développeur : maintenir plusieurs repos serait un surcoût.
- Le code s'exécute à plusieurs endroits (ma machine, la CI, puis AWS et
  Databricks) : les installations doivent être identiques partout.
- Le repo est public et sert de vitrine technique : il doit suivre les
  standards actuels et être lisible rapidement.
- La qualité du code doit être vérifiée automatiquement, pas reposer sur
  la discipline.

## Décision
1. **Monorepo** : ingestion, transformations, infra, CI et docs dans un seul repo.
2. **uv** pour gérer Python, l'environnement virtuel et les dépendances, avec
   un `uv.lock` commité.
3. **Layout `src/`** : le package vit dans `src/dpe_dvf/`.
4. **ruff** pour le linting et le formatage.
5. **mypy en mode strict** pour la vérification des types.
6. **pre-commit** pour lancer ces vérifications avant chaque commit.
## Alternatives considérées
- **Multi-repo** : écarté. Pour une seule personne, il multiplie les CI, les
  configurations et la coordination des versions entre repos.
- **pip + venv** : écarté. Pas de lockfile natif, donc pas de garantie
  d'installation identique entre ma machine et la CI.
- **poetry** : solution mature, mais plus lente et ne gère pas les versions
  de Python ; uv couvre tout le besoin avec un seul outil.
- **Layout plat** (package à la racine) : écarté. Les tests peuvent importer
  les fichiers locaux au lieu du package installé, ce qui masque les
  erreurs de packaging.
- **flake8 + isort + black** : écarté. Trois outils et trois configurations
  pour un résultat que ruff fournit seul.
- **pyright** : alternative crédible à mypy ; mypy retenu car plus répandu
  dans les projets Python existants.

## Conséquences

Positives :
- Installations reproductibles partout grâce à `uv.lock`.
- Qualité homogène, vérifiée automatiquement à chaque commit.
- Un seul endroit pour comprendre tout le projet.

Négatives :
- uv est plus récent que pip et poetry : ses évolutions peuvent imposer des
  ajustements.
- Quand le monorepo grossira, la CI devra ne lancer que les jobs concernés
  par les dossiers modifiés.
- pre-commit et mypy strict ajoutent de la friction, surtout au début.
- ruff ne couvre pas toutes les règles de pylint.
