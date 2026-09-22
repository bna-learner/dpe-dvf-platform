# ADR-0002 : Stratégie de branches et d'intégration

## Statut
Accepté

## Date
2026-09-22

## Contexte
Je dois définir comment mes développements sont intégrés dans la branche
principale (`main`) du dépôt GitHub.

Contraintes :
- **Un seul développeur** : GitHub ne permet pas d'approuver sa propre PR.
- **CI/CD** : des déploiements automatiques partiront de `main`, qui doit
  donc toujours être stable et déployable.
- **Traçabilité** : l'historique doit rester propre et lisible. Le dépôt est
  public et sert de vitrine technique.
- **Sécurité de `main`** : aucune modification ne doit y arriver sans être passée
  par un processus de validation.

## Décision
1. **Trunk-based development** : une seule branche longue (`main`) et des branches
   courtes, supprimées rapidement, pour chaque évolution du projet.
2. **Squash and merge** comme unique stratégie de fusion : chaque PR devient un
   seul commit sur `main`, dont le message est le titre de la PR.
3. **Nommage des branches** : `type/description-courte`
   (ex. `feat/client-api-dpe`, `docs/adr-0002`).
4. **Conventional commits** : format `type: description`, pour les commits
   comme pour les **titres de PR**, puisqu'ils deviennent les messages des
   commits sur `main`. Un commit correspond à un seul changement logique.
5. **Ruleset sur `main`** :
   - PR obligatoire, historique linéaire, force push et suppression interdits ;
   - 0 approbation requise, puisque je suis seul et ne peux pas approuver mes
     propres PR : la validation repose sur une auto-relecture, complétée par
     une CI obligatoire à partir de la Phase 2 ;
   - aucun bypass, pour que même l'administrateur du dépôt ne puisse pas
     contourner les règles.
6. **Suppression automatique** des branches après fusion.

## Alternatives considérées
- **Merge commit** : écarté. Il ajoute des commits de fusion et rend l'historique
  non linéaire, ce qui va contre la contrainte de traçabilité.
- **Rebase and merge** : écarté. L'historique reste linéaire, mais tous les
  commits intermédiaires (« wip », « fix typo »…) arrivent sur `main`, ce qui
  nuit à sa lisibilité.
- **GitFlow** : écarté. Il est conçu pour maintenir plusieurs versions en
  production, ce qui n'est pas le cas ici : seule `main` est déployée. Ses
  branches longues (`develop`) retardent aussi l'intégration, contrairement à
  l'objectif d'une `main` toujours à jour et déployable.
- **Push direct sur `main` sans protection** : écarté. Rien ne garantirait que
  `main` reste stable et déployable.

## Conséquences

Positives :
- `main` reste toujours stable et déployable, prête pour la CI/CD.
- L'historique est linéaire, avec un commit par PR et des messages normalisés.
- Les règles s'appliquent automatiquement, sans reposer sur la discipline.

Négatives :
- Même une modification d'une ligne demande une branche et une PR, ce qui
  ajoute de la friction.
- Le squash fait perdre le détail des commits intermédiaires sur `main`.
  Mitigation : ce détail reste consultable dans la PR sur GitHub.
- Étant seul, la revue est une auto-relecture, ce qui limite sa qualité.
  Mitigation : CI obligatoire.
- Avec le squash, la qualité des titres de PR devient critique.
- Mettre à jour une branche avec `rebase` demande de maîtriser la résolution
  de conflits.
