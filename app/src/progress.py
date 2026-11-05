"""Punten, levels en elo.

Twee losse ladders, met opzet:

- **XP en level** zijn een beloning voor oefenen. Ze kunnen alleen omhoog, dus
  wie veel oefent komt vanzelf hoger. Dat is bedoeld voor de leerling die
  gewoon zijn toets wil halen.
- **Elo** is een schatting van hoe goed je bent ten opzichte van anderen en kan
  dus ook zakken. Die verandert alleen door duels.

Ze door elkaar halen zou allebei kapotmaken: een level dat kan zakken voelt
oneerlijk, en een ranglijst waarin de fanatiekste oefenaar bovenaan staat zegt
niets over wie het beste is.
"""
from __future__ import annotations

# ----------------------------------------------------------------------
# XP en levels
# ----------------------------------------------------------------------
XP_PER_QUESTION = 2        # per vraag die je in een oefensessie goed krijgt
XP_ACCURACY_BONUS = 0.5    # maximaal 50% erbij als je bijna niets fout doet
XP_DAILY_CAP = 600         # rem tegen eindeloos dezelfde kleine kaart herhalen
MAX_LEVEL = 60


def xpForLevel(level: int) -> int:
    """Hoeveel totale XP je nodig hebt om dit level te halen.

    Level 2 op 50, level 3 op 150, level 5 op 500, level 10 op 2250: elk level
    kost 50 XP meer dan het vorige. Zo blijft het begin snel en wordt het later
    iets waar je echt voor moet oefenen.
    """
    level = max(1, int(level))
    return 25 * (level - 1) * level


def levelForXp(xp: int) -> int:
    xp = max(0, int(xp or 0))
    level = 1
    while level < MAX_LEVEL and xpForLevel(level + 1) <= xp:
        level += 1
    return level


def levelProgress(xp: int) -> dict:
    """Alles wat een balkje 'level 4, nog 80 XP te gaan' nodig heeft."""
    xp = max(0, int(xp or 0))
    level = levelForXp(xp)
    start = xpForLevel(level)
    if level >= MAX_LEVEL:
        return {'level': level, 'xp': xp, 'inLevel': 0, 'needed': 0,
                'toNext': 0, 'percent': 100, 'max': True}
    nextAt = xpForLevel(level + 1)
    inLevel = xp - start
    needed = nextAt - start
    return {
        'level': level,
        'xp': xp,
        'inLevel': inLevel,
        'needed': needed,
        'toNext': nextAt - xp,
        'percent': round(100 * inLevel / needed) if needed else 0,
        'max': False,
    }


def practiceXp(questionCount: int, guesses: int) -> int:
    """XP voor een afgeronde oefensessie.

    Een sessie is klaar als elke vraag goed is, dus de omvang van de kaart
    bepaalt de basis. Wie weinig fouten maakt krijgt er tot de helft bij.
    """
    questionCount = max(0, int(questionCount))
    guesses = max(questionCount, int(guesses or 0))
    if questionCount == 0:
        return 0
    base = questionCount * XP_PER_QUESTION
    accuracy = questionCount / guesses if guesses else 1.0
    return int(round(base * (1 + XP_ACCURACY_BONUS * accuracy)))


def quizXp(score: int, rank: int, players: int) -> int:
    """XP voor een klassikale quiz: vooral je eigen score, met een bonus voor de top drie."""
    score = max(0, int(score or 0))
    xp = score // 100
    if players > 1 and rank <= 3:
        xp += {1: 30, 2: 20, 3: 10}[rank]
    return xp


def duelXp(won: bool, score: int) -> int:
    """XP voor een duel. Ook de verliezer houdt er iets aan over."""
    xp = max(0, int(score or 0)) // 100
    return xp + (25 if won else 10)


# ----------------------------------------------------------------------
# Elo
# ----------------------------------------------------------------------
START_RATING = 1000
MIN_RATING = 100
PLACEMENT_GAMES = 10   # de eerste tien duels tellen zwaarder
K_PLACEMENT = 40
K_NORMAL = 24


def expectedScore(rating: int, opponentRating: int) -> float:
    return 1 / (1 + 10 ** ((opponentRating - rating) / 400))


def kFactor(gamesPlayed: int) -> int:
    return K_PLACEMENT if gamesPlayed < PLACEMENT_GAMES else K_NORMAL


def newRating(rating: int, opponentRating: int, result: float, gamesPlayed: int) -> int:
    """result: 1 gewonnen, 0.5 gelijk, 0 verloren."""
    expected = expectedScore(rating, opponentRating)
    change = kFactor(gamesPlayed) * (result - expected)
    return max(MIN_RATING, int(round(rating + change)))


def ratingTitle(rating: int) -> str:
    """Een naam bij een elo, zodat een getal ook iets zegt."""
    if rating < 800:
        return 'Beginner'
    if rating < 1000:
        return 'Leerling'
    if rating < 1200:
        return 'Kenner'
    if rating < 1400:
        return 'Atlas'
    if rating < 1600:
        return 'Ontdekkingsreiziger'
    return 'Cartograaf'
