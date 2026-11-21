# Correspondance entre l'API et la base complète des DPE

Ce document décrit comment reconstruire, à partir de la base complète de
l'ADEME, les DPE tels que les publie l'API (`dpe03existant` et `dpe02neuf`),
au format du modèle silver. Chaque règle a été établie par une mesure, en
novembre 2026.

## Source

La base complète est publiée chaque semaine par l'ADEME en Parquet, et
interrogeable avec DuckDB sans téléchargement préalable :

```sql
ATTACH 'https://s3.fr-par.scw.cloud/prod-dpe-opendata/dpe/dpe.duckdb' AS src_dpe (READ_ONLY);
COPY FROM DATABASE src_dpe TO opendata;
DETACH DATABASE IF EXISTS src_dpe;
```

La copie locale (`opendata.duckdb`) ne contient que des vues, qui lisent à
distance les fichiers Parquet de l'ADEME. Elle compte 175 vues : 45 tables de
données et 130 référentiels (`*_enum_*`, `*_tv_*`). C'est le même modèle
normalisé que le dump PostgreSQL de l'ADEME.

À ne pas stocker sur un système de fichiers exFAT : la base locale y a été
perdue une fois (verrous et journal de DuckDB mal pris en charge).

## Périmètre : quels DPE publie l'API

L'API publie les DPE qui vérifient les trois conditions :

| Condition | Colonne |
|---|---|
| DPE de logement | `dpe_administratif.enum_modele_dpe_id IN (1, 2, 3)` |
| non désactivé | `NOT dpe.desactive` |
| non en cours de suppression | `NOT dpe.suppression_en_cours` |

Modèles : 1 = existant (`dpe03existant`) ; 2 et 3 = neuf, RT2012 et RE2020
(`dpe02neuf`) ; 4 = tertiaire, hors périmètre.

Mesure (base du 17 novembre 2026) : sur 20 200 182 DPE, 17 498 743
remplissent les trois conditions. Les exclusions se répartissent entre
DPE désactivés (2 114 966), en cours de suppression (121) et tertiaires.

Validation : sur janvier 2025, période close, les DPE neufs concordent
exactement avec l'API (21 924), les existants à 5 DPE près sur 285 088 ; le
seul écart examiné aux bornes du mois est un DPE remplacé entre les deux
photographies.

## Jointures

Toutes les jointures sont de un à un : chacun des 17 498 743 DPE du périmètre
a exactement une ligne dans chaque table.

```
dpe.id ──┬── dpe_administratif.dpe_id
         ├── dpe_caracteristique_generale.dpe_id
         ├── dpe_ep_conso.dpe_id
         ├── dpe_emission_ges.dpe_id
         └── dpe_geolocalisation.administratif_id
                 └── dpe_geolocalisation.adresse_bien_id ── dpe_t_adresse.id
```

Référentiels :

| Code | Référentiel | Libellé utilisé |
|---|---|---|
| `dpe_caracteristique_generale.enum_methode_application_dpe_log_id` | `dpe_enum_methode_application_dpe_log` | `type_batiment` |
| `dpe_caracteristique_generale.enum_periode_construction_id` | `dpe_enum_periode_construction` | `lib` |
| `dpe_t_adresse.enum_statut_geocodage_ban_id` | `dpe_enum_statut_geocodage_ban` | `lib` |

Les libellés des référentiels sont identiques à ceux de l'API.

## Conventions

- **Dates** : les horodatages de la base sont en UTC ; l'API les exprime à
  l'heure de Paris. Conversion :
  `CAST((horodatage AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Paris' AS DATE)`.
  Mesure : 171 DPE reçus près de minuit départagent les deux conventions,
  tous en faveur de l'heure de Paris.
- **Arrondis** : l'API arrondit ou tronque certains nombres. Les arrondis se
  calculent en `DECIMAL`, jamais en `DOUBLE` : en binaire, 35,65 est stocké
  35,6499… et s'arrondirait à 35,6 au lieu de 35,7 (3 % d'écart sur la
  surface en `DOUBLE`, 0,014 % en `DECIMAL`).
- **Format** (décision) : silver reproduit le format de l'API, pour que les
  DPE de l'historique et ceux de l'ingestion hebdomadaire soient homogènes.
  Bronze conserve la pleine précision de la base complète.

## Champs

Concordance mesurée sur 1 247 235 DPE présents à la fois dans silver (API) et
dans la base complète.

| Champ silver | Source | Règle | Concordance | Dictionnaire ADEME |
|---|---|---|---|---|
| `numero_dpe` | `dpe.identifiant_dpe` | | clé | confirmé |
| `date_etablissement_dpe` | `dpe.date_etablissement_dpe` | date à l'heure de Paris | 100 % | absent |
| `date_reception_dpe` | `dpe.date_reception_dpe` | date à l'heure de Paris | 100 % | confirmé |
| `date_derniere_modification_dpe` | `dpe.date_derniere_modification` | date à l'heure de Paris | 97,93 % (100 % hors DPE modifiés) | confirmé |
| `etiquette_dpe` | `dpe_ep_conso.classe_bilan_dpe` | | 100 % | confirmé |
| `etiquette_ges` | `dpe_emission_ges.classe_emission_ges` | | 100 % | confirmé |
| `conso_5_usages_ep` | `dpe_ep_conso.ep_conso_5_usages` | arrondi au dixième, en `DECIMAL` | 99,999 % | confirmé (champ nommé `conso_ep_5_usages`) |
| `conso_5_usages_par_m2_ep` | `dpe_ep_conso.ep_conso_5_usages_m2` | **tronqué** au dixième, en `DECIMAL` | 99,995 % | confirmé (champ nommé `conso_ep_5_usages_par_m2`) |
| `type_batiment` | référentiel des méthodes d'application | `type_batiment` | 100 % | confirmé |
| `periode_construction` | référentiel des périodes | `lib` | 100 % | confirmé |
| `annee_construction` | `dpe_caracteristique_generale.annee_construction` | | 99,98 % | confirmé |
| `surface_habitable_logement` | `dpe_caracteristique_generale.surface_habitable_logement` | arrondi au dixième, en `DECIMAL` | 99,99 % | confirmé |
| `adresse_brut` | `dpe_t_adresse.adresse_brut` | espaces de début et de fin supprimés | 99,88 % | **contredit** : le dictionnaire indique `label_brut` (0,01 % mesuré) |
| `nom_commune_brut` | `dpe_t_adresse.nom_commune_brut` | espaces de début et de fin supprimés | 99,999 % | confirmé |
| `code_postal_brut` | `dpe_t_adresse.code_postal_brut` | complété à 5 chiffres | 99,95 % | confirmé |
| `identifiant_ban` | `dpe_t_adresse.ban_id` | | 99,99 % | confirmé |
| `score_ban` | `dpe_t_adresse.ban_score` | arrondi au centième | 99,97 % | confirmé |
| `statut_geocodage` | référentiel des statuts | `lib` | 100 % | confirmé |
| `code_postal_ban` | `dpe_t_adresse.ban_postcode` | | 99,99 % | confirmé |
| `code_insee_ban` | `dpe_t_adresse.ban_citycode` | | 99,99 % | confirmé |
| `code_departement_ban` | `dpe_t_adresse.ban_departement` | | 99,98 % | confirmé |
| `code_region_ban` | `dpe_t_adresse.ban_region` | | 99,98 % | confirmé |
| `coordonnee_cartographique_x_ban` | `dpe_t_adresse.ban_x` | | 99,99 % | confirmé |
| `coordonnee_cartographique_y_ban` | `dpe_t_adresse.ban_y` | | 99,99 % | confirmé |

Comparaison avec le dictionnaire de données des jeux de données publié par
l'ADEME : 22 correspondances sur 24 sont confirmées. Le dictionnaire décrit
une version antérieure des jeux de données : certains champs y portent un
autre nom, et la correspondance de l'adresse est contredite par la mesure
(`label_brut` contient l'adresse suivie du code postal et de la commune, ce que
l'API n'affiche pas). Il ne documente ni le fuseau horaire des dates, ni les
arrondis, ni la troncature de la consommation au m² : ces règles viennent
uniquement de la mesure.

Les colonnes dérivées de silver (`code_departement`, `source_departement`) et
la validation du modèle `DPE` s'appliquent aux DPE de l'historique comme à
ceux de l'API.

Candidats écartés : `ancienne_classe_bilan_dpe`, `nouvelle_classe_energie_dpe`
et `nouvelle_classe_bilan_dpe_pef` (0 % : vides pour ces DPE),
`ban_id_ban_adresse` (10 %), `dpe_administratif.date_derniere_modification`
(légèrement moins concordante), `label_brut` et
`label_brut_avec_complement` (adresse suivie du code postal et de la commune).

## Écarts résiduels

| Cause | Champs | Ordre de grandeur |
|---|---|---|
| DPE modifiés depuis leur ingestion par l'API | date de modification et autres champs | ~2 % des DPE |
| adresses regéocodées depuis l'ingestion | score BAN | 256 DPE |
| nettoyage des validateurs silver (années impossibles, codes postaux aberrants) | année de construction, code postal | 0,02 à 0,05 % |
| non expliqué à ce stade | adresse brute | 0,12 % |

## Constats pour l'architecture

- **12 188 DPE de silver (0,97 %) ne sont plus actifs** dans la base
  complète : très probablement désactivés ou remplacés après leur ingestion.
  L'ingestion par l'API ne voit pas ces suppressions (à vérifier
  précisément).
- **Environ 2 % des DPE ont été modifiés** après leur ingestion : la fenêtre
  sur la date de réception ne capte pas ces corrections.
- La base complète est une photographie hebdomadaire de l'ensemble des DPE :
  la comparaison de deux photographies successives permettrait de capter
  ajouts, modifications et suppressions. À décider dans l'ADR-0005.

## Reproduire les mesures

## Reproduire les mesures

Scripts dans `scripts/base_complete/`, à lancer depuis la racine du projet ;
ils lisent la base locale et le silver synchronisé dans `data/` (non
versionné) :

- `validation.py` : reconstruit les DPE de silver depuis la base complète, et
  calcule la concordance de chaque champ ;
- `diagnostic.py` : distribution des écarts et exemples ;
- `regles.py` : vérification des règles d'arrondi et de format.

Dictionnaires de données de l'ADEME (jeux de données, base complète,
référentiels, tables de valeurs) : publiés avec les jeux de données DPE sur
data.ademe.fr.
