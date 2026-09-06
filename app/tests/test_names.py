"""Test van het naamfilter. Draaien vanuit de map `app`: python tests/test_names.py"""
import importlib.util
import os
import sys

# Los inladen, zodat er voor een filtertest geen database nodig is.
_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'src', 'names.py')
_spec = importlib.util.spec_from_file_location('names', _path)
names = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(names)
checkName, NameError_ = names.checkName, names.NameError_

# Namen die gewoon moeten kunnen, inclusief een paar die een te grof filter
# ten onrechte tegenhoudt (Nazir, Methorst, Hoera, Fagel).
GOED = ['Floris', 'Sami', 'Joel', 'Joël', 'Jan-Willem', 'Anne Marie', 'de Vries',
        'Lucía', 'Méndez', 'R1ck', 'Sam88', 'J.P', 'Bo', 'Nazir', 'Methorst',
        'Hoera', 'Fagel', 'Cassandra', 'Del Piero', 'Kanaal']

# (naam, stuk van de melding dat we verwachten)
FOUT = [
    ('a', 'minstens'),
    ('x' * 21, 'hooguit'),
    ('123', 'twee letters'),
    ('aaaaa', 'dezelfde tekens'),
    ('<b>Jan</b>', 'alleen letters'),
    ('Jan@Piet', 'alleen letters'),
    ('admin', 'gereserveerd'),
    ('Docent Jansen', 'gereserveerd'),
    ('Ichthus', 'gereserveerd'),
    ('kut', 'niet toestaan'),
    ('K-U-T', 'niet toestaan'),
    ('f.u.c.k', 'niet toestaan'),
    ('FuCk', 'niet toestaan'),
    ('K4nker', 'niet toestaan'),
    ('sh1t', 'niet toestaan'),
    ('kankerjoch', 'niet toestaan'),
    ('hoer', 'niet toestaan'),
    ('neuken', 'niet toestaan'),
]

fails = []


def check(name, cond, extra=''):
    print(('OK   ' if cond else 'FOUT ') + name + ('' if cond else ' :: ' + str(extra)[:200]))
    if not cond:
        fails.append(name)


for naam in GOED:
    try:
        schoon = checkName(naam)
        check(f'toegestaan: {naam!r}', bool(schoon))
    except NameError_ as e:
        check(f'toegestaan: {naam!r}', False, e)

for naam, melding in FOUT:
    try:
        checkName(naam)
        check(f'geweigerd: {naam!r}', False, 'werd toegelaten')
    except NameError_ as e:
        check(f'geweigerd: {naam!r}', melding in str(e), e)

# Spaties en onzichtbare tekens worden opgeschoond, niet geweigerd.
check('spaties opschonen', checkName('  Jan   Piet  ') == 'Jan Piet')
check('onzichtbare tekens eruit', checkName('Jan​​Piet') == 'JanPiet')
check('te lang wordt niet afgekapt maar geweigerd',
      not names.isAcceptable('Een hele lange naam die niet past'))

print('\n' + ('ALLES GOED' if not fails else 'MISLUKT: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
