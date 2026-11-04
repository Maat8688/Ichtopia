from __future__ import annotations
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from enum import Enum

db:SQLAlchemy = SQLAlchemy()

class AccountType(Enum):
    TEACHER = 1
    STUDENT = 2

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    account_type = db.Column(db.Enum(AccountType), nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
class Results(db.Model):
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    players = db.Column(db.ARRAY(db.Integer), nullable=False)
    scores = db.Column(db.ARRAY(db.Integer), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Results {self.user_id} {self.score} {self.date}>'


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

    def __repr__(self):
        return f'<Gebruik {self.soort} {self.tijd}>'
