"""Meldingen: bezoekers zeggen wat er niet klopt, wij lezen het op /beheer.

Twee manieren om iets te melden:

- tijdens het oefenen het knopje "Klopt dit niet?" onder de uitleg na een
  antwoord, en in de uitslag van een toets bij elke fout. De melding weet
  dan zelf om welke kaart en vraag het ging en wat de leerling antwoordde;
  de leerling kiest alleen nog een reden;
- het linkje "Iets kapot of een idee?" onderaan elke pagina, met een kort
  formulier.

Er wordt geen naam, account of IP-adres bij een melding bewaard. Tegen
volspammen zit er een rem per IP-adres op (alleen in het geheugen), een
maximale lengte, en per oefensessie kan elke vraag maar een keer gemeld
worden.
"""
from __future__ import annotations

import re

from flask import (Blueprint, current_app, flash, jsonify, redirect, render_template,
                   request, url_for)

from .kahoot_routes import teacherRequired
from .models import Melding, db
from .security import AttemptLimiter, clientIp, csrfValid

meldingen = Blueprint('meldingen', __name__)

MAX_TEKST = 500
SOORTEN = ('kaart', 'kapot', 'idee')
REDENEN = {
    'antwoord': 'mijn antwoord werd fout gerekend',
    'plek': 'de plek of de grens klopt niet',
    'spelling': 'spelfout in de naam',
    'anders': 'iets anders',
}
SOORT_NAMEN = {'kaart': 'Kaart klopt niet', 'kapot': 'Iets werkt niet', 'idee': 'Idee'}

# Ruim genoeg voor een klas achter een IP-adres die allemaal iets meldt, te
# weinig om de lijst vol te spammen.
meldLimiter = AttemptLimiter(maxAttempts=30, window=10 * 60)


def _schoon(tekst, lengte: int) -> str:
    """Zonder onzichtbare tekens, witruimte samengevoegd, hooguit `lengte` tekens."""
    tekst = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', str(tekst or ''))
    tekst = re.sub(r'[ \t]+', ' ', tekst)
    tekst = re.sub(r'\n{3,}', '\n\n', tekst).strip()
    return tekst[:lengte]


def _pagina(pad) -> str | None:
    """Alleen het pad, zonder ?-deel: daarin kan een sessietoken staan."""
    pad = str(pad or '').split('?', 1)[0].split('#', 1)[0]
    if not pad.startswith('/') or pad.startswith('//'):
        return None
    return pad[:80]


def _wilJson() -> bool:
    return request.headers.get('X-Requested-With') == 'fetch'


def _antwoord(ok: bool, bericht: str, status: int = 200):
    """JSON voor het knopje tijdens het oefenen, anders terug naar het formulier."""
    if _wilJson():
        return jsonify({'ok': ok, 'bericht': bericht}), status
    flash(bericht, 'success' if ok else 'error')
    if ok:
        return redirect(url_for('meldingen.bedankt'))
    return redirect(url_for('meldingen.formulier', van=request.form.get('pagina') or None))


def _kaartGegevens(sessionToken, vraagNaam):
    """Kaart, vraag en antwoord uit de oefensessie zelf, niet uit de browser.

    Zonder vraagnaam: de laatst beantwoorde vraag. Met vraagnaam (bij de
    uitslag van een toets): alleen als die vraag echt in deze toets zat.
    """
    from . import sessionManager
    sessie = sessionManager.findSession(sessionToken)
    if sessie is None:
        return None, 'Deze oefening is verlopen; begin een nieuwe en meld het dan.'
    if vraagNaam:
        antwoorden = {a['vraag']: a['gegeven'] for a in getattr(sessie, 'toetsAntwoorden', [])}
        if vraagNaam not in antwoorden:
            return None, 'Die vraag zat niet in deze toets.'
        return {'sessie': sessie, 'kaart': sessie.mapName, 'vraag': vraagNaam,
                'antwoord': antwoorden[vraagNaam]}, None
    vorige = getattr(sessie, 'vorigeVraag', None)
    if not vorige:
        return None, 'Beantwoord eerst een vraag.'
    return {'sessie': sessie, 'kaart': sessie.mapName, 'vraag': vorige['vraag'],
            'antwoord': vorige['gegeven']}, None


@meldingen.route('/melden', methods=['GET'])
def formulier():
    return render_template('melden.html', van=_pagina(request.args.get('van')) or '')


@meldingen.route('/melden/bedankt')
def bedankt():
    return render_template('melden.html', bedankt=True, van='')


@meldingen.route('/melden', methods=['POST'])
def melden():
    if not csrfValid():
        return _antwoord(False, 'Het formulier is verlopen. Laad de pagina opnieuw.', 400)
    ip = clientIp()
    if meldLimiter.blocked(ip):
        return _antwoord(False, 'Er zijn vanaf dit adres net heel veel meldingen gedaan. '
                                'Probeer het later nog eens.', 429)

    soort = request.form.get('soort')
    if soort not in SOORTEN:
        return _antwoord(False, 'Kies wat je wilt melden.', 400)
    tekst = _schoon(request.form.get('tekst'), MAX_TEKST)
    melding = Melding(soort=soort, tekst=tekst or None, pagina=_pagina(request.form.get('pagina')))

    if soort == 'kaart':
        reden = request.form.get('reden')
        if reden not in REDENEN:
            return _antwoord(False, 'Kies wat er niet klopt.', 400)
        gegevens, fout = _kaartGegevens(request.form.get('sessionToken'),
                                        _schoon(request.form.get('vraag'), 80))
        if fout:
            return _antwoord(False, fout, 400)
        # Een keer per vraag per oefensessie, ook als iemand blijft klikken.
        gemeld = gegevens['sessie'].__dict__.setdefault('gemeld', set())
        if gegevens['vraag'] in gemeld:
            return _antwoord(True, 'Deze vraag had je al gemeld. Bedankt!')
        gemeld.add(gegevens['vraag'])
        melding.reden = reden
        melding.kaart = (gegevens['kaart'] or '')[:40] or None
        melding.vraag = gegevens['vraag'][:80]
        melding.antwoord = (gegevens['antwoord'] or '')[:80] or None
    elif len(tekst) < 3:
        return _antwoord(False, 'Schrijf even op wat er is.', 400)

    meldLimiter.registerFailure(ip)
    db.session.add(melding)
    db.session.commit()
    return _antwoord(True, 'Bedankt! De makers lezen je melding.')


# ----------------------------------------------------------------------
# Lezen op /beheer/meldingen
# ----------------------------------------------------------------------
def openMeldingen() -> int:
    try:
        return Melding.query.filter_by(afgehandeld=False).count()
    except Exception:
        db.session.rollback()
        return 0


@meldingen.route('/beheer/meldingen')
@teacherRequired
def overzicht():
    toon = request.args.get('toon', 'open')
    if toon not in ('open', 'afgehandeld', 'alles'):
        toon = 'open'
    vraag = Melding.query
    if toon == 'open':
        vraag = vraag.filter_by(afgehandeld=False)
    elif toon == 'afgehandeld':
        vraag = vraag.filter_by(afgehandeld=True)
    lijst = vraag.order_by(Melding.tijd.desc(), Melding.id.desc()).limit(300).all()

    # Open kaartmeldingen per vraag opgeteld: wat vaak gemeld wordt, staat bovenaan.
    groepen = {}
    for m in Melding.query.filter_by(afgehandeld=False, soort='kaart').all():
        g = groepen.setdefault((m.kaart, m.vraag), {'kaart': m.kaart, 'vraag': m.vraag,
                                                     'aantal': 0, 'redenen': {}, 'antwoorden': {}})
        g['aantal'] += 1
        g['redenen'][m.reden] = g['redenen'].get(m.reden, 0) + 1
        if m.antwoord:
            g['antwoorden'][m.antwoord] = g['antwoorden'].get(m.antwoord, 0) + 1
    groepen = sorted(groepen.values(), key=lambda g: (-g['aantal'], g['kaart'] or '', g['vraag'] or ''))

    return render_template('beheer_meldingen.html', lijst=lijst, toon=toon, groepen=groepen,
                           redenen=REDENEN, soortNamen=SOORT_NAMEN,
                           aantallen={'open': Melding.query.filter_by(afgehandeld=False).count(),
                                      'afgehandeld': Melding.query.filter_by(afgehandeld=True).count()})


def _terugNaarLijst():
    return redirect(url_for('meldingen.overzicht', toon=request.form.get('toon') or None))


@meldingen.route('/beheer/melding/<int:meldingId>/afgehandeld', methods=['POST'])
@teacherRequired
def afhandelen(meldingId):
    if not csrfValid():
        flash('Het formulier is verlopen. Probeer het opnieuw.', 'error')
        return _terugNaarLijst()
    melding = db.session.get(Melding, meldingId)
    if melding is not None:
        melding.afgehandeld = not melding.afgehandeld
        db.session.commit()
    return _terugNaarLijst()


@meldingen.route('/beheer/meldingen/vraag-afgehandeld', methods=['POST'])
@teacherRequired
def vraagAfhandelen():
    """Alle open meldingen over dezelfde vraag in een keer afhandelen."""
    if not csrfValid():
        flash('Het formulier is verlopen. Probeer het opnieuw.', 'error')
        return _terugNaarLijst()
    aantal = (Melding.query.filter_by(afgehandeld=False, soort='kaart',
                                      kaart=request.form.get('kaart') or None,
                                      vraag=request.form.get('vraag') or None)
              .update({'afgehandeld': True}, synchronize_session=False))
    db.session.commit()
    flash(f'{aantal} melding{"" if aantal == 1 else "en"} afgehandeld.', 'success')
    return _terugNaarLijst()


@meldingen.route('/beheer/melding/<int:meldingId>/verwijderen', methods=['POST'])
@teacherRequired
def verwijder(meldingId):
    if not csrfValid():
        flash('Het formulier is verlopen. Probeer het opnieuw.', 'error')
        return _terugNaarLijst()
    melding = db.session.get(Melding, meldingId)
    if melding is not None:
        db.session.delete(melding)
        db.session.commit()
        current_app.logger.info('beheer: melding %s verwijderd', meldingId)
        flash('De melding is verwijderd.', 'success')
    return _terugNaarLijst()
