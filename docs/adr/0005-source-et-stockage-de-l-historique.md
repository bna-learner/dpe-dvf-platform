# ADR-0005 : Source et stockage de l'historique des DPE

## Statut
Accepté. Remplace la décision 1 de l'ADR-0004 (dump PostgreSQL pour
l'historique).

## Date
2026-11-23

## Contexte
La V2 a besoin de l'historique complet des DPE (environ 17,5 millions de DPE
actifs depuis 2021), en particulier pour le rapprochement avec les ventes
immobilières (DVF). L'ADR-0004 prévoyait de le charger depuis le dump
PostgreSQL de l'ADEME.

Constats et mesures (novembre 2026) :
- **Dump PostgreSQL** : 71,5 Go, à restaurer dans PostgreSQL (Docker). Sa
  restauration complète échouerait sur l'extension d'anonymisation `anon`,
  absente des images officielles.
- **Base complète en Parquet** : l'ADEME publie chaque semaine la même base,
  en fichiers Parquet interrogeables avec DuckDB sans téléchargement préalable.
  Même modèle normalisé que le dump (175 vues : 45 tables, 130 référentiels).
- **Reconstruction validée** : sur 1 247 235 DPE communs avec silver, tous les
  champs reconstruits concordent avec l'API à plus de 99,88 %
  ([correspondance](../correspondance-base-complete.md)).
- **Angles morts de l'ingestion par l'API** : 12 188 DPE de silver (0,97 %) ne
  sont plus actifs ; environ 2 % ont été modifiés depuis leur ingestion ;
  2 044 384 DPE de logement ont été remplacés (99,4 % des désactivations).
  L'ingestion par fenêtre glissante ne voit ni les modifications tardives, ni
  les désactivations.
- **Volume** : les dix tables nécessaires pèsent 11,03 Go ; leurs seules
  colonnes utiles, 4,26 Go, dont une grande part de clés UUID, incompressibles.
- **Mémoire** : une extraction en une seule requête (sept jointures sur
  20 millions de lignes) dépasse 24,8 Go et échoue.
- **Partitionnement de la source** : chaque table est répartie en seize
  fichiers (`part-0` à `part-f`) selon le premier caractère de l'identifiant du
  DPE ; toutes les tables rattachées au DPE sont co-partitionnées, sauf les
  adresses, réparties selon leur propre identifiant.
- **Contraintes** : coût quasi nul ; exécution possible dans GitHub Actions
  (mémoire limitée, 6 heures maximum par job).

## Décision
1. **La base complète en Parquet devient la source principale** de la
   plateforme, pour l'historique comme pour les mises à jour hebdomadaires.
   L'ingestion par l'API est maintenue pendant la transition, comme contrôle,
   puis arrêtée une fois la nouvelle chaîne validée sur plusieurs semaines.
2. **Une photographie hebdomadaire** (instantané) : une ligne par DPE de
   logement (modèles 1, 2 et 3), **y compris les DPE désactivés**, avec leur
   statut et le numéro de leur remplaçant. Valeurs brutes, sans arrondi ni
   conversion de date ; seules des jointures structurelles et la traduction des
   référentiels sont appliquées.
3. **Une extraction en deux étapes**, pour tenir en mémoire :
   - étape A : jointure fichier par fichier des tables co-partitionnées par
     identifiant de DPE ;
   - étape B : redistribution par identifiant d'adresse, puis jointure fichier
     par fichier avec les adresses.
4. **Bronze conserve les changements, pas les photographies** :
   - chaque photographie est comparée à la précédente sur `numero_dpe`, avec
     une empreinte de ligne ; seuls les DPE ajoutés, modifiés ou disparus sont
     écrits, et conservés sans limite de durée ;
   - la photographie la plus récente est conservée pour la comparaison
     suivante ; les plus anciennes expirent automatiquement après cinq semaines
     (règle de cycle de vie S3) ;
   - la première photographie constitue le chargement initial : tous ses DPE
     sont des ajouts.
5. **Silver applique les règles de la correspondance** : périmètre de l'API
   (DPE non désactivés, non supprimés), dates à l'heure de Paris, arrondis de
   l'API calculés en `DECIMAL`, validation par le modèle `DPE`. L'historique
   des versions de chaque DPE (dimension à évolution lente de type 2) est
   construit à partir des changements.
6. **Des contrôles à chaque extraction** : seize fichiers par table, une ligne
   par DPE, aucun DPE actif incomplet, cohérence des volumes avec la
   photographie précédente.

## Alternatives considérées
- **Continuer avec l'API** : écarté. Trop lente pour l'historique (plusieurs
  jours), et aveugle aux modifications tardives et aux désactivations.
- **Le dump PostgreSQL** : écarté. 71,5 Go à télécharger et à restaurer, une
  extension d'anonymisation à contourner, pour les mêmes données que la base en
  Parquet.
- **Photographier les tables complètes** : écarté. 11 Go par semaine, dont une
  majorité de colonnes inutilisées et de clés UUID.
- **Une extraction en une seule requête** : écarté. Plus de 24,8 Go de mémoire.
- **Conserver toutes les photographies** : écarté. Environ 86 Go par an, pour
  un coût en hausse continue ; l'historique est conservé à moindre coût par les
  changements.
- **Ne conserver que les dernières photographies** : écarté. L'historique des
  versions serait perdu au-delà de la période de rétention.
- **Spark ou Databricks** : non retenu à ce stade. L'extraction prend environ
  deux minutes avec DuckDB sur une seule machine ; un moteur distribué
  ajouterait un coût et une complexité sans gain mesurable.

## Conséquences

Positives :
- **Les trois angles morts de la V1 sont traités** : DPE publiés tardivement,
  corrections tardives et remplacements apparaissent dans la comparaison de
  deux photographies.
- **L'historique complet**, depuis 2021, est disponible.
- **Rapide et économe** : extraction en 2 minutes 6 secondes, sous 8 Go de
  mémoire, pour une photographie de 1,65 Go ; bronze ne grossit que des
  changements de la semaine.
- **Sans PostgreSQL ni Docker** : DuckDB lit directement les fichiers de
  l'ADEME.

Négatives :
- **Dépendance à un format non documenté** : le découpage en seize fichiers
  co-partitionnés et les règles de reconstruction ne sont décrits nulle part.
  Mitigations : l'extraction s'arrête si une table n'a pas exactement seize
  fichiers, les contrôles détectent un DPE actif incomplet, et la
  reconstruction est comparée périodiquement à l'API.
- **Seules les colonnes extraites sont suivies** : une correction sur une
  colonne non photographiée n'est pas détectée.
- **Granularité hebdomadaire** : deux modifications d'un même DPE dans la
  semaine n'apparaissent que comme une seule.
- **Complexité accrue** : la comparaison de photographies et l'historique des
  versions demandent du code et des tests supplémentaires.
- **Cinq semaines pour rattraper une erreur** : au-delà, une photographie
  incorrecte ne peut plus être recalculée depuis bronze ; seuls les changements
  qu'elle a produits subsistent.
