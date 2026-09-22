# ADR (Architecture Decision Records)

## Rôle
Un ADR sert à tracer une décision. L'ensemble de tous les ADR du projet permet de constituer le journal de décision du projet.

## Principe de l'ADR
Un ADR accepté ne se modifie pas. Si la décision change, on écrit un nouvel ADR et l'ancien passe au statut remplacé par ADR-NNNN.
Les statuts possibles: Proposé, Accepté, Déprécié, Remplacé par ADR-NNNN

## Trame utilisée
- Titre (`# ADR-NNNN: Titre de la décision`)
- Statut
- Date
- Contexte
- Décision
- Alternatives considérées
- Conséquences

## Quand écrire un ADR
- La décision est structurante : elle impacte plusieurs parties du projet ;
- Elle est coûteuse à défaire ;
- Plusieurs options crédibles ont été comparées ;
- Quelqu'un pourrait plus tard se demander « pourquoi on a fait ça ? »

## Convention de nommage
`NNNN-titre-en-kebab-case.md` où `NNNN`est un numéro incrémentiel sur 4 chiffres (0001, 0002, 0003,...)

## Index ADR
| N° | Titre | Statut |
|---|---|---|
| [0001](0001-structure-du-projet.md) | Structure du projet et outillage Python | Accepté |
