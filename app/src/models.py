from __future__ import annotations
from datetime import date, datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from enum import Enum

from .progress import START_RATING, levelForXp, levelProgress, ratingTitle

db:SQLAlchemy = SQLAlchemy()

class AccountType(Enum):
    TEACHER = 1
    STUDENT = 2

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    # Niet meer gebruikt: een account is alleen een naam en een wachtwoord.
    # De kolom blijft bestaan (leeg) zodat oudere databases niet stuk gaan;
    # de migratie e2b4c6d8f0a1 heeft alle adressen gewist.
    email = db.Column(db.String(120), unique=True, nullable=True)
    # Ruim genomen: de hash van werkzeug (scrypt) is een stuk langer dan 128
    # tekens en paste niet in de oude kolom.
    password_hash = db.Column(db.String(255), nullable=False)
    account_type = db.Column(db.Enum(AccountType), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    # Oefenen: XP kan alleen omhoog.
    xp = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    # Dagteller voor de XP-rem; wordt vanzelf gereset op een nieuwe dag.
    xp_day = db.Column(db.Date, nullable=True)
    xp_today = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    # Duels: elo kan ook zakken.
    rating = db.Column(db.Integer, nullable=False, default=START_RATING,
                       server_default=str(START_RATING))
    duels_won = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    duels_lost = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    duels_drawn = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    def __repr__(self):
        return f'<User {self.username}>'
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def isTeacher(self) -> bool:
        return self.account_type == AccountType.TEACHER

    @property
    def level(self) -> int:
        return levelForXp(self.xp)

    @property
    def levelProgress(self) -> dict:
        return levelProgress(self.xp)

    @property
    def ratingTitle(self) -> str:
        return ratingTitle(self.rating)

    @property
    def duelsPlayed(self) -> int:
        return (self.duels_won or 0) + (self.duels_lost or 0) + (self.duels_drawn or 0)

    def addXp(self, amount: int, cap: int | None = None) -> int:
        """Tel XP op, met een rem per dag. Geeft terug hoeveel er echt bijkwam."""
        amount = max(0, int(amount))
        if amount == 0:
            return 0
        today = date.today()
        if self.xp_day != today:
            self.xp_day = today
            self.xp_today = 0
        if cap is not None:
            room = max(0, cap - (self.xp_today or 0))
            amount = min(amount, room)
            if amount == 0:
                return 0
        self.xp = (self.xp or 0) + amount
        self.xp_today = (self.xp_today or 0) + amount
        return amount

    
class Results(db.Model):
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    players = db.Column(db.ARRAY(db.Integer), nullable=False)
    scores = db.Column(db.ARRAY(db.Integer), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Results {self.user_id} {self.score} {self.date}>'


class DuelMatch(db.Model):
    """Een gespeeld duel. Bewaard voor de geschiedenis op je accountpagina en
    om te zien of twee mensen elkaar de hele dag punten zitten toe te spelen."""
    id = db.Column(db.Integer, primary_key=True)
    played_at = db.Column(db.DateTime, nullable=False,
                          default=lambda: datetime.now(timezone.utc), index=True)
    map_name = db.Column(db.String(40), nullable=False)
    questions = db.Column(db.Integer, nullable=False)
    rated = db.Column(db.Boolean, nullable=False, default=True, server_default='1')

    one_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    two_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    one_score = db.Column(db.Integer, nullable=False, default=0)
    two_score = db.Column(db.Integer, nullable=False, default=0)
    one_rating_before = db.Column(db.Integer, nullable=False)
    two_rating_before = db.Column(db.Integer, nullable=False)
    one_rating_after = db.Column(db.Integer, nullable=False)
    two_rating_after = db.Column(db.Integer, nullable=False)

    one = db.relationship('User', foreign_keys=[one_id])
    two = db.relationship('User', foreign_keys=[two_id])

    def __repr__(self):
        return f'<DuelMatch {self.one_id} {self.one_score}-{self.two_score} {self.two_id}>'

    def opponentOf(self, userId: int):
        return self.two if self.one_id == userId else self.one

    def resultFor(self, userId: int) -> str:
        mine, theirs = ((self.one_score, self.two_score) if self.one_id == userId
                        else (self.two_score, self.one_score))
        if mine > theirs:
            return 'gewonnen'
        if mine < theirs:
            return 'verloren'
        return 'gelijk'

    def ratingChangeFor(self, userId: int) -> int:
        if self.one_id == userId:
            return self.one_rating_after - self.one_rating_before
        return self.two_rating_after - self.two_rating_before

    def scoreFor(self, userId: int) -> tuple[int, int]:
        return ((self.one_score, self.two_score) if self.one_id == userId
                else (self.two_score, self.one_score))
class Gebruik(db.Model):
    """Eén gebeurtenis op de site, voor de pagina /statistieken.

    Bewust zonder namen, e-mailadressen of IP-adressen: de site wordt door
    leerlingen gebruikt. `bezoeker` is een code die elke dag opnieuw wordt
    gemaakt (zie gebruik.py), zodat je wel kunt tellen hoeveel verschillende
    mensen er op een dag waren, maar niet wie dat waren of wie er gisteren
    terugkwam.
    """
    __tablename__ = 'gebruik'

    id = db.Column(db.Integer, primary_key=True)
    tijd = db.Column(db.DateTime, nullable=False, index=True)   # UTC
    soort = db.Column(db.String(24), nullable=False, index=True)
    pagina = db.Column(db.String(40))
    bezoeker = db.Column(db.String(16))
    apparaat = db.Column(db.String(12))
    kaart = db.Column(db.String(40))
    vorm = db.Column(db.String(20))
    onderdelen = db.Column(db.String(200))       # met komma's ertussen
    niveau = db.Column(db.String(8))
    vragen = db.Column(db.Integer)
    pogingen = db.Column(db.Integer)
    duur = db.Column(db.Integer)                 # seconden
    spelers = db.Column(db.Integer)
    fout = db.Column(db.Text)                    # JSON: {plek: extra pogingen}
    # Waar vandaan, opgezocht bij het bezoek (locatie.py). Het IP-adres zelf
    # wordt niet bewaard.
    land = db.Column(db.String(2))
    provincie = db.Column(db.String(20))
    school = db.Column(db.Boolean)               # op het schoolnetwerk (als SCHOOL_NETWERK is ingesteld)
    # Leeg = waarschijnlijk een mens. Anders waarom het op een bot lijkt
    # ('zoekmachine', 'script', 'geen taal', ...); zie gebruik.botReden().
    bot = db.Column(db.String(24))
    toets = db.Column(db.Boolean)                # True: een toets in plaats van oefenen
    cijfer = db.Column(db.Integer)               # cijfer van de toets x 10 (75 = 7,5)

    def __repr__(self):
        return f'<Gebruik {self.soort} {self.tijd}>'


class GeblokkeerdWoord(db.Model):
    """Een woord dat een beheerder op /beheer aan het naamfilter heeft
    toegevoegd, omdat het er toch doorheen glipte. Zie names.zetExtraWoorden."""
    __tablename__ = 'geblokkeerd_woord'

    id = db.Column(db.Integer, primary_key=True)
    woord = db.Column(db.String(40), unique=True, nullable=False)
    toegevoegd_op = db.Column(db.DateTime, nullable=False,
                              default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<GeblokkeerdWoord {self.woord}>'


class Melding(db.Model):
    """Een melding van een bezoeker: iets werkt niet, een idee, of een vraag
    op de kaart die niet klopt. Alleen te zien op /beheer/meldingen.

    Bewust zonder naam, account of IP-adres: wie meldt, blijft onbekend.
    """
    __tablename__ = 'melding'

    id = db.Column(db.Integer, primary_key=True)
    tijd = db.Column(db.DateTime, nullable=False, index=True,
                     default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    soort = db.Column(db.String(10), nullable=False)       # kaart, kapot, idee
    reden = db.Column(db.String(20))                         # bij kaart: antwoord, plek, spelling, anders
    tekst = db.Column(db.String(500))
    pagina = db.Column(db.String(80))
    kaart = db.Column(db.String(40))
    vraag = db.Column(db.String(80))
    antwoord = db.Column(db.String(80))                     # wat de leerling antwoordde
    afgehandeld = db.Column(db.Boolean, nullable=False, default=False, server_default='0')

    def __repr__(self):
        return f'<Melding {self.soort} {self.tijd}>'
