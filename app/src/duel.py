"""1-tegen-1 duels.

Twee ingelogde spelers krijgen dezelfde vragen op hetzelfde moment. Per vraag
levert snelheid punten op (net als bij de klassikale quiz); wie na alle vragen
de hoogste score heeft, wint en pakt elo van de ander af.

Deze module is bewust zonder database: hij kent alleen het spel. Het opslaan
van elo en de uitslag gebeurt in duel_routes.py.
"""
from __future__ import annotations

import random
import secrets
import string
import threading
import time

from .kahoot import (MAP_CATEGORIES, MAP_FILES, MAP_NIVEAUS, MODE_CLICKTHECOUNTRY,
                     MODE_MULTIPLECHOICE, QUESTION_PROMPTS, buildOptions, displayName)
from .map import mapQuestion, mapSession, normalizeAnswer

MAX_POINTS = 1000
DEFAULT_QUESTIONS = 10
DEFAULT_SECONDS = 15
MAX_ANSWER_LENGTH = 200
DUEL_MAX_AGE = 2 * 60 * 60        # oude duels opruimen
LOBBY_MAX_AGE = 20 * 60           # een duel waar niemand op afkomt
CODE_ALPHABET = string.ascii_uppercase.replace('O', '').replace('I', '') + '23456789'


class DuelPlayer:
    def __init__(self, userId: int, name: str, rating: int, level: int):
        self.userId = int(userId)
        self.name = name
        self.rating = int(rating)
        self.level = int(level)
        self.score = 0
        self.lastPoints = 0
        self.answers: dict[int, dict] = {}
        self.sid = None
        self.connected = False

    def toDict(self) -> dict:
        return {
            'userId': self.userId,
            'name': self.name,
            'rating': self.rating,
            'level': self.level,
            'score': self.score,
            'connected': self.connected,
        }


class Duel:
    def __init__(self, code: str, mapName: str, gameMap: mapSession, mode: int,
                 categories: list[str], niveau: str | None, questionCount: int,
                 seconds: int, creator: DuelPlayer, open_: bool = True):
        if not gameMap.questions:
            raise ValueError('Er zijn geen vragen voor deze selectie.')

        self.code = code
        self.mapName = mapName
        self.map = gameMap
        self.mode = mode
        self.categories = categories
        self.niveau = niveau
        self.seconds = seconds
        self.open = open_

        questionCount = max(1, min(questionCount, len(gameMap.questions)))
        self.questions: list[mapQuestion] = random.sample(gameMap.questions, questionCount)

        self.players: list[DuelPlayer] = [creator]
        self.state = 'lobby'   # lobby -> question -> reveal -> ... -> finished
        self.currentIndex = -1
        self.questionRun = 0
        self.questionStart: float | None = None
        self.currentOptions: list[str] = []
        self.lastReveal: dict | None = None
        self.createdAt = time.time()
        self.startedAt: float | None = None
        self.ratingApplied = False   # elo wordt maar een keer verwerkt
        self.resultChanges: dict[int, dict] = {}   # per speler wat elo en XP deden
        self.lock = threading.Lock()

    # ------------------------------------------------------------------
    # Spelers
    # ------------------------------------------------------------------
    @property
    def isFull(self) -> bool:
        return len(self.players) >= 2

    def playerFor(self, userId: int) -> DuelPlayer | None:
        for player in self.players:
            if player.userId == int(userId):
                return player
        return None

    def opponentOf(self, player: DuelPlayer) -> DuelPlayer | None:
        for other in self.players:
            if other.userId != player.userId:
                return other
        return None

    def join(self, player: DuelPlayer) -> DuelPlayer:
        """Voeg de tegenstander toe, of geef de bestaande speler terug bij terugkomen."""
        with self.lock:
            existing = self.playerFor(player.userId)
            if existing is not None:
                return existing
            if self.state != 'lobby':
                raise ValueError('Dit duel is al begonnen.')
            if len(self.players) >= 2:
                raise ValueError('Dit duel zit al vol.')
            self.players.append(player)
            return player

    def playerBySid(self, sid) -> DuelPlayer | None:
        for player in self.players:
            if player.sid == sid:
                return player
        return None

    # ------------------------------------------------------------------
    # Vragen
    # ------------------------------------------------------------------
    @property
    def currentQuestion(self) -> mapQuestion | None:
        if 0 <= self.currentIndex < len(self.questions):
            return self.questions[self.currentIndex]
        return None

    @property
    def isLastQuestion(self) -> bool:
        return self.currentIndex >= len(self.questions) - 1

    def remainingSeconds(self) -> float:
        if self.state != 'question' or self.questionStart is None:
            return 0
        return max(0.0, self.seconds - (time.time() - self.questionStart))

    def nextQuestion(self) -> bool:
        with self.lock:
            if self.currentIndex >= len(self.questions) - 1:
                self.state = 'finished'
                return False
            self.currentIndex += 1
            self.questionRun += 1
            self.state = 'question'
            self.questionStart = time.time()
            if self.startedAt is None:
                self.startedAt = self.questionStart
            self.lastReveal = None
            question = self.questions[self.currentIndex]
            self.currentOptions = (buildOptions(self.map, question)
                                   if self.mode == MODE_MULTIPLECHOICE else [])
            return True

    def questionPayload(self) -> dict:
        question = self.currentQuestion
        payload = {
            'index': self.currentIndex,
            'number': self.currentIndex + 1,
            'total': len(self.questions),
            'mode': self.mode,
            'seconds': self.seconds,
            'remaining': self.remainingSeconds(),
            'category': question.category,
            'isLast': self.isLastQuestion,
        }
        if self.mode == MODE_MULTIPLECHOICE:
            payload['options'] = list(self.currentOptions)
            payload['prompt'] = QUESTION_PROMPTS.get(question.category, 'Wat is dit?')
        else:
            payload['prompt'] = f'Klik op: {displayName(question)}'
        return payload

    # ------------------------------------------------------------------
    # Antwoorden
    # ------------------------------------------------------------------
    def isCorrect(self, answer: str, hashed: bool) -> bool:
        question = self.currentQuestion
        if question is None:
            return False
        answer = str(answer)[:MAX_ANSWER_LENGTH]
        if hashed:
            return answer == self.map.hash(question.id)
        return normalizeAnswer(answer) in [normalizeAnswer(a) for a in question.allAnswers]

    def answer(self, userId: int, answer: str, hashed: bool) -> tuple[bool, bool]:
        """Verwerk een antwoord. Geeft (geaccepteerd, allebei geantwoord)."""
        with self.lock:
            player = self.playerFor(userId)
            if player is None or self.state != 'question':
                return False, False
            if self.currentIndex in player.answers:
                return False, False
            elapsed = time.time() - self.questionStart
            if elapsed > self.seconds + 1:
                return False, False
            correct = self.isCorrect(answer, hashed)
            fraction = min(max(elapsed / self.seconds, 0.0), 1.0)
            points = round(MAX_POINTS * (1 - fraction / 2)) if correct else 0
            player.answers[self.currentIndex] = {
                'correct': correct,
                'points': points,
                'time': round(elapsed, 2),
            }
            bothAnswered = all(self.currentIndex in p.answers for p in self.players)
            return True, bothAnswered

    # ------------------------------------------------------------------
    # Onthullen en einde
    # ------------------------------------------------------------------
    def reveal(self) -> dict | None:
        with self.lock:
            if self.state != 'question':
                return None
            self.state = 'reveal'
            question = self.currentQuestion
            for player in self.players:
                info = player.answers.get(self.currentIndex)
                player.lastPoints = info['points'] if info else 0
                player.score += player.lastPoints

            self.lastReveal = {
                'index': self.currentIndex,
                'number': self.currentIndex + 1,
                'total': len(self.questions),
                'correctAnswer': displayName(question),
                'mapId': self.map.hash(question.id),
                'isLast': self.isLastQuestion,
                'scores': [p.toDict() for p in self.players],
            }
            return self.lastReveal

    def resultFor(self, player: DuelPlayer) -> dict:
        info = player.answers.get(self.currentIndex)
        opponent = self.opponentOf(player)
        opponentInfo = opponent.answers.get(self.currentIndex) if opponent else None
        return {
            'answered': info is not None,
            'correct': bool(info and info['correct']),
            'points': info['points'] if info else 0,
            'score': player.score,
            'opponentCorrect': bool(opponentInfo and opponentInfo['correct']),
            'opponentPoints': opponentInfo['points'] if opponentInfo else 0,
            'opponentScore': opponent.score if opponent else 0,
            'correctAnswer': self.lastReveal['correctAnswer'] if self.lastReveal else None,
            'isLast': self.isLastQuestion,
        }

    def finish(self):
        with self.lock:
            self.state = 'finished'

    @property
    def winner(self) -> DuelPlayer | None:
        """None bij gelijkspel of bij een duel dat nooit gespeeld is."""
        if len(self.players) < 2:
            return None
        first, second = self.players[0], self.players[1]
        if first.score == second.score:
            return None
        return first if first.score > second.score else second

    def finishedPayload(self, player: DuelPlayer, ratingChange: dict | None = None) -> dict:
        opponent = self.opponentOf(player)
        winner = self.winner
        if winner is None:
            outcome = 'gelijk'
        elif winner.userId == player.userId:
            outcome = 'gewonnen'
        else:
            outcome = 'verloren'
        payload = {
            'outcome': outcome,
            'score': player.score,
            'opponentScore': opponent.score if opponent else 0,
            'opponentName': opponent.name if opponent else '',
            'questions': len(self.questions),
            'correct': sum(1 for a in player.answers.values() if a['correct']),
        }
        if ratingChange:
            payload.update(ratingChange)
        return payload

    # ------------------------------------------------------------------
    # Volledige status (voor herverbinden)
    # ------------------------------------------------------------------
    def stateFor(self, player: DuelPlayer, ratingChange: dict | None = None) -> dict:
        opponent = self.opponentOf(player)
        state = {
            'state': self.state,
            'code': self.code,
            'mode': self.mode,
            'mapName': self.mapName,
            'totalQuestions': len(self.questions),
            'seconds': self.seconds,
            'me': player.toDict(),
            'opponent': opponent.toDict() if opponent else None,
        }
        if self.state == 'question':
            state['question'] = self.questionPayload()
            state['answered'] = self.currentIndex in player.answers
        elif self.state == 'reveal':
            state['result'] = self.resultFor(player)
        elif self.state == 'finished':
            state['result'] = self.finishedPayload(player, ratingChange)
        return state

    def summary(self) -> dict:
        """Regel voor de lijst met openstaande duels."""
        creator = self.players[0]
        return {
            'code': self.code,
            'mapName': self.mapName,
            'mode': self.mode,
            'questions': len(self.questions),
            'seconds': self.seconds,
            'creator': creator.name,
            'creatorRating': creator.rating,
            'creatorLevel': creator.level,
            'waitingFor': round(time.time() - self.createdAt),
        }


class DuelManager:
    def __init__(self):
        self.duels: dict[str, Duel] = {}
        self.lock = threading.Lock()

    def _newCode(self) -> str:
        while True:
            code = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(5))
            if code not in self.duels:
                return code

    def createDuel(self, creator: DuelPlayer, mapName: str, mode: str | int,
                   categories: list[str], questionCount: int = DEFAULT_QUESTIONS,
                   seconds: int = DEFAULT_SECONDS, niveau: str | None = None,
                   open_: bool = True) -> Duel:
        if mapName not in MAP_FILES:
            raise ValueError('Onbekende kaart.')
        categories = [c for c in categories if c in MAP_CATEGORIES[mapName]]
        if not categories:
            raise ValueError('Kies minstens een soort vraag.')
        modeValue = (MODE_CLICKTHECOUNTRY if mode in ('ClickTheCountry', MODE_CLICKTHECOUNTRY)
                     else MODE_MULTIPLECHOICE)
        questionCount = max(3, min(int(questionCount), 25))
        seconds = max(5, min(int(seconds), 60))
        if niveau not in (MAP_NIVEAUS.get(mapName) or []):
            niveau = None

        gameMap = mapSession.fromSVG(MAP_FILES[mapName], modeValue, categories, niveau)
        with self.lock:
            self._cleanup()
            # Meer dan een openstaand duel per persoon is alleen maar rommel.
            for duel in list(self.duels.values()):
                if (duel.state == 'lobby' and not duel.isFull
                        and duel.players[0].userId == creator.userId):
                    del self.duels[duel.code]
            code = self._newCode()
            duel = Duel(code, mapName, gameMap, modeValue, categories, niveau,
                        questionCount, seconds, creator, open_)
            self.duels[code] = duel
        return duel

    def getDuel(self, code: str) -> Duel | None:
        if not code:
            return None
        return self.duels.get(str(code).strip().upper())

    def openDuels(self, exceptUserId: int | None = None) -> list[dict]:
        self._cleanup()
        duels = [d for d in self.duels.values()
                 if d.open and d.state == 'lobby' and not d.isFull
                 and d.players[0].userId != exceptUserId]
        duels.sort(key=lambda d: d.createdAt)
        return [d.summary() for d in duels]

    def duelForUser(self, userId: int) -> Duel | None:
        """Het duel waar deze speler nu in zit, om terug te kunnen keren."""
        for duel in self.duels.values():
            if duel.state != 'finished' and duel.playerFor(userId) is not None:
                return duel
        return None

    def remove(self, code: str):
        with self.lock:
            self.duels.pop(code, None)

    def _cleanup(self):
        now = time.time()
        for code in list(self.duels.keys()):
            duel = self.duels[code]
            tooOld = now - duel.createdAt > DUEL_MAX_AGE
            staleLobby = (duel.state == 'lobby' and not duel.isFull
                          and now - duel.createdAt > LOBBY_MAX_AGE)
            if tooOld or staleLobby:
                del self.duels[code]
