"""Beheer: accounts nakijken en rare namen opruimen.

Alleen met de docentcode (dezelfde als voor de klassikale quiz en
/statistieken). Wat je hier kunt:

- accounts zoeken op naam, nieuwste bovenaan;
- een naam veranderen, of met een klik een neutrale naam geven
  ("Speler 12"), als iemand toch iets raars heeft verzonnen;
- een account verwijderen;
- woorden aan het naamfilter toevoegen, voor wat er toch doorheen glipt.
  Ze gelden meteen, ook voor de naam waarmee iemand aan een quiz meedoet.

De statistieken (/statistieken) staan los van accounts: een account
verwijderen haalt daar niets weg.
"""
from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_

from .kahoot_routes import teacherRequired
from .models import DuelMatch, GeblokkeerdWoord, Results, User, db
from .names import NameError_, checkName, extraWoord, naamSleutel, normaalWoord, zetExtraWoorden
from .security import csrfValid

beheer = Blueprint('beheer', __name__)

PER_PAGINA = 50


def laadWoorden():
    """Zet de woorden uit de database in het naamfilter. Bij het opstarten
    en na elke wijziging hier."""
    try:
        zetExtraWoorden(w for (w,) in db.session.query(GeblokkeerdWoord.woord).all())
    except Exception:
        db.session.rollback()
        current_app.logger.warning('Geblokkeerde woorden niet geladen', exc_info=True)


def _log(tekst: str):
    current_app.logger.info('beheer: %s (vanaf %s)', tekst, request.remote_addr)


def _terug():
    return redirect(url_for('beheer.overzicht', zoek=request.form.get('zoek') or None))


def _naamFout(naam: str, voor: User) -> str | None:
    """Waarom deze naam niet kan voor dit account, of None als hij goed is."""
    try:
        checkName(naam)
    except NameError_ as e:
        return str(e)
    sleutel = naamSleutel(naam)
    for (andere_id, andere) in db.session.query(User.id, User.username).all():
        if andere_id == voor.id:
            continue
        if andere.lower() == naam.lower():
            return 'Die naam heeft iemand anders al.'
        if naamSleutel(andere) == sleutel:
            return f'Die naam lijkt te veel op die van {andere}.'
    return None


def _neutraleNaam(account: User) -> str:
    naam = f'Speler {account.id}'
    teller = 1
    while db.session.query(User.id).filter(func.lower(User.username) == naam.lower(),
                                           User.id != account.id).first():
        teller += 1
        naam = f'Speler {account.id}-{teller}'
    return naam


@beheer.route('/beheer')
@teacherRequired
def overzicht():
    zoek = ' '.join((request.args.get('zoek') or '').split())[:40]
    try:
        pagina = max(1, int(request.args.get('pagina', 1)))
    except ValueError:
        pagina = 1

    vraag = User.query
    if zoek:
        vraag = vraag.filter(func.lower(User.username).contains(zoek.lower()))
    totaal = vraag.count()
    accounts = (vraag.order_by(User.created_at.desc(), User.id.desc())
                .offset((pagina - 1) * PER_PAGINA).limit(PER_PAGINA).all())

    woorden = GeblokkeerdWoord.query.order_by(GeblokkeerdWoord.woord).all()
    # Wie heeft nu een naam met een van die woorden? Die zie je dan meteen.
    verdacht = {a.id: extraWoord(a.username) for a in accounts}

    return render_template('beheer.html', accounts=accounts, zoek=zoek, pagina=pagina,
                           paginas=max(1, -(-totaal // PER_PAGINA)), totaal=totaal,
                           alleAccounts=User.query.count(), woorden=woorden,
                           verdacht=verdacht)


@beheer.route('/beheer/account/<int:accountId>/naam', methods=['POST'])
@teacherRequired
def hernoem(accountId):
    if not csrfValid():
        flash('Het formulier is verlopen. Probeer het opnieuw.', 'error')
        return _terug()
    account = db.session.get(User, accountId)
    if account is None:
        flash('Dat account bestaat niet meer.', 'error')
        return _terug()

    oud = account.username
    if request.form.get('neutraal'):
        nieuw = _neutraleNaam(account)
    else:
        nieuw = ' '.join((request.form.get('naam') or '').split())
        fout = _naamFout(nieuw, account)
        if fout:
            flash(f'"{nieuw}" kan niet: {fout}', 'error')
            return _terug()

    account.username = nieuw
    db.session.commit()
    _log(f'naam {oud!r} -> {nieuw!r} (account {account.id})')
    flash(f'"{oud}" heet nu "{nieuw}".', 'success')
    return _terug()


@beheer.route('/beheer/account/<int:accountId>/verwijderen', methods=['POST'])
@teacherRequired
def verwijder(accountId):
    if not csrfValid():
        flash('Het formulier is verlopen. Probeer het opnieuw.', 'error')
        return _terug()
    account = db.session.get(User, accountId)
    if account is None:
        flash('Dat account bestaat niet meer.', 'error')
        return _terug()
    if request.form.get('zeker') != 'ja':
        flash(f'Vink "zeker weten" aan om {account.username} te verwijderen.', 'error')
        return _terug()

    naam = account.username
    verwijderAccount(account)
    _log(f'account {naam!r} verwijderd')
    flash(f'Het account "{naam}" is verwijderd.', 'success')
    return _terug()


def verwijderAccount(account: User):
    """Haal een account weg, met alles wat er alleen voor dit account is.

    Ook gebruikt als iemand zijn eigen account verwijdert (auth.py). De
    gespeelde duels gaan mee, want die verwijzen naar dit account; de elo en
    de gewonnen/verloren duels van de tegenstander blijven wat ze waren. De
    statistieken staan los van accounts en blijven helemaal staan.
    """
    from .duel_routes import duelManager

    for duel in list(duelManager.duels.values()):
        if duel.playerFor(account.id) is not None:
            duelManager.remove(duel.code)

    DuelMatch.query.filter(or_(DuelMatch.one_id == account.id,
                               DuelMatch.two_id == account.id)).delete(synchronize_session=False)
    Results.query.filter_by(creator_id=account.id).delete(synchronize_session=False)
    db.session.delete(account)
    db.session.commit()


@beheer.route('/beheer/woord', methods=['POST'])
@teacherRequired
def woordErbij():
    if not csrfValid():
        flash('Het formulier is verlopen. Probeer het opnieuw.', 'error')
        return _terug()
    getypt = (request.form.get('woord') or '').strip()
    woord = normaalWoord(getypt)
    if len(woord) < 3:
        # Twee letters zitten in veel te veel gewone namen.
        flash('Een woord moet minstens drie letters hebben.', 'error')
        return _terug()
    if len(woord) > 40:
        flash('Dat woord is te lang.', 'error')
        return _terug()
    if GeblokkeerdWoord.query.filter_by(woord=woord).first():
        flash(f'"{woord}" stond er al op.', 'error')
        return _terug()

    db.session.add(GeblokkeerdWoord(woord=woord))
    db.session.commit()
    laadWoorden()
    _log(f'woord {woord!r} geblokkeerd')

    geraakt = [a.username for a in User.query.all() if extraWoord(a.username) == woord]
    if geraakt:
        flash(f'"{woord}" is geblokkeerd. Deze accounts hebben het al in hun naam: '
              + ', '.join(geraakt[:10]) + (' en meer' if len(geraakt) > 10 else '')
              + '. Geef ze hieronder een andere naam.', 'success')
    else:
        flash(f'"{woord}" is geblokkeerd. Geen enkel account heeft het nu in zijn naam.', 'success')
    return _terug()


@beheer.route('/beheer/woord/<int:woordId>/weg', methods=['POST'])
@teacherRequired
def woordWeg(woordId):
    if not csrfValid():
        flash('Het formulier is verlopen. Probeer het opnieuw.', 'error')
        return _terug()
    woord = db.session.get(GeblokkeerdWoord, woordId)
    if woord is not None:
        db.session.delete(woord)
        db.session.commit()
        laadWoorden()
        _log(f'woord {woord.woord!r} weer toegestaan')
        flash(f'"{woord.woord}" mag weer.', 'success')
    return _terug()
