# ADR-0004 : Stratégie d'ingestion des DPE

## Statut
Partiellement remplacé par l'ADR-0005

## Date
2026-11-19

## Contexte
La plateforme doit collecter régulièrement les DPE publiés par l'ADEME, sans en
perdre, à partir de deux jeux de données : `dpe03existant` (logements existants,
plus de 15 millions de lignes) et `dpe02neuf` (logements neufs, plus de
1,4 million).

Contraintes mesurées :
- **Débit de l'API** : environ 500 ko/s en accès anonyme, pour environ 6 ko par
  DPE en JSON. La compression ne réduit pas la durée des requêtes. Débit réel de
  l'ingestion : environ 300 000 DPE par heure.
- **Chargement complet impossible par l'API** : plusieurs jours pour les DPE
  existants, alors qu'un job GitHub Actions est limité à 6 heures.
- **Dump de l'ADEME** : 74 Go compressés, téléchargés à environ 23 Mo/s, soit
  environ une heure.
- **Volume hebdomadaire** : de l'ordre de 60 000 nouveaux DPE.
- **Aucun moyen de demander « ce qui est nouveau »** : l'API n'expose ni
  horodatage de publication par ligne, ni identifiant croissant, ni journal des
  changements. Le journal du jeu de données est réservé à ses gestionnaires
  (erreur 403). Seules les métadonnées du jeu de données indiquent la date de la
  dernière publication (`finalizedAt`).
- **Publication par lots, avec retard** : un DPE n'apparaît dans l'API que
  plusieurs jours après sa réception. Sur 405 141 DPE découverts par les
  exécutions hebdomadaires (du 6 octobre au 16 novembre 2026), le retard entre
  réception et première ingestion a une médiane de 11 jours, un 90ᵉ centile de
  14 jours, un 99ᵉ centile de 17 jours ; seuls 68 DPE dépassent 17 jours, et un
  seul dépasse 21 jours (31 jours, un DPE corrigé après sa réception).

## Décision
1. **L'API pour l'ingestion incrémentale, le dump pour l'historique** : l'API
   alimente l'ingestion hebdomadaire ; le chargement historique se fera à partir
   du dump (V2).
2. **Une fenêtre glissante de 35 jours sur `date_reception_dpe`** : chaque
   exécution relit les DPE reçus au cours des 35 derniers jours, découpés en
   lots mensuels, par pages de 1 000 lignes (une requête en échec ne fait relire
   qu'une page).
3. **Une exécution hebdomadaire**, le lundi à 4 h 17 UTC (hors de l'heure pile,
   où GitHub retarde ou abandonne les exécutions planifiées), sans annulation
   d'une exécution en cours. Un lancement manuel permet de choisir la fenêtre,
   pour un backfill ou un rattrapage.
4. **Bronze immuable, dédoublonnage en aval** : chaque exécution écrit de
   nouveaux lots ; les DPE relus plusieurs fois sont dédoublonnés par
   `numero_dpe` dans la vue `silver_dpe_courant`, qui retient la version la plus
   récemment modifiée, puis la plus récemment ingérée.
5. **Des contrôles à chaque exécution** : complétude de chaque lot (lignes lues
   égales au total annoncé), retard de publication
   (`controle_retard_publication.sql`) et fraîcheur (`controle_fraicheur.sql`).

## Alternatives considérées
- **Charger l'ensemble par l'API** : écarté. Plusieurs jours de requêtes,
  au-delà de la limite de 6 heures d'un job.
- **Ingestion incrémentale par filigrane** (horodatage technique ou identifiant
  croissant) : impossible, la source n'expose aucun des deux.
- **Une fenêtre de 8 jours** : écarté après mesure. Elle aurait perdu
  silencieusement 47 858 DPE (environ 5 % de la base) en une seule semaine.
- **Une fenêtre de 21 jours** : écarté. Avec un retard maximal alors mesuré de
  18 jours, la marge n'était que de 3 jours.
- **Filtrer sur `date_derniere_modification_dpe`** : non retenu à ce stade. Il
  capterait aussi les corrections tardives, mais le taux de remplissage du champ
  n'est pas encore mesuré.
- **Déclencher l'ingestion à la publication** (lecture quotidienne de
  `finalizedAt`) : reporté après la V2. C'est une optimisation, pas une
  correction : la fenêtre actuelle couvre le retard observé.

## Conséquences

Positives :
- **Aucune perte mesurée** : la fenêtre couvre 99,98 % des DPE avec un retard
  inférieur à 17 jours, et le cas isolé de 31 jours.
- **Ingestion idempotente** : une exécution relancée réécrit les mêmes lots ;
  un rattrapage ne crée que des doublons, éliminés en aval.
- **Simplicité** : aucun état à conserver entre deux exécutions.

Négatives :
- **Redondance** : chaque DPE est relu environ cinq fois, pour environ une heure
  d'ingestion par semaine ; bronze grossit plus vite que la base réelle, pour un
  coût de quelques centimes par mois.
- **Mesure censurée** : les retards supérieurs à 35 jours ne peuvent pas être
  observés. Mitigation : un rattrapage manuel périodique, sur 90 jours, qui
  récupère et mesure les DPE hors fenêtre.
- **Corrections tardives non captées** : un DPE corrigé plus de 35 jours après sa
  réception n'est jamais relu, et la vue conserve son ancienne version. À
  mesurer, puis à traiter, par exemple avec un filtre sur la date de dernière
  modification.
- **Attente jusqu'au lundi** : un lot publié le mercredi attend plus de quatre
  jours avant d'être ingéré. Traité par le déclenchement à la publication, prévu
  après la V2.
- **Exécution planifiée non garantie** : GitHub peut retarder ou abandonner une
  exécution. Une exécution manquée est détectée par le contrôle de fraîcheur,
  et rattrapée par la fenêtre suivante.
