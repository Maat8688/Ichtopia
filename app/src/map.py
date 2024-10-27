from __future__ import annotations
import werkzeug.security
import random
from enum import Enum
from bs4 import BeautifulSoup
import sys

class mapSession():
    def __init__(self, questions:list[mapQuestion], backgroundElements:list, viewBox:tuple=(0, 0, 1000, 1000)):
        self.questions = questions
        self.backgroundElements = backgroundElements
        self.viewBox = (0, 0, 1000, 1000)
        self.currentQuestion = 0
        self.score = 0
        self.totalQuestions = 0
        self.finished = False
        self.antiCheat = False
        self.hashSalt = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890', k=16))

    @staticmethod
    def fromSVG(file:str):
        with open(file, 'r') as f:
            svg = f.read()
        
        data = BeautifulSoup(svg, 'xml')
        mapElement = data.find('g', id='map')
        questions = []
        backgroundElements = []
        allData = mapElement
        #loop trough all g in map
        for g in mapElement.find_all('g'):
            if g.get('class') == None:
                backgroundElements.append(str(g))
            elif "question" in g.get('class'):
                answers = []
                for text in g.find_all('text'):
                    answers.append(text.get_text())
                paths = g.find_all('path')
                questions.append(mapQuestion(answers, str(paths)))
            else:
                backgroundElements.append(str(g))
            
        return mapSession(questions, backgroundElements)
    
class mapQuestion():
    def __init__(self, answers:list, svg:str):
        self.answers = answers
        self.svg = svg
