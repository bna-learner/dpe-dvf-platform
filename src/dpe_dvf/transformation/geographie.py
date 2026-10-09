"""Règles géographiques : rattachement d'un code postal à son département."""


def departement_depuis_code_postal(code_postal: str | None) -> str | None:
    """Déduit le département d'un code postal à 5 chiffres.

    Approximation : quelques communes ont un code postal rattaché au département
    voisin. Corse : 200xx-201xx pour la Corse-du-Sud (2A), 202xx et au-delà pour la
    Haute-Corse (2B). Outre-mer : le département se lit sur trois chiffres (971…976).
    """
    if code_postal is None or len(code_postal) != 5 or not code_postal.isdigit():
        return None
    if code_postal.startswith(("00", "98", "99")):
        return None  # préfixes sans département métropolitain ou d'outre-mer
    if code_postal.startswith("20"):
        return "2A" if int(code_postal) < 20200 else "2B"
    if code_postal.startswith("97"):
        return code_postal[:3]
    return code_postal[:2]
