"""Accounts: registreren, inloggen, uitloggen en de accountpagina.

Een account is nergens verplicht. Oefenen kan gewoon zonder inloggen; een
account voegt iets toe (XP, duels, de ranglijst).

Er is geen keuze tussen leerling en docent: iedereen krijgt hetzelfde soort
account. Een docent start een klassikale quiz met de docentcode op /host; zo
kan een leerling zichzelf nooit docentrechten geven. Oude docentaccounts
blijven gewoon werken.

Bewust zonder e-mailadres: we hebben er niets aan, de leerlingen ook niet, en
ouders en scholen willen liever dat er geen persoonsgegevens van kinderen
worden verzameld. Een account is dus alleen een naam en een wachtwoord. Wie
zijn wachtwoord vergeet, maakt een nieuw account.
"""
from __future__ import annotations

import re
import secrets

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .models import db, DuelMatch, User, AccountType
from .names import NameError_, checkName, naamSleutel
from .security import (AttemptLimiter, clientIp, csrfToken, csrfValid,
                       rotateCsrfToken, safeUrl)

auth = Blueprint('auth', __name__)

# Vijf misluke pogingen per IP, daarna vijf minuten wachten.
loginLimiter = AttemptLimiter(maxAttempts=5, window=5 * 60)
# Registreren mag hooguit vijf keer per uur per IP, tegen het volautomatisch
# aanmaken van accounts.
registerLimiter = AttemptLimiter(maxAttempts=5, window=60 * 60)

MIN_PASSWORD_LENGTH = 8

# Een echte hash van een willekeurig wachtwoord om tegenaan te rekenen als de
# naam niet bestaat. Zo duurt een inlogpoging even lang met en zonder
# bestaand account, en kun je via de reactietijd niet uitvissen wie er een
# account heeft.
DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(16))


@auth.app_context_processor
def injectAuthHelpers():
    """`csrfToken()` beschikbaar in elke template."""
    return {'csrfToken': csrfToken}


def zoekGebruiker(naam: str) -> User | None:
    """Het account bij deze naam. Hoofdletters maken niet uit."""
    naam = ' '.join((naam or '').split())
    if not naam:
        return None
    return User.query.filter(func.lower(User.username) == naam.lower()).first()


def lijktOpBestaandeNaam(naam: str) -> bool:
    """Lijkt de naam te veel op een bestaande? Floris, F1oris, FIoris en
    Flor1s zijn voor wie op de ranglijst kijkt dezelfde persoon. Zo kan
    niemand een ander nadoen."""
    sleutel = naamSleutel(naam)
    return any(naamSleutel(bestaand) == sleutel
               for (bestaand,) in db.session.query(User.username).all())


def validateRegistration(username: str, password: str,
                         passwordRepeat: str) -> list[str]:
    """Alle fouten in een keer terug, zodat het formulier ze samen kan tonen."""
    errors: list[str] = []

    # Dezelfde controle als bij een quiznaam: hij komt op de ranglijst te staan.
    try:
        checkName(username)
    except NameError_ as e:
        errors.append(str(e))
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f'Het wachtwoord moet minstens {MIN_PASSWORD_LENGTH} tekens lang zijn.')
    if password != passwordRepeat:
        errors.append('De twee wachtwoorden zijn niet gelijk.')

    return errors


@auth.route('/registreren', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('auth.account'))

    formData = {'username': ''}
    errors: list[str] = []

    if request.method == 'POST':
        username = ' '.join((request.form.get('username') or '').split())
        password = request.form.get('password') or ''
        passwordRepeat = request.form.get('passwordRepeat') or ''

        formData = {'username': username}

        if not csrfValid():
            errors.append('Het formulier is verlopen. Probeer het opnieuw.')
        elif registerLimiter.blocked(clientIp()):
            errors.append('Er zijn vanaf dit adres net te veel accounts aangemaakt. '
                          'Probeer het over een uur nog eens.')
        else:
            errors = validateRegistration(username, password, passwordRepeat)

            if not errors:
                if zoekGebruiker(username):
                    errors.append('Deze naam is al bezet. Kies een andere.')
                elif lijktOpBestaandeNaam(username):
                    errors.append('Deze naam lijkt te veel op die van iemand anders. Kies een andere.')

            if not errors:
                user = User(
                    username=username,
                    account_type=AccountType.STUDENT,
                )
                user.set_password(password)
                try:
                    db.session.add(user)
                    db.session.commit()
                except IntegrityError:
                    # Twee mensen tegelijk met dezelfde naam.
                    db.session.rollback()
                    errors.append('Dat account bestaat al. Probeer het opnieuw.')
                except Exception:
                    db.session.rollback()
                    current_app.logger.exception('Registreren mislukt')
                    errors.append('Het account kon niet worden aangemaakt. '
                                  'Probeer het later nog eens.')
                else:
                    # Alleen echte aanmeldingen tellen mee voor de rem; een
                    # typefout in het formulier mag niemand buitensluiten.
                    registerLimiter.registerFailure(clientIp())
                    rotateCsrfToken()
                    login_user(user)
                    flash('Je account is aangemaakt.', 'success')
                    return redirect(url_for('auth.account'))

    return render_template('register.html', errors=errors, form=formData)


@auth.route('/login')
def loginAlias():
    """Oude Engelse link; stuurt door naar /inloggen."""
    return redirect(url_for('auth.login', **request.args))


@auth.route('/inloggen', methods=['GET', 'POST'])
def login():
    nextUrl = safeUrl(request.values.get('next'), url_for('main.index'))

    if current_user.is_authenticated:
        return redirect(nextUrl)

    errors: list[str] = []
    username = ''

    if request.method == 'POST':
        username = ' '.join((request.form.get('username') or '').split())[:80]
        password = request.form.get('password') or ''
        ip = clientIp()

        if not csrfValid():
            errors.append('Het formulier is verlopen. Probeer het opnieuw.')
        elif loginLimiter.blocked(ip):
            errors.append('Te veel mislukte pogingen. Wacht vijf minuten en probeer het opnieuw.')
        else:
            user = zoekGebruiker(username)
            if user and user.check_password(password):
                loginLimiter.reset(ip)
                rotateCsrfToken()
                login_user(user, remember=bool(request.form.get('remember')))
                flash('Je bent ingelogd.', 'success')
                return redirect(nextUrl)

            if not user:
                # Even lang rekenen als bij een bestaand account.
                check_password_hash(DUMMY_HASH, password)
            loginLimiter.registerFailure(ip)
            # Bewust een algemene melding: verklap niet of de naam bestaat.
            errors.append('Naam of wachtwoord klopt niet.')

    return render_template('login.html', errors=errors, username=username, next=nextUrl)


@auth.route('/uitloggen', methods=['POST'])
@login_required
def logout():
    if not csrfValid():
        return redirect(url_for('auth.account'))
    logout_user()
    rotateCsrfToken()
    flash('Je bent uitgelogd.', 'success')
    return redirect(url_for('main.index'))


@auth.route('/account')
@login_required
def account():
    recent = (DuelMatch.query
              .filter(db.or_(DuelMatch.one_id == current_user.id,
                             DuelMatch.two_id == current_user.id))
              .order_by(DuelMatch.played_at.desc())
              .limit(5).all())
    return render_template('account.html', duels=recent)
