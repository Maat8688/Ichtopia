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
    # E-mail wordt altijd in kleine letters opgeslagen, zodat Jan@ en jan@
    # niet twee losse accounts worden.
    email = db.Column(db.String(120), unique=True, nullable=False)
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

    @staticmethod
    def normalizeEmail(email: str) -> str:
        return (email or '').strip().lower()
    
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
