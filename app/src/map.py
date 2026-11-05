from __future__ import annotations
import copy
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


# Vlakken die land vormen. Worden ze niet gevraagd, dan blijven ze als
# achtergrond op de kaart staan.
DECOR_CATEGORIES = ('Landen', 'Provincies')


def decorFrom(g) -> str:
    """Kopie van een vraaggroep als stille achtergrond: geen id (dat hoort bij
    de vraag), geen antwoorden en niet aanklikbaar."""
    decor = copy.copy(g)
    for attr in ('id', 'category', 'niveau'):
        decor.attrs.pop(attr, None)
    decor['class'] = 'decor'
    for awnser in decor.find_all('awnser'):
        awnser.decompose()
    for path in decor.find_all('path'):
        path.attrs.pop('id', None)
        path.attrs['style'] = ''
    return str(decor)


class SessionGamemode(Enum):
    MULTIPLECHOICE = 1
    FILLINTHEBLANK = 2
    CLICKTHECOUNTRY = 3

# Een oefensessie blijft in het geheugen staan zolang iemand ermee bezig is.
# Zonder opruimen groeit dat tot de server omvalt: een sessie op de wereldkaart
# kost ongeveer 1,6 MB, en op een machine van 1 GB is het na een paar honderd
# sessies op. Een les duurt een lesuur, dus drie uur stilte is ruim genoeg om
# een sessie als verlaten te beschouwen.
MAX_SESSIE_LEEFTIJD = 3 * 60 * 60   # seconden zonder iets te doen
# 250 sessies x ~1,6 MB is ongeveer 400 MB in het ergste geval. Dat past op een
# server van 1 GB met Postgres en Caddy ernaast. Staat de site op een grotere
# machine, dan mag dit getal omhoog.
MAX_SESSIES = 250                   # harde bovengrens, wat er ook gebeurt


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
        self.maxSessions = maxSessions or int(os.getenv('MAX_PRACTICE_SESSIONS', str(MAX_SESSIES)))
        self.maxIdle = maxIdle or int(os.getenv('PRACTICE_SESSION_IDLE_SECONDS', str(MAX_SESSIE_LEEFTIJD)))
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

    def stats(self, window:int=300) -> dict:
        """Wie is er nu bezig? Actief = in de laatste `window` seconden iets gedaan.

        De teller kijkt naar oefensessies, niet naar browservensters. Wie de
        kaart openzet en een kwartier niets doet, telt niet meer mee.
        """
        now = datetime.now()
        perMap = {}
        active = 0
        for session in list(self.sessions.values()):
            if (now - session.lastSeen).total_seconds() > window:
                continue
            active += 1
            name = session.mapName or 'onbekend'
            perMap[name] = perMap.get(name, 0) + 1
        return {
            'active': active,
            'perMap': dict(sorted(perMap.items(), key=lambda kv: -kv[1])),
            'started': len(self.sessions),
            'window': window,
        }

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
        self.lastSeen = self.startTimestamp
        # De laatst beantwoorde vraag, voor het knopje "Klopt dit niet?":
        # {'vraag', 'onderdeel', 'gegeven', 'goed'}. Zie awnserQuestion.
        self.vorigeVraag: dict | None = None
        self.mapName = None
        self.sessionMode = sessionMode
        self.correctThreshold = 0.5
        # Toetsmodus (zie startToets): elke vraag een keer, zonder te zeggen of
        # het goed was, en aan het eind een cijfer.
        self.toets = False
        self.toetsVolgorde: list[int] = []
        self.toetsPositie = 0
        self.toetsAntwoorden: list[dict] = []

    def touch(self):
        """Onthoud dat er zojuist nog iemand met deze sessie bezig was."""
        self.lastSeen = datetime.now()

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
            "totalQuestions": len(self.questions),
            # Voor "x van y gekend" op de startpagina: welke vragen je nu
            # kent (dezelfde codes als op de kaart, dus elke sessie gelijk) en
            # hoeveel vragen de hele kaart heeft op jouw niveau. De browser
            # telt de codes van alle sessies bij elkaar op.
            "gekendIds": [self.hash(q.id) for q in self.questions
                          if self.getQuestionState(q) == "Correct"],
            "kaartTotaal": getattr(self, 'kaartTotaal', None) or len(self.questions),
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


    # ------------------------------------------------------------------
    # Toetsmodus
    # ------------------------------------------------------------------
    def startToets(self, aantal: int | None = None):
        """Maak er een toets van: `aantal` vragen (of alle) in een vaste,
        willekeurige volgorde. Elke vraag komt precies een keer."""
        self.toets = True
        volgorde = list(range(len(self.questions)))
        random.shuffle(volgorde)
        if aantal:
            volgorde = volgorde[:max(1, min(aantal, len(volgorde)))]
        self.toetsVolgorde = volgorde
        self.toetsPositie = 0
        self.toetsAntwoorden = []
        self.currentQuestionIndex = volgorde[0] if volgorde else -1

    @property
    def toetsTotaal(self) -> int:
        return len(self.toetsVolgorde)

    def beantwoordToets(self, awnser, hashed: bool) -> bool:
        """Kijk het antwoord na en onthoud het. Geeft niets terug aan de
        leerling: dat komt pas bij de uitslag."""
        vraag = self.currentQuestion
        goed = self.awnserQuestion(awnser, hashed)
        gegeven = self.vorigeVraag['gegeven']
        self.toetsAntwoorden.append({
            'id': vraag.id, 'vraag': vraag.displayName, 'onderdeel': vraag.category,
            'gegeven': gegeven, 'goed': goed,
        })
        return goed

    def volgendeToetsvraag(self) -> bool:
        """Naar de volgende vraag. True als de toets klaar is."""
        self.toetsPositie += 1
        if self.toetsPositie >= len(self.toetsVolgorde):
            self.finished = True
            return True
        self.currentQuestionIndex = self.toetsVolgorde[self.toetsPositie]
        return False

    def toetsVoortgang(self) -> dict:
        return {'beantwoord': len(self.toetsAntwoorden), 'totaal': self.toetsTotaal}

    def toetsUitslag(self) -> dict:
        """Het cijfer en wat er fout ging. Cijfer zoals op school gebruikelijk:
        1 + 9 x (goed / totaal), op een decimaal."""
        totaal = self.toetsTotaal
        goed = sum(1 for a in self.toetsAntwoorden if a['goed'])
        cijfer = round(1 + 9 * goed / totaal, 1) if totaal else 1.0
        return {
            'goed': goed,
            'totaal': totaal,
            'cijfer': cijfer,
            'voldoende': cijfer >= 5.5,
            'tijd': (datetime.now() - self.startTimestamp).seconds,
            'fouten': [{'vraag': a['vraag'], 'gegeven': a['gegeven'], 'onderdeel': a['onderdeel']}
                       for a in self.toetsAntwoorden if not a['goed']],
        }

    def hash(self, awnser:str):
        if self.antiCheat:
            awnser = hashlib.sha256(str(awnser).encode('utf-8')).hexdigest()
        return awnser
    
    def gegevenAntwoord(self, awnser, hashed: bool) -> str:
        """Wat de leerling antwoordde, leesbaar. Bij aanwijzen komt het
        (gehashte) id van het aangeklikte gebied binnen; zoek op welke plek
        dat was."""
        if hashed:
            namen = {self.hash(q.id): q.displayName for q in self.questions}
            return namen.get(str(awnser), 'een andere plek')
        return str(awnser).strip()[:60]

    def awnserQuestion(self, awnser:int, hashed:bool):
        possibleAwnsers = self.currentQuestion.allAnswers
        vraag = self.currentQuestion
        gegeven = self.gegevenAntwoord(awnser, hashed)
        
        self.currentQuestion.tries += 1

        if hashed:
            # Bij aanwijzen stuurt de browser de id van het gebied door (gehasht),
            # dus de id telt hier altijd mee, ook als er <awnser>-regels zijn.
            awnser = str(awnser)
            possibleAwnsers = [self.hash(a) for a in possibleAwnsers + [self.currentQuestion.id]]
        else:
            awnser = normalizeAnswer(awnser)
            possibleAwnsers = [normalizeAnswer(a) for a in possibleAwnsers]

        goed = awnser in possibleAwnsers
        self.vorigeVraag = {'vraag': vraag.displayName, 'onderdeel': vraag.category,
                            'gegeven': gegeven, 'goed': goed}
        if goed:
            self.score += 1
            self.currentQuestion.timesCorrect += 1
        return goed
        
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
                overslaan = g.get('category') != None and g.get('category') not in includeQuestions
                # Kaarten met een niveau-kenmerk (havo/vwo) alleen de vragen van
                # dat niveau. Vormen zonder kenmerk horen bij allebei.
                if niveau and g.get('niveau') and niveau not in g.get('niveau').split():
                    overslaan = True
                if overslaan:
                    # Een land of provincie die niet gevraagd wordt, is nog wel
                    # land. Zonder deze vorm zou je bij alleen 'Steden' de zee
                    # zien waar Nederland hoort te liggen.
                    if g.get('category') in DECOR_CATEGORIES:
                        backgroundElements.append(decorFrom(g))
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

        newSession = mapSession(questions, backgroundElements, foregroundElements, viewBox, sessionMode)
        newSession.mapName = os.path.splitext(os.path.basename(file))[0]
        return newSession
    
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
