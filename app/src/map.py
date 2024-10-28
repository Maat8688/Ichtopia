from __future__ import annotations
import werkzeug.security
import random
from enum import Enum
from bs4 import BeautifulSoup
import sys
from datetime import datetime

class SessionManager():
    def __init__(self):
        self.sessions = {}
    
    def createSession(self, session:mapSession):
        id = werkzeug.security.generate_password_hash(str(datetime.now()))
        self.sessions[id] = session
        return id
    
    def getSession(self, id:str):
        print(self.sessions, file=sys.stderr)
        print(id, file=sys.stderr)
        return self.sessions[id]
    
    def deleteSession(self, id:str):
        del self.sessions[id]

class mapSession():
    def __init__(self, questions:list[mapQuestion], backgroundElements:list, viewBox:tuple=(0, 0, 1000, 1000)):
        self.questions = questions
        self.backgroundElements = backgroundElements
        self.viewBox = viewBox
        self.currentQuestion = 0
        self.score = 0
        self.finished = False
        self.antiCheat = True
        self.startTimestamp = datetime.now()

    def getViewBox(self):
        return ' '.join(map(str, self.viewBox))
    
    @property
    def totalGuesses(self):
        return sum([question.tries for question in self.questions])
    
    def hashAwnser(self, awnser:str):
        if self.antiCheat:
            awnser = werkzeug.security.generate_password_hash(awnser)
        return awnser
    
    def awnserQuestion(self, awnser:int, hashed:bool):
        possibleAwnsers = self.questions[self.currentQuestion].answers + [self.questions[self.currentQuestion].id]
        
        self.questions[self.currentQuestion].tries += 1

        awnserCorrect = False

        if hashed:
            for possibleAwnser in possibleAwnsers:
                if werkzeug.security.check_password_hash(awnser, possibleAwnser):
                    awnserCorrect = True
        else:
            if awnser in possibleAwnsers:
                awnserCorrect = True
        
        if awnserCorrect:
            self.score += 1
            self.questions[self.currentQuestion].timesCorrect += 1
            return True
        else:
            return False
        
    def nextQuestion(self):
        possibleQuestions = []
        for i, question in enumerate(self.questions):
            if question.timesCorrect == 0:
                possibleQuestions.append(i)
        if len(possibleQuestions) == 0:
            self.finished = True
            return True
        self.currentQuestion = random.choice(possibleQuestions)

    @staticmethod
    def fromSVG(file:str):
        with open(file, 'r') as f:
            svg = f.read()
        
        data = BeautifulSoup(svg, 'xml')
        mapElement = data.find('g', id='map')
        questions = []
        backgroundElements = []
        #loop trough all g in map
        for g in mapElement.find_all('g'):
            if g.get('class') == None:
                backgroundElements.append(str(g))
            elif "question" in g.get('class'):
                answers = []
                for text in g.find_all('text'):
                    answers.append(text.get_text())
                paths = g.find_all('path')

                for path in paths:
                    path.attrs['style'] = ''

                id = g.get('id')

                questions.append(mapQuestion(id, answers, str(paths)))
            else:
                backgroundElements.append(str(g))

        svgElement = data.find('svg')
        if svgElement.get('viewBox') != None:
            viewBox = svgElement.get('viewBox').split(' ')
            viewBox = (int(viewBox[0]), int(viewBox[1]), int(viewBox[2]), int(viewBox[3]))
        else:
            viewBox = (0, 0, 1000, 1000)

        return mapSession(questions, backgroundElements, viewBox)
    
class mapQuestion():
    def __init__(self, id:str, answers:list, svg:str):
        self.id = id
        self.answers = answers
        self.svg = svg
        self.tries = 0
        self.timesCorrect = 0
