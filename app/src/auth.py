"""Accounts: registreren, inloggen, uitloggen en de accountpagina.

Een account is nergens verplicht. Oefenen kan gewoon zonder inloggen; een
account voegt alleen iets toe (docentrechten nu, opgeslagen voortgang later).
"""
from __future__ import annotations

import re
import secrets

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .models import db, User, AccountType
from .security import (AttemptLimiter, clientIp, csrfToken, csrfValid,
                       rotateCsrfToken, safeUrl)

auth = Blueprint('auth', __name__)

# Vijf misluke pogingen per IP, daarna vijf minuten wachten.
loginLimiter = AttemptLimiter(maxAttempts=5, window=5 * 60)
# Registreren mag hooguit vijf keer per uur per IP, tegen het volautomatisch
# aanmaken van accounts.
registerLimiter = AttemptLimiter(maxAttempts=5, window=60 * 60)

USERNAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ._-]{1,31}$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$')
MIN_PASSWORD_LENGTH = 8

# Een echte hash van een willekeurig wachtwoord om tegenaan te rekenen als het
# e-mailadres niet bestaat. Zo duurt een inlogpoging even lang met en zonder
# bestaand account, en kun je via de reactietijd niet uitvissen wie er een
# account heeft.
DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(16))


def teacherCode() -> str:
    """De docentcode uit de omgeving; dezelfde code als voor de klassikale quiz."""
    # Hier geimporteerd en niet bovenaan, om een kringetje van imports te vermijden.
    from .kahoot_routes import hostCode
    return hostCode()


@auth.app_context_processor
def injectAuthHelpers():
    """`csrfToken()` beschikbaar in elke template."""
    return {'csrfToken': csrfToken}


def validateRegistration(username: str, email: str, password: str,
                         passwordRepeat: str, accountType: str, code: str) -> list[str]:
    """Alle fouten in een keer terug, zodat het formulier ze samen kan tonen."""
    errors: list[str] = []

    if not USERNAME_RE.match(username):
        errors.append('Kies een naam van 2 tot 32 tekens: letters, cijfers, '
                      'spatie, punt, streepje of liggend streepje.')
    if not EMAIL_RE.match(email) or len(email) > 120:
        errors.append('Vul een geldig e-mailadres in.')
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f'Het wachtwoord moet minstens {MIN_PASSWORD_LENGTH} tekens lang zijn.')
    if password != passwordRepeat:
        errors.append('De twee wachtwoorden zijn niet gelijk.')
    if accountType not in ('student', 'docent'):
        errors.append('Kies of je leerling of docent bent.')
    elif accountType == 'docent':
        expected = teacherCode()
        if not expected:
            errors.append('Docentaccounts kunnen nog niet worden aangemaakt: er is '
                          'op de server geen docentcode ingesteld.')
        elif code != expected:
            errors.append('De docentcode klopt niet.')

    return errors


@auth.route('/registreren', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('auth.account'))

    formData = {'username': '', 'email': '', 'accountType': 'student'}
    errors: list[str] = []

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = User.normalizeEmail(request.form.get('email'))
        password = request.form.get('password') or ''
        passwordRepeat = request.form.get('passwordRepeat') or ''
        accountType = request.form.get('accountType') or 'student'
        code = (request.form.get('teacherCode') or '').strip()

        formData = {'username': username, 'email': email, 'accountType': accountType}

        if not csrfValid():
            errors.append('Het formulier is verlopen. Probeer het opnieuw.')
        elif registerLimiter.blocked(clientIp()):
            errors.append('Er zijn vanaf dit adres net te veel accounts aangemaakt. '
                          'Probeer het over een uur nog eens.')
        else:
            errors = validateRegistration(username, email, password,
                                          passwordRepeat, accountType, code)

            if not errors:
                if User.query.filter_by(email=email).first():
                    errors.append('Er bestaat al een account met dit e-mailadres.')
                if User.query.filter_by(username=username).first():
                    errors.append('Deze naam is al bezet.')

            if not errors:
                user = User(
                    username=username,
                    email=email,
                    account_type=(AccountType.TEACHER if accountType == 'docent'
                                  else AccountType.STUDENT),
                )
                user.set_password(password)
                try:
                    db.session.add(user)
                    db.session.commit()
                except IntegrityError:
                    # Twee mensen tegelijk met dezelfde naam of hetzelfde adres.
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

    return render_template('register.html', errors=errors, form=formData,
                           teacherSignupPossible=bool(teacherCode()))


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
    email = ''

    if request.method == 'POST':
        email = User.normalizeEmail(request.form.get('email'))
        password = request.form.get('password') or ''
        ip = clientIp()

        if not csrfValid():
            errors.append('Het formulier is verlopen. Probeer het opnieuw.')
        elif loginLimiter.blocked(ip):
            errors.append('Te veel mislukte pogingen. Wacht vijf minuten en probeer het opnieuw.')
        else:
            user = User.query.filter_by(email=email).first()
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
            # Bewust een algemene melding: verklap niet of het adres bestaat.
            errors.append('E-mailadres of wachtwoord klopt niet.')

    return render_template('login.html', errors=errors, email=email, next=nextUrl)


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
    return render_template('account.html')
