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

# ----------------------------------------------------------------------
# Grote lijsten. Echte namen die moeten kunnen, en pogingen van brugklassers
# die tegengehouden moeten worden. Vul aan als er iets doorheen glipt of als
# een echte naam ten onrechte geweigerd wordt.
# ----------------------------------------------------------------------
voornamen = '''Noah Daan Sem Lucas Levi Finn Milan Luuk Bram Liam Jesse Thijs Ruben Thomas Stijn Lars Niels Jens Gijs Teun Pepijn Hidde Siem Mees Jurre Boaz
Ilyas Adam Rayan Amir Ibrahim Omar Youssef Mohamed Mohammed Ayoub Yassine Ayaan Kenzo Dex Joep Tim Koen Wessel Jelle Kai Jayden Dylan Brian Kevin Mike Rick Dirk
Henk Floris Sami Joel Joël Bas Sebastiaan Casper Jasper Kasper Mathijs Nick Niek Dick Sander Twan Wout Hugo Olivier Vince Senna Mats Tygo Quinten Max
Emma Julia Mila Tess Sophie Zoë Sara Nora Liv Anna Evi Saar Lotte Fenna Lieke Isa Noor Yara Sanne Femke Floor Iris Marit Ilse Romy Demi Kim Esmee Britt
Puck Fleur Roos Maud Sophia Olivia Elif Zeynep Ecrin Hiba Malak Nour Hajar Meryem Ilayda Esra Ezra Fatima Aisha Amira Yasmina Lina Lara Nikki Jessica Vanessa
Melissa Cassandra Tessa Nikita Anouk Gaya Isabel Isabella Alexa Dieuwertje Wietske Wietse Nazir Kutlu Lulof Analiese Janus Titus Lucía Méndez Bo Jip Sep Kees Klaas'''.split()
achternamen = '''de Jong|Jansen|de Vries|van den Berg|van Dijk|Bakker|Janssen|Visser|Smit|Meijer|de Boer|Mulder|de Groot|Bos|Vos|Peters|Hendriks|van Leeuwen|Dekker
|Brouwer|de Wit|Dijkstra|Smits|de Graaf|van der Meer|van der Linden|Kok|Jacobs|de Haan|Vermeulen|van den Heuvel|van der Veen|van den Broek|de Bruijn
|van der Heijden|Schouten|van Beek|Willems|van Vliet|van de Ven|Hoekstra|Maas|Verhoeven|Koster|van Dam|van der Wal|Prins|Blom|Huisman|Peeters
|Kuipers|van Veen|Post|Kuiper|Veenstra|Kramer|van den Brink|Scholten|van Wijk|Postma|Martens|Vink|de Ruiter|Timmermans|Groen|Gerritsen|Jonker
|van Loon|Willemsen|Smeets|de Lange|Bosch|van Dongen|Schipper|de Koning|van der Laan|Driessen|van Doorn|Hermans|Evers|Hofman|Bosman|Wolters
|Sanders|van der Horst|Mertens|Kuijpers|Methorst|Pikkemaat|Drolsma|Poepjes|Homoet|Kontich|Weeda|Rik Anker|el Amrani|Yilmaz|Kaya|Demir|Öztürk|Bouzid'''.replace('\n','').split('|')
bijnamen = ['TopoKoning','Gamer Bas','FlorisDeBaas','SuperSanne','Pizza Liefhebber','Ninja Noah','Kapitein Koek','De Snelle Sem','Brugger12','Sam88','R1ck',
            'Topo Tijger','Kaartlezer','Aardrijkskunde fan','Wereldbol','Noordpool','Lucas_2012','xXLucasXx','Pikachu','Knappe Koen','Hoera','Kanaal',
            'Cassie','Kebab Koning','Voetbal Fenna','Paarden meisje','Snelle Jelle','Rik Anker','Bas de Wit','Jan-Willem','Anne Marie','J.P','Del Piero']
goed = voornamen + achternamen + bijnamen + [f'{v} {a}' for v, a in zip(voornamen[::3], achternamen)]
fout = '''kut|K-U-T|f.u.c.k|FuCk|K4nker|kaaanker|k.a.n.k.e.r|kan ker|kankerjoch|KANKERLIJER|Tyfuslijer|tering|klere|H1tler|H1tl3r|Hitler|h i t l e r|Adolf Hitler|hit ler|reltih|Nazi|N4zi
|Heil|Sieg Heil|kkk|KKK lid|Jan1488|swastika|Holocaust|Taliban|Jihad|neger|n1gger|Nigga|nikker|kaffer|Makak|spleetoog|faggot|flikker|homo|Homo Jan|gayboy|retard|Mongool|mongo|downie
|hoer|Hoerenjong|slet|sloerie|kutwijf|lulhannes|Pikkie|pikachuuuu|piemel|penis|p3n1s|Vagina|neuken|neuker|Seks|sexy|Sexybabe|porno|pornhub|hentai|milf|dildo|tieten|boobs|geil|horny
|onlyfans|pedo|pedofiel|zelfmoord|suicide|kys|Kill jezelf|killer|moordenaar|Terrorist|cocaine|coke|heroine|wiet|weed|xtc|mdma|stoned|shit|sh1t|bitch|b1tch|asshole|klootzak|Kloothommel
|debiel|idioot|sukkel|loser|trut|teef|eikel|poep|poepjes kont|drol|stront|schijt|pis|reet|admin|Admin123|Beheerder|Docent|Juf Anja|Meneer Jansen|Meester Bram|Mevrouw de Vries|Mr Bean
|Rector|Ichtopia|Ichthus|Moderator|Systeem|Anoniem|test|asdfgh|qwerty|qwertyuiop|zxcvbn|jkljkl|hahahaha|hahaha|lololol|abcabcabc|xkcdq|bhjgkl|bbbbbb|aaa|Floris1234567|12345ab|06 12345678
|insta jan|snap floor|tiktok sem|www.jan.nl|jan.com|kаnker|Кanker|fuuuck|phuck|phuk|vvhore|wh0re|Ass|C0ck|Dick Head|Lul|Fu|stfu|WTF|satan|lucifer'''.replace('\n','').split('|')
pogingen = ['K a n k e r', 'kanker_', 'Kanker2012', 'xXkankerXx', 'Hitlerjugend', 'Hit-ler', 'H.i.t.l.e.r', 'Nazi_Jan', 'Neger123',
        'Nikkertje', 'Mongooltje', 'Kutje', 'Ku7', 'Kut3', 'kutt', 'Kuttt', 'KuT', 'k-u-t-j-e', 'Lul123', 'Fvck', 'Fvcker', 'Ni99er', 'Kkanker',
        'H0er', 'Pedobear', 'Kinderneuker', 'Tyfushond', 'Sukkeltje', 'Jodenhater', 'Moslimhater', 'Homohater', 'Kankerhomo', 'Teringjong',
        'Klerelijer', 'Pokkenjong', 'Pik-man', 'Kut_Floris', 'Floris_Kut', 'FlorisKut', 'kutFloris', 'Juf_Anja', 'Juffie', 'Mr.Jansen',
        'Docent123', 'D0cent', 'Adm1n', 'Leraar Bas', 'Meneer', 'Sexmachine', 'Seksbom', 'Geile Gerrit', 'Lekker ding', 'Hot Babe',
        'Tietenman', 'Penisman', 'Pornoster', 'XXX', 'xXx', '69', 'Nr69', 'Jan69', 'Sixtynine', '420', 'Wiet420', 'Snoop420', 'Hasj',
        'Coke Kees', 'Kys Jan', 'Kill Me', 'Dood Gaan', 'Bomb', 'Allahu Akbar', 'Hamas', 'IS strijder', 'Osama',
        'Stalin', 'Mussolini', 'Breivik', 'Hakenkruis', 'SS Jan', 'NSB', 'Zieg Heil', 'Seig Heil', 'Kanker Marokkaan', 'Kut Turk',
        'Neger Jan', 'Zwarte Piet', 'Roetmop', 'Bosneger', 'Apenkop', 'Mongool Jan', 'Spast', 'Autist', 'Downie Jan']
mild = ['Speed Freak', 'Aap Jan', 'Hond', 'Ezel', 'Kech', 'Gekkie', 'Malloot', 'Dombo', 'Snotneus', 'Lekker Bezig', 'Kaas', 'Koekie', 'Bink', 'Baas', 'Patser', 'Boef']

onterechtGeweigerd = [x for x in goed if not names.isAcceptable(x)]
check(f'{len(goed)} echte namen en bijnamen toegestaan', not onterechtGeweigerd, onterechtGeweigerd)
onterechtToegelaten = [x for x in fout + pogingen if names.isAcceptable(x)]
check(f'{len(fout) + len(pogingen)} pogingen tegengehouden', not onterechtToegelaten, onterechtToegelaten)
check('milde bijnamen (Hond, Dombo, Boef) mogen', all(names.isAcceptable(x) for x in mild),
      [x for x in mild if not names.isAcceptable(x)])

# Namen die te veel op elkaar lijken, voor wie op de ranglijst kijkt.
sleutel = names.naamSleutel
check('F1oris, FIoris, Flor1s en floris zijn dezelfde',
      len({sleutel(x) for x in ['Floris', 'F1oris', 'FIoris', 'Flor1s', 'floris', 'FLORIS', 'Flo-ris']}) == 1)
check('Floris en Flora zijn verschillend', sleutel('Floris') != sleutel('Flora'))

# Spaties en onzichtbare tekens worden opgeschoond, niet geweigerd.
check('spaties opschonen', checkName('  Jan   Piet  ') == 'Jan Piet')
check('onzichtbare tekens eruit', checkName('Jan​​Piet') == 'JanPiet')
check('te lang wordt niet afgekapt maar geweigerd',
      not names.isAcceptable('Een hele lange naam die niet past'))

print('\n' + ('ALLES GOED' if not fails else 'MISLUKT: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
