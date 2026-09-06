from __future__ import annotations
from datetime import datetime, timezone
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
    # E-mail wordt altijd in kleine letters opgeslagen, zodat Jan@ en jan@
    # niet twee losse accounts worden.
    email = db.Column(db.String(120), unique=True, nullable=False)
    # Ruim genomen: de hash van werkzeug (scrypt) is een stuk langer dan 128
    # tekens en paste niet in de oude kolom.
    password_hash = db.Column(db.String(255), nullable=False)
    account_type = db.Column(db.Enum(AccountType), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<User {self.username}>'
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def isTeacher(self) -> bool:
        return self.account_type == AccountType.TEACHER

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
