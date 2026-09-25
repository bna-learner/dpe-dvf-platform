"""Exceptions levées par le client de l'API ADEME."""


class AdemeApiError(Exception):
    """Erreur de base pour tout échec d'appel à l'API ADEME."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TransientAdemeError(AdemeApiError):
    """Erreur temporaire (surcharge, panne passagère, réseau) : l'appel peut être retenté."""


class RateLimitError(TransientAdemeError):
    """L'API a refusé l'appel pour dépassement des limites de débit (HTTP 429)."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class UnexpectedResponseError(AdemeApiError):
    """La réponse n'est pas du JSON exploitable (page HTML, JSON invalide, structure inattendue)."""
