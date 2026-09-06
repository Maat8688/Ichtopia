"""Kleine beveiligingshulpjes: CSRF-tokens, een rem op gokken en veilige redirects.

Bewust zonder extra afhankelijkheden: de app draait op een enkele server en
heeft geen volledige formulierbibliotheek nodig.
"""
from __future__ import annotations

import secrets
import threading
import time
from urllib.parse import urlparse

from flask import request, session

CSRF_SESSION_KEY = 'csrfToken'


# ----------------------------------------------------------------------
# CSRF
# ----------------------------------------------------------------------
def csrfToken() -> str:
    """Token voor deze browsersessie. Wordt eenmalig aangemaakt en hergebruikt."""
    token = session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def csrfValid() -> bool:
    """Hoort het verstuurde formulier bij deze sessie?"""
    stored = session.get(CSRF_SESSION_KEY)
    sent = request.form.get('csrfToken', '')
    if not isinstance(stored, str) or not stored or not sent:
        return False
    return secrets.compare_digest(stored, sent)


def rotateCsrfToken():
    """Na in- of uitloggen een nieuw token, zodat een oud formulier niet blijft werken."""
    session.pop(CSRF_SESSION_KEY, None)


# ----------------------------------------------------------------------
# Rem op gokken
# ----------------------------------------------------------------------
class AttemptLimiter:
    """Telt mislukte pogingen per sleutel (meestal een IP-adres).

    Na `maxAttempts` mislukkingen binnen `window` seconden is de sleutel
    geblokkeerd tot het venster voorbij is. Alles staat in het geheugen van
    dit proces; bij een herstart is de teller leeg. Dat is genoeg om
    wachtwoorden raden af te remmen.
    """

    def __init__(self, maxAttempts: int, window: int):
        self.maxAttempts = maxAttempts
        self.window = window
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        attempts = [t for t in self._attempts.get(key, []) if now - t < self.window]
        if attempts:
            self._attempts[key] = attempts
        else:
            self._attempts.pop(key, None)
        return attempts

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key, time.time())) >= self.maxAttempts

    def registerFailure(self, key: str):
        with self._lock:
            now = time.time()
            attempts = self._recent(key, now)
            attempts.append(now)
            self._attempts[key] = attempts

    def reset(self, key: str):
        with self._lock:
            self._attempts.pop(key, None)


def clientIp() -> str:
    # Bewust geen X-Forwarded-For: die header kan een bezoeker zelf verzinnen
    # om de rem te omzeilen. De app draait zonder proxy ervoor.
    return request.remote_addr or 'unknown'


# ----------------------------------------------------------------------
# Redirects
# ----------------------------------------------------------------------
def safeUrl(target: str | None, fallback: str) -> str:
    """Alleen doorsturen naar een pad binnen deze site, nooit naar een ander domein."""
    if not target:
        return fallback
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return fallback
    if not target.startswith('/') or target.startswith('//'):
        return fallback
    return target
