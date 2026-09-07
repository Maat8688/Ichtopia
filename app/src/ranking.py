"""De ranglijst: wie heeft de meeste XP, en wie de hoogste elo."""
from __future__ import annotations

from flask import Blueprint, render_template, request
from flask_login import current_user

from .models import User, db
from .progress import START_RATING, levelForXp, ratingTitle

ranking = Blueprint('ranking', __name__)

TOP_COUNT = 25
# Wie nog nooit geduelleerd heeft, staat niet in de elo-lijst: anders staat de
# halve school op precies 1000 en zegt de lijst niets.
MIN_DUELS = 1


def xpBoard(limit: int = TOP_COUNT) -> list[dict]:
    users = (User.query.filter(User.xp > 0)
             .order_by(User.xp.desc(), User.username.asc())
             .limit(limit).all())
    return [{
        'rank': i + 1,
        'id': user.id,
        'name': user.username,
        'xp': user.xp,
        'level': user.level,
        'teacher': user.isTeacher,
    } for i, user in enumerate(users)]


def eloBoard(limit: int = TOP_COUNT) -> list[dict]:
    users = (User.query
             .filter((User.duels_won + User.duels_lost + User.duels_drawn) >= MIN_DUELS)
             .order_by(User.rating.desc(), User.username.asc())
             .limit(limit).all())
    return [{
        'rank': i + 1,
        'id': user.id,
        'name': user.username,
        'rating': user.rating,
        'title': user.ratingTitle,
        'won': user.duels_won,
        'lost': user.duels_lost,
        'drawn': user.duels_drawn,
        'teacher': user.isTeacher,
    } for i, user in enumerate(users)]


def ownXpRank(user) -> int:
    """Op welke plaats sta je zelf, ook als je buiten de top valt."""
    if not user.xp:
        return 0
    return db.session.query(User).filter(User.xp > user.xp).count() + 1


def ownEloRank(user) -> int:
    if user.duelsPlayed < MIN_DUELS:
        return 0
    return (db.session.query(User)
            .filter((User.duels_won + User.duels_lost + User.duels_drawn) >= MIN_DUELS)
            .filter(User.rating > user.rating).count() + 1)


@ranking.route('/ranglijst')
def board():
    tab = 'elo' if request.args.get('lijst') == 'elo' else 'xp'
    me = None
    if current_user.is_authenticated:
        me = {
            'id': current_user.id,
            'xpRank': ownXpRank(current_user),
            'eloRank': ownEloRank(current_user),
            'xp': current_user.xp,
            'level': current_user.level,
            'progress': current_user.levelProgress,
            'rating': current_user.rating,
            'title': current_user.ratingTitle,
            'duels': current_user.duelsPlayed,
        }
    return render_template('ranglijst.html', tab=tab, me=me,
                           xpBoard=xpBoard(), eloBoard=eloBoard(),
                           startRating=START_RATING)
