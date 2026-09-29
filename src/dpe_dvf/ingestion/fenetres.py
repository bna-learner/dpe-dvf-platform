"""Fenêtres temporelles d'ingestion, en intervalles semi-ouverts [début, fin)."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Fenetre:
    """Intervalle de dates semi-ouvert : `debut` inclus, `fin` exclue."""

    debut: date
    fin: date

    def __post_init__(self) -> None:
        if self.debut >= self.fin:
            raise ValueError(f"Fenêtre vide ou inversée : {self.debut} → {self.fin}")

    def en_params(self, champ: str) -> dict[str, str | int]:
        """Traduit la fenêtre en filtres de l'API Data Fair sur le champ donné."""
        return {
            f"{champ}_gte": self.debut.isoformat(),
            f"{champ}_lt": self.fin.isoformat(),
        }


def _premier_du_mois_suivant(jour: date) -> date:
    if jour.month == 12:
        return date(jour.year + 1, 1, 1)
    return date(jour.year, jour.month + 1, 1)


def decouper_par_mois(fenetre: Fenetre) -> Iterator[Fenetre]:
    """Découpe une fenêtre en sous-fenêtres d'au plus un mois calendaire."""
    debut = fenetre.debut
    while debut < fenetre.fin:
        fin = min(_premier_du_mois_suivant(debut), fenetre.fin)
        yield Fenetre(debut, fin)
        debut = fin
