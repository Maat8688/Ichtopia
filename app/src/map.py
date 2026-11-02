from __future__ import annotations
import hashlib
import os
import random
import secrets
import threading
import time
import unicodedata
from collections import OrderedDict
from enum import Enum
from bs4 import BeautifulSoup
import sys
from datetime import datetime

def normalizeAnswer(text) -> str:
    """Maak een antwoord vergelijkbaar met de goede antwoorden.

    Hoofdletters, accenten, spaties, streepjes, apostroffen en punten doen er
    niet toe. "den haag", "Den-Haag" en "Den Haag" worden alle drie "denhaag",
    en "Slovenie" wordt hetzelfde als "Slovenië". Zo hoeft niet elke schrijfwijze
    los in de kaart te staan.
    """
    text = unicodedata.normalize('NFD', str(text))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ''.join(c for c in text.lower() if c.isalnum())


class SessionGamemode(Enum):
    MULTIPLECHOICE = 1
    FILLINTHEBLANK = 2
    CLICKTHECOUNTRY = 3

class SessionManager():
    """Houdt de oefensessies bij, in het geheugen van dit proces.

    Een sessie met de wereldkaart kost al snel een paar MB, en iedereen kan er
    zonder account een aanmaken. Zonder grens kan een script de server dus
    vullen tot hij omvalt. Daarom:

    - verloopt een sessie die `maxIdle` seconden niet gebruikt is;
    - zijn er nooit meer dan `maxSessions` tegelijk: is de pot vol, dan gaat de
      sessie die het langst niet gebruikt is eruit. Wie aan het oefenen is
      raakt zijn sessie bij elk antwoord aan en blijft dus het langst staan.
    """

    def __init__(self, maxSessions: int | None = None, maxIdle: int | None = None):
        self.maxSessions = maxSessions or int(os.getenv('MAX_PRACTICE_SESSIONS', '400'))
        self.maxIdle = maxIdle or int(os.getenv('PRACTICE_SESSION_IDLE_SECONDS', str(60 * 60)))
        # Op volgorde van laatst gebruikt: vooraan het oudste.
        self.sessions: OrderedDict[str, mapSession] = OrderedDict()
        self._lastUsed: dict[str, float] = {}
        self._lock = threading.Lock()

    def _purgeExpired(self, now: float):
        for id in list(self.sessions.keys()):
            if now - self._lastUsed.get(id, 0) <= self.maxIdle:
                break   # de rest is recenter gebruikt
            self.sessions.pop(id, None)
            self._lastUsed.pop(id, None)

    def createSession(self, session:mapSession) -> str:
        id = secrets.token_urlsafe(24)
        now = time.time()
        with self._lock:
            self._purgeExpired(now)
            while len(self.sessions) >= self.maxSessions:
                oldId, _ = self.sessions.popitem(last=False)
                self._lastUsed.pop(oldId, None)
            self.sessions[id] = session
            self._lastUsed[id] = now
        return id

    def findSession(self, id) -> mapSession | None:
        """De sessie bij dit token, of None als hij niet (meer) bestaat."""
        if not isinstance(id, str):
            return None
        now = time.time()
        with self._lock:
            session = self.sessions.get(id)
            if session is None:
                return None
            if now - self._lastUsed.get(id, 0) > self.maxIdle:
                self.sessions.pop(id, None)
                self._lastUsed.pop(id, None)
                return None
            self.sessions.move_to_end(id)
            self._lastUsed[id] = now
            return session

    def getSession(self, id:str) -> mapSession:
        session = self.findSession(id)
        if session is None:
            raise KeyError(id)
        return session

    def deleteSession(self, id:str):
        with self._lock:
            self.sessions.pop(id, None)
            self._lastUsed.pop(id, None)

class mapSession():
    def __init__(self, questions:list[mapQuestion], backgroundElements:list, foregroundElements:list, viewBox:tuple=(0, 0, 1000, 1000), sessionMode:SessionGamemode=SessionGamemode.MULTIPLECHOICE):
        self.questions = questions
        self.backgroundElements = backgroundElements
        self.foregroundElements = foregroundElements
        self.viewBox = viewBox
        self.currentQuestionIndex = random.randint(0, len(questions) - 1) if questions else -1
        self.score = 0
        self.finished = False
        self.antiCheat = True
        self.startTimestamp = datetime.now()
        self.sessionMode = sessionMode
        self.correctThreshold = 0.5

    def getViewBox(self):
        return ' '.join(map(str, self.viewBox))
    
    @property
    def totalGuesses(self):
        return sum([question.tries for question in self.questions])
    
    @property
    def currentQuestion(self) -> mapQuestion:
        return self.questions[self.currentQuestionIndex]
    
    @property
    def mcAwnsers(self, length:int=4):
        awnsers = []
        awnsers.append(self.currentQuestion.allAnswers[0]) # add correct awnser
        
        # choose length - 1 random awnsers
        while len(awnsers) < length:
            awnser = random.choice(self.questions).allAnswers[0]
            if awnser not in awnsers:
                awnsers.append(awnser)
            
        random.shuffle(awnsers)
        return awnsers
    
    def getMapState(self):
        mapstate = {}

        for question in self.questions:
            mapElementId = self.hash(question.id) if self.antiCheat else question.id
            
            mapstate[mapElementId] = self.getQuestionState(question)

        return mapstate
    
    def getQuestionState(self, question):
        if question.tries == 0 or (question.timesCorrect / question.tries) == self.correctThreshold:
            state = "Normal"
        elif (question.timesCorrect / question.tries) > self.correctThreshold:
            state = "Correct"
        elif (question.timesCorrect / question.tries) < self.correctThreshold:
            state = "Incorrect"

        return state

    def getProgresBar(self):
        totalCorrect = 0
        totalTried = 0
        for question in self.questions:
            if self.getQuestionState(question) == "Correct":
                totalCorrect += 1
            if question.tries > 0:
                totalTried += 1
        
        totalIncorrect = totalTried - totalCorrect

        return {
            "totalTried": totalTried,
            "totalCorrect": totalCorrect,
            "totalIncorrect": totalIncorrect,
            "totalQuestions": len(self.questions)
        }
    
    def getFinishedData(self):
        questionBreakdown = []
        for question in self.questions:
            questionBreakdown.append( {
                "name": question.id,
                "tries": question.tries,
                "timesCorrect": question.timesCorrect
            })

        return {
            "score": self.score,
            "totalGuesses": self.totalGuesses,
            "totalErrors": self.totalGuesses - len(self.questions),
            "time": (datetime.now() - self.startTimestamp).seconds,
            "questionBreakdown": questionBreakdown
        }


    def hash(self, awnser:str):
        if self.antiCheat:
            awnser = hashlib.sha256(str(awnser).encode('utf-8')).hexdigest()
        return awnser
    
    def awnserQuestion(self, awnser:int, hashed:bool):
        possibleAwnsers = self.currentQuestion.allAnswers
        
        self.currentQuestion.tries += 1

        if hashed:
            # Bij aanwijzen stuurt de browser de id van het gebied door (gehasht),
            # dus de id telt hier altijd mee, ook als er <awnser>-regels zijn.
            awnser = str(awnser)
            possibleAwnsers = [self.hash(a) for a in possibleAwnsers + [self.currentQuestion.id]]
        else:
            awnser = normalizeAnswer(awnser)
            possibleAwnsers = [normalizeAnswer(a) for a in possibleAwnsers]

        if awnser in possibleAwnsers:
            self.score += 1
            self.currentQuestion.timesCorrect += 1
            return True
        else:
            return False
        
    def nextQuestion(self):
        possibleQuestions = []
        for i, question in enumerate(self.questions):
            if self.getQuestionState(question) != "Correct":
                possibleQuestions.append(i)
        if len(possibleQuestions) == 0:
            self.finished = True
            return True
        self.currentQuestionIndex = random.choice(possibleQuestions)
        

    @staticmethod
    def fromSVG(file:str, sessionMode:SessionGamemode|str=SessionGamemode.MULTIPLECHOICE, includeQuestions:list[str]=[], niveau:str=None) -> mapSession:
        with open(file, 'r') as f:
            svg = f.read()
        
        data = BeautifulSoup(svg, 'xml')
        mapElement = data.find('g', id='map')
        questions = []
        backgroundElements = []
        foregroundElements = []
        #loop trough all g in map
        for g in mapElement.find_all('g'):
            if g.get('class') == None:
                backgroundElements.append(str(g))
            elif "question" in g.get('class'):
                if g.get('category') != None and g.get('category') not in includeQuestions:
                    continue
                # Kaarten met een niveau-kenmerk (havo/vwo) alleen de vragen van
                # dat niveau. Vormen zonder kenmerk horen bij allebei.
                if niveau and g.get('niveau') and niveau not in g.get('niveau').split():
                    continue
                answers = []
                for awnser in g.find_all('awnser'):
                    answers.append(awnser.get_text())
                paths = g.find_all('path')

                for path in paths:
                    path.attrs['style'] = ''

                id = g.get('id')

                questions.append(mapQuestion(id, answers, str(paths), g.get('category')))
            elif "foreground" in g.get('class'):
                foregroundElements.append(str(g))
            elif "background" in g.get('class'):
                backgroundElements.append(str(g))

        svgElement = data.find('svg')
        if svgElement.get('viewBox') != None:
            viewBox = svgElement.get('viewBox').split(' ')
            viewBox = (int(viewBox[0]), int(viewBox[1]), int(viewBox[2]), int(viewBox[3]))
        else:
            viewBox = (0, 0, 1000, 1000)

        if sessionMode == 'MultipleChoise':
            sessionMode = 1 #SessionGamemode.MULTIPLECHOICE
        elif sessionMode == 'FillInTheBlank':
            sessionMode = 2 #SessionGamemode.FILLINTHEBLANK
        elif sessionMode == 'ClickTheCountry':
            sessionMode = 3 #SessionGamemode.CLICKTHECOUNTRY

        return mapSession(questions, backgroundElements, foregroundElements, viewBox, sessionMode)
    
class mapQuestion():
    def __init__(self, id:str, answers:list, svg:str, category:str=None):
        self.id = id
        self.answers = answers
        self.svg = svg
        self.tries = 0
        self.timesCorrect = 0
        self.category = category

    @property
    def allAnswers(self):
        # Staan er <awnser>-regels in de kaart, dan gelden alleen die. Het id is
        # dan puur een naam om de vorm mee aan te wijzen, zodat twee vormen
        # dezelfde naam mogen hebben (Sao Paulo is een stad en een deelstaat).
        return self.answers if self.answers else [self.id]

    @property
    def displayName(self) -> str:
        """De naam die de leerling te zien krijgt: de eerste <awnser> uit de
        kaart, en anders het id."""
        return self.answers[0] if self.answers else self.id
