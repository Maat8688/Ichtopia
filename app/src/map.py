from __future__ import annotations
import werkzeug.security
import hashlib
import random
from enum import Enum
from bs4 import BeautifulSoup
import sys
from datetime import datetime

class SessionGamemode(Enum):
    MULTIPLECHOICE = 1
    FILLINTHEBLANK = 2
    CLICKTHECOUNTRY = 3

class SessionManager():
    def __init__(self):
        self.sessions = {}
    
    def createSession(self, session:mapSession) -> str:
        id = werkzeug.security.generate_password_hash(str(datetime.now()))
        self.sessions[id] = session
        return id
    
    def getSession(self, id:str) -> mapSession:
        return self.sessions[id]
    
    def deleteSession(self, id:str):
        del self.sessions[id]

class mapSession():
    def __init__(self, questions:list[mapQuestion], backgroundElements:list, foregroundElements:list, viewBox:tuple=(0, 0, 1000, 1000), sessionMode:SessionGamemode=SessionGamemode.MULTIPLECHOICE):
        self.questions = questions
        self.backgroundElements = backgroundElements
        self.foregroundElements = foregroundElements
        self.viewBox = viewBox
        self.currentQuestionIndex = 0
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
            possibleAwnsers = [self.hash(awnser) for awnser in possibleAwnsers]
        else:
            awnser = awnser.upper()
            possibleAwnsers = [awnser.upper() for awnser in possibleAwnsers]
        
        print(awnser, file=sys.stderr)
        print(possibleAwnsers, file=sys.stderr)
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
    def fromSVG(file:str, sessionMode:SessionGamemode|str=SessionGamemode.MULTIPLECHOICE, includeQuestions:list[str]=[]) -> mapSession:
        with open(file, 'r') as f:
            svg = f.read()
        
        data = BeautifulSoup(svg, 'xml')
        mapElement = data.find('g', id='map')
        questions = []
        backgroundElements = []
        foregroundElements = []
        #loop trough all g in map
        print(includeQuestions, file=sys.stderr)
        for g in mapElement.find_all('g'):
            if g.get('class') == None:
                backgroundElements.append(str(g))
            elif "question" in g.get('class'):
                if g.get('category') != None and g.get('category') not in includeQuestions:
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
        return self.answers + [self.id]
