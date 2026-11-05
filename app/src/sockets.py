"""Een plek voor socket-dingen die meer dan een module aangaan.

Flask-SocketIO houdt per event maar een handler bij: wie 'disconnect' als
tweede registreert, gooit de eerste eruit. De klassikale quiz en de duels
willen er allebei iets mee, dus melden ze zich hier aan en roept __init__.py
ze allebei aan.
"""
from __future__ import annotations

_disconnectHandlers: list = []


def registerDisconnect(func):
    """Gebruik als decorator: de functie krijgt de sid van de weggevallen verbinding."""
    if func not in _disconnectHandlers:
        _disconnectHandlers.append(func)
    return func


def dispatchDisconnect(sid):
    for handler in list(_disconnectHandlers):
        handler(sid)
