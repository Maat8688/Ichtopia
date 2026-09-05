"""Klassikale quiz ("Kahoot-modus").

Een docent host een quiz op het bord, leerlingen doen mee op hun eigen
laptop via een pincode. Per vraag krijgen leerlingen punten op basis van
juistheid en snelheid, en na elke vraag is er een scorebord.

Deze module bevat alleen de spel-logica; de socket-handlers en routes staan in
kahoot_routes.py.
"""
from __future__ import annotations

import random
import secrets
import threading
import time

from .map import mapSession, mapQuestion, normalizeAnswer

# Maximale punten per vraag. Wie meteen goed antwoordt krijgt MAX_POINTS,
# wie op het allerlaatste moment goed antwoordt krijgt de helft.
MAX_POINTS = 1000

MODE_MULTIPLECHOICE = 1
MODE_CLICKTHECOUNTRY = 3

MAP_FILES = {
    'Nederland': 'data/maps/Nederland.svg',
    'Europa': 'data/maps/Europa.svg',
    'Wereld': 'data/maps/Wereld.svg',
}

MAP_CATEGORIES = {
    'Nederland': ['Steden', 'Provincies', 'Wateren', 'Gebieden'],
    'Europa': ['Landen'],
    'Wereld': ['Landen', 'Hoofdsteden', 'Steden'],
}

QUESTION_PROMPTS = {
    'Landen': 'Welk land is dit?',
    'Steden': 'Welke stad is dit?',
    'Hoofdsteden': 'Welke hoofdstad is dit?',
    'Provincies': 'Welke provincie is dit?',
    'Wateren': 'Welk water is dit?',
    'Gebieden': 'Welk gebied is dit?',
}

# Spellen die langer dan dit bestaan worden opgeruimd.
GAME_MAX_AGE = 4 * 60 * 60

MAX_PLAYERS = 100
MAX_NAME_LENGTH = 24
MAX_ANSWER_LENGTH = 200


def cleanName(name: str) -> str:
    """Haal rare tekens en dubbele spaties uit een spelersnaam."""
    name = ''.join(ch for ch in str(name) if ch.isprintable())
    return ' '.join(name.split())[:MAX_NAME_LENGTH]


def displayName(question: mapQuestion) -> str:
    """De naam die op het bord getoond wordt voor een vraag."""
    return question.displayName


class KahootPlayer:
    def __init__(self, name: str):
        self.id = secrets.token_urlsafe(16)
        self.name = name
        self.score = 0
        self.sid = None
        self.connected = True
        self.lastPoints = 0
        self.answers: dict[int, dict] = {}  # questionIndex -> answer info

    def toDict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'score': self.score,
            'connected': self.connected,
        }


class KahootGame:
    def __init__(self, pin: str, mapName: str, gameMap: mapSession, mode: int,
                 questionCount: int, secondsPerQuestion: int, categories: list[str]):
        self.pin = pin
        self.hostToken = secrets.token_urlsafe(24)
        self.mapName = mapName
        self.map = gameMap
        self.mode = mode
        self.seconds = secondsPerQuestion
        self.categories = categories

        if not gameMap.questions:
            raise ValueError('Er zijn geen vragen voor deze selectie.')
        questionCount = max(1, min(questionCount, len(gameMap.questions)))
        self.questions: list[mapQuestion] = random.sample(gameMap.questions, questionCount)

        self.state = 'lobby'  # lobby -> question -> reveal -> ... -> finished
        self.currentIndex = -1
        self.players: dict[str, KahootPlayer] = {}
        self.kicked: set[str] = set()
        self.lock = threading.Lock()
        self.questionStart: float | None = None
        self.questionRun = 0  # verhoogd per vraag, zodat een oude timer niets meer doet
        self.currentOptions: list[str] = []
        self.lastReveal: dict | None = None
        self.hostSid = None
        self.createdAt = time.time()

    # ------------------------------------------------------------------
    # Spelers
    # ------------------------------------------------------------------
    def addPlayer(self, name: str) -> KahootPlayer:
        name = cleanName(name)
        if not name:
            raise ValueError('Vul een naam in.')
        if self.state == 'finished':
            raise ValueError('Deze quiz is al afgelopen.')
        with self.lock:
            if len(self.players) >= MAX_PLAYERS:
                raise ValueError('Deze quiz zit vol.')
            # Namen zijn uniek, ook van spelers die even geen verbinding hebben:
            # anders kan iemand anders jouw naam en score overnemen.
            for player in self.players.values():
                if player.name.lower() == name.lower():
                    raise ValueError('Deze naam is al in gebruik, kies een andere naam.')
            player = KahootPlayer(name)
            self.players[player.id] = player
            return player

    def removePlayer(self, playerId: str) -> KahootPlayer | None:
        """Verwijder een speler (door de docent). Die kan met dit id niet meer terugkomen."""
        with self.lock:
            player = self.players.pop(playerId, None)
            if player is not None:
                self.kicked.add(playerId)
            return player

    def getPlayer(self, playerId: str) -> KahootPlayer | None:
        return self.players.get(playerId)

    def playerBySid(self, sid) -> KahootPlayer | None:
        for player in self.players.values():
            if player.sid == sid:
                return player
        return None

    def playersPayload(self) -> dict:
        players = sorted(self.players.values(), key=lambda p: p.name.lower())
        return {
            'players': [p.toDict() for p in players],
            'count': len(players),
            'connected': sum(1 for p in players if p.connected),
        }

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

    def buildOptions(self, question: mapQuestion, length: int = 4) -> list[str]:
        """Maak meerkeuze-opties: het goede antwoord plus afleiders uit dezelfde categorie."""
        correct = displayName(question)
        sameCategory = [q for q in self.map.questions
                        if q.category == question.category and q is not question]
        others = [q for q in self.map.questions if q is not question]
        pool = sameCategory if len(sameCategory) >= length - 1 else others

        options = [correct]
        candidates = [displayName(q) for q in pool]
        random.shuffle(candidates)
        for candidate in candidates:
            if len(options) >= length:
                break
            if candidate.lower() not in [o.lower() for o in options]:
                options.append(candidate)
        random.shuffle(options)
        return options

    def nextQuestion(self) -> bool:
        """Ga naar de volgende vraag. Geeft False als er geen vragen meer zijn."""
        with self.lock:
            if self.currentIndex >= len(self.questions) - 1:
                self.state = 'finished'
                return False
            self.currentIndex += 1
            self.questionRun += 1
            self.state = 'question'
            self.questionStart = time.time()
            self.lastReveal = None
            question = self.questions[self.currentIndex]
            if self.mode == MODE_MULTIPLECHOICE:
                self.currentOptions = self.buildOptions(question)
            else:
                self.currentOptions = []
            return True

    def questionPayload(self, forHost: bool) -> dict:
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
            if forHost:
                # Alleen het bord krijgt te zien welk gebied oplicht.
                payload['mapId'] = self.map.hash(question.id)
        else:
            payload['name'] = displayName(question)
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

    def answer(self, playerId: str, answer: str, hashed: bool) -> tuple[bool, bool]:
        """Verwerk een antwoord. Geeft (geaccepteerd, iedereen heeft geantwoord)."""
        with self.lock:
            player = self.players.get(playerId)
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
                'answer': str(answer)[:MAX_ANSWER_LENGTH],
                'hashed': hashed,
                'correct': correct,
                'points': points,
                'time': round(elapsed, 2),
            }
            everyoneAnswered = all(
                self.currentIndex in p.answers
                for p in self.players.values() if p.connected
            )
            return True, everyoneAnswered

    def answeredCount(self) -> dict:
        answered = sum(1 for p in self.players.values() if self.currentIndex in p.answers)
        total = sum(1 for p in self.players.values() if p.connected)
        return {'answered': answered, 'total': total}

    # ------------------------------------------------------------------
    # Onthullen en scorebord
    # ------------------------------------------------------------------
    def reveal(self) -> dict | None:
        """Sluit de vraag, ken punten toe en maak het scorebord. None als er niets te onthullen is."""
        with self.lock:
            if self.state != 'question':
                return None
            self.state = 'reveal'
            question = self.currentQuestion
            correctName = displayName(question)

            for player in self.players.values():
                info = player.answers.get(self.currentIndex)
                points = info['points'] if info else 0
                player.lastPoints = points
                player.score += points

            distribution = []
            if self.mode == MODE_MULTIPLECHOICE:
                for option in self.currentOptions:
                    count = sum(
                        1 for p in self.players.values()
                        if self.currentIndex in p.answers
                        and normalizeAnswer(p.answers[self.currentIndex]['answer']) == normalizeAnswer(option)
                    )
                    distribution.append({
                        'label': option,
                        'count': count,
                        'correct': option.upper() in [a.upper() for a in question.allAnswers],
                    })
            else:
                correctCount = sum(1 for p in self.players.values()
                                   if p.answers.get(self.currentIndex, {}).get('correct'))
                wrongCount = sum(1 for p in self.players.values()
                                 if self.currentIndex in p.answers
                                 and not p.answers[self.currentIndex]['correct'])
                distribution = [
                    {'label': 'Goed', 'count': correctCount, 'correct': True},
                    {'label': 'Fout', 'count': wrongCount, 'correct': False},
                ]
            noAnswer = sum(1 for p in self.players.values() if self.currentIndex not in p.answers)

            self.lastReveal = {
                'index': self.currentIndex,
                'number': self.currentIndex + 1,
                'total': len(self.questions),
                'mode': self.mode,
                'correctAnswer': correctName,
                'mapId': self.map.hash(question.id),
                'category': question.category,
                'distribution': distribution,
                'noAnswer': noAnswer,
                'leaderboard': self._leaderboard(),
                'isLast': self.isLastQuestion,
            }
            return self.lastReveal

    def _leaderboard(self) -> list[dict]:
        players = sorted(self.players.values(), key=lambda p: (-p.score, p.name.lower()))
        board = []
        for i, player in enumerate(players):
            board.append({
                'rank': i + 1,
                'id': player.id,
                'name': player.name,
                'score': player.score,
                'lastPoints': player.lastPoints,
                'connected': player.connected,
            })
        return board

    def leaderboard(self) -> list[dict]:
        with self.lock:
            return self._leaderboard()

    def rankOf(self, player: KahootPlayer) -> int:
        for entry in self._leaderboard():
            if entry['id'] == player.id:
                return entry['rank']
        return len(self.players)

    def playerResult(self, player: KahootPlayer) -> dict:
        """Het resultaat van de huidige (onthulde) vraag voor één speler."""
        info = player.answers.get(self.currentIndex)
        return {
            'answered': info is not None,
            'correct': bool(info and info['correct']),
            'points': info['points'] if info else 0,
            'score': player.score,
            'rank': self.rankOf(player),
            'players': len(self.players),
            'correctAnswer': self.lastReveal['correctAnswer'] if self.lastReveal else None,
            'isLast': self.isLastQuestion,
        }

    def finish(self):
        with self.lock:
            self.state = 'finished'

    # ------------------------------------------------------------------
    # Volledige status (voor herverbinden)
    # ------------------------------------------------------------------
    def hostState(self) -> dict:
        state = {
            'state': self.state,
            'pin': self.pin,
            'mode': self.mode,
            'mapName': self.mapName,
            'totalQuestions': len(self.questions),
            'seconds': self.seconds,
            'players': self.playersPayload(),
        }
        if self.state == 'question':
            state['question'] = self.questionPayload(forHost=True)
            state['answered'] = self.answeredCount()
        elif self.state == 'reveal':
            state['reveal'] = self.lastReveal
        elif self.state == 'finished':
            state['leaderboard'] = self.leaderboard()
        return state

    def playerState(self, player: KahootPlayer) -> dict:
        state = {
            'state': self.state,
            'pin': self.pin,
            'mode': self.mode,
            'name': player.name,
            'score': player.score,
            'totalQuestions': len(self.questions),
        }
        if self.state == 'question':
            state['question'] = self.questionPayload(forHost=False)
            state['answered'] = self.currentIndex in player.answers
        elif self.state == 'reveal':
            state['result'] = self.playerResult(player)
        elif self.state == 'finished':
            state['result'] = {
                'score': player.score,
                'rank': self.rankOf(player),
                'players': len(self.players),
            }
            state['leaderboard'] = self.leaderboard()
        return state


class KahootManager:
    def __init__(self):
        self.games: dict[str, KahootGame] = {}
        self.lock = threading.Lock()

    def _newPin(self) -> str:
        while True:
            pin = ''.join(random.choices('0123456789', k=6))
            if pin not in self.games:
                return pin

    def createGame(self, mapName: str, mode: str | int, categories: list[str],
                   questionCount: int, secondsPerQuestion: int) -> KahootGame:
        if mapName not in MAP_FILES:
            raise ValueError('Onbekende kaart.')
        categories = [c for c in categories if c in MAP_CATEGORIES[mapName]]
        if not categories:
            raise ValueError('Kies minstens één soort vraag.')
        if mode in ('ClickTheCountry', MODE_CLICKTHECOUNTRY):
            modeValue = MODE_CLICKTHECOUNTRY
        else:
            modeValue = MODE_MULTIPLECHOICE
        secondsPerQuestion = max(5, min(int(secondsPerQuestion), 120))
        questionCount = max(1, min(int(questionCount), 100))

        gameMap = mapSession.fromSVG(MAP_FILES[mapName], modeValue, categories)
        with self.lock:
            self._cleanup()
            pin = self._newPin()
            game = KahootGame(pin, mapName, gameMap, modeValue, questionCount,
                              secondsPerQuestion, categories)
            self.games[pin] = game
        return game

    def getGame(self, pin: str) -> KahootGame | None:
        if pin is None:
            return None
        return self.games.get(str(pin).strip())

    def _cleanup(self):
        now = time.time()
        for pin in list(self.games.keys()):
            if now - self.games[pin].createdAt > GAME_MAX_AGE:
                del self.games[pin]

    def findBySid(self, sid) -> tuple[KahootGame | None, KahootPlayer | None]:
        for game in list(self.games.values()):
            if game.hostSid == sid:
                return game, None
            player = game.playerBySid(sid)
            if player is not None:
                return game, player
        return None, None
