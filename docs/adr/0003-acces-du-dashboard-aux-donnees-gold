# ADR-0003 : Accès du dashboard aux données gold

## Statut
Accepté

## Date
2026-10-12

## Contexte
Le dashboard de la plateforme doit lire les indicateurs de la couche gold,
stockés dans un bucket S3 privé.

Contraintes :
- **Hébergement** : le dashboard est développé avec Streamlit et hébergé sur
  Streamlit Community Cloud, gratuit et accessible par une URL publique, pour
  être présenté à tout moment.
- **Règle de sécurité du projet** : aucune clé permanente ; les traitements
  automatisés (GitHub Actions) obtiennent des identifiants temporaires par OIDC.
  Streamlit Community Cloud ne permet pas cette authentification.
- **Nature des données** : gold ne contient que des agrégats de données ouvertes
  (Licence Ouverte de l'ADEME), sans aucune donnée à caractère personnel.
- **Coût** : projet financé personnellement. Le dashboard doit rester
  accessible en continu pour un coût quasi nul, sans dépendre d'avantages
  temporaires (crédits, offre gratuite).

## Décision
1. **Gold matérialisé en Parquet** : chaque semaine, après silver, le pipeline
   écrit les résultats des requêtes gold dans le bucket gold.
2. **Un utilisateur IAM dédié au dashboard**, dont la seule permission est la
   lecture du bucket gold (principe du moindre privilège).
3. **Une clé d'accès** pour cet utilisateur, stockée uniquement dans les secrets
   de Streamlit Community Cloud ; jamais dans le code, le dépôt, ni le state
   Terraform.

## Alternatives considérées
- **Interroger Athena en direct** : écarté. Chaque visite déclencherait des
  requêtes facturées, et la clé nécessiterait des droits plus larges (Athena,
  Glue, plusieurs buckets).
- **Héberger le dashboard sur AWS avec un rôle IAM** : écarté. Aucune clé
  permanente, mais un coût continu, incompatible avec un budget quasi nul.
- **Rendre gold public** : écarté. Possible puisque les données sont ouvertes,
  mais c'est une exposition volontaire sur Internet, alors qu'une lecture
  contrôlée est possible pour un coût nul.

## Conséquences

Positives :
- **Coût quasi nul** : le dashboard lit quelques Ko de Parquet, sans déclencher
  aucune requête Athena.
- **Dashboard rapide**, et indépendant d'Athena.
- **Hébergement gratuit**.

Négatives :
- **Une clé permanente existe**, seule exception à la règle du projet.
  - **Impact en cas de fuite** : la lecture d'agrégats déjà publics, et rien
    d'autre ; aucune écriture, aucun autre service, aucune donnée sensible.
  - **Mitigations** : permission limitée à la lecture d'un seul bucket ; clé
    stockée uniquement dans les secrets de Streamlit ; renouvellement tous les
    90 jours.
  - **En cas de fuite** : désactiver la clé dans IAM, en créer une nouvelle,
    mettre à jour le secret de Streamlit.
- **Fraîcheur limitée** : le dashboard affiche l'état de gold au dernier calcul
  hebdomadaire.
