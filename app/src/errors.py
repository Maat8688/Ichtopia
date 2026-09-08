"""Nette foutpagina's in plaats van de kale meldingen van Flask."""
from __future__ import annotations

from flask import render_template, request
from werkzeug.exceptions import HTTPException

# Teksten per foutcode. Alles wat hier niet in staat valt terug op DEFAULT.
MESSAGES = {
    404: (
        'Deze pagina bestaat niet',
        'Misschien klopt de link niet meer, of is de quiz waar je naartoe wilde afgelopen.',
    ),
    403: (
        'Geen toegang',
        'Je mag deze pagina niet bekijken. Ben je docent? Log dan eerst in met de docentcode.',
    ),
    405: (
        'Dat kan hier niet',
        'Deze pagina verwacht een andere actie. Ga terug en probeer het opnieuw.',
    ),
    500: (
        'Er ging iets mis',
        'De server liep vast. Probeer het straks nog eens, of ga terug naar de startpagina.',
    ),
}

DEFAULT = (
    'Er ging iets mis',
    'Probeer het opnieuw, of ga terug naar de startpagina.',
)


def errorPage(code: int):
    title, message = MESSAGES.get(code, DEFAULT)
    return render_template('error.html', code=code, title=title, message=message), code


def registerErrorHandlers(app):
    @app.errorhandler(HTTPException)
    def handleHttpError(error: HTTPException):
        # Socket.IO en andere API-achtige verzoeken hebben niets aan een HTML-pagina.
        if request.path.startswith('/socket.io'):
            return error
        return errorPage(error.code or 500)

    @app.errorhandler(Exception)
    def handleUnexpectedError(error: Exception):
        app.logger.exception('Onverwachte fout op %s', request.path)
        if app.debug:
            # In debug wil je de echte traceback van Flask zien.
            raise error
        return errorPage(500)
