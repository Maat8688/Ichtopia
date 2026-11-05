"""Genereert Noord-Amerika.svg en Zuid-Amerika.svg uit Natural Earth (publiek domein).
Structuur gelijk aan de bestaande kaarten van de site."""
import json, math, unicodedata, sys, io, contextlib
sys.setrecursionlimit(20000)
sys.path.insert(0,'.')
with contextlib.redirect_stdout(io.StringIO()):
    exec(open('lijsten.py').read())


# Namen die op twee verschillende vormen slaan. De eerste <awnser> is wat de
# leerling te zien krijgt, de rest wordt ook goedgerekend bij het typen.
VERDUIDELIJK = {
    ('Uruguay', 'Wateren'):    'Uruguay (rivier)',
    ('Paraná', 'Wateren'):     'Paraná (rivier)',
    ('Paraná', 'Provincies'):  'Paraná (deelstaat)',
    ('São Paulo', 'Provincies'): 'São Paulo (deelstaat)',
    ('São Paulo', 'Plaatsen'): 'São Paulo (stad)',
}

def N(t):
    t = unicodedata.normalize('NFD', str(t))
    return ''.join(c for c in t if not unicodedata.combining(c)).lower()
def K(t): return ''.join(c for c in N(t) if c.isalnum())

VELDEN = ['NAME','NAME_EN','NAME_NL','NAMEALT','NAMEASCII','NAME_ES','NAME_PT','ADMIN','SUBUNIT',
          'name','name_en','name_nl','name_alt','name_es','name_pt','admin']
_c = {}
def laag(f):
    if f not in _c:
        d = json.load(open('ne/'+f+'.geojson'))
        idx = {}
        for feat in d['features']:
            for v in VELDEN:
                w = feat['properties'].get(v)
                if w and str(w).lower() not in ('none','null'): idx.setdefault(K(w), []).append(feat)
        _c[f] = (idx, d['features'])
    return _c[f]

LAGEN = {
 'Landen':     ['ne_50m_admin_0_countries','ne_10m_admin_0_map_subunits'],
 'Provincies': ['ne_10m_admin_1_states_provinces'],
 'Gebergten':  ['ne_10m_geography_regions_polys'],
 'Plaatsen':   ['ne_10m_populated_places'],
 'Wateren':    ['ne_10m_lakes','ne_50m_lakes','ne_10m_rivers_lake_centerlines',
                'ne_50m_rivers_lake_centerlines','ne_10m_geography_marine_polys',
                'ne_50m_geography_marine_polys','ne_10m_playas'],
}
VERTAAL = {'Verenigde Staten':'United States of America','Frans-Guyana':'French Guiana',
 'Argentinië':'Argentina','Brazilië':'Brazil','Chili':'Chile','Trinidad en Tobago':'Trinidad and Tobago',
 'Falklandeilanden':'Falkland Islands','Lake Superior (Bovenmeer)':'Lake Superior',
 'Michiganmeer':'Lake Michigan','Titicacameer':'Lago Titicaca','Amazone':'Amazonas','Rio Negro':'Negro',
 'Coast Ranges (Kustgebergte)':'COAST RANGES','Appalachen':'APPALACHIAN MTS.',
 'Coloradoplateau':'COLORADO PLATEAU','Hoogland van Guyana':'GUIANA HIGHLANDS',
 'Hoogland van Brazilië':'BRAZILIAN HIGHLANDS','Rocky Mountains':'ROCKY MOUNTAINS','Andes':'ANDES',
 'Sierra Nevada':'SIERRA NEVADA','Straat van Magallanes':'Strait of Magellan','Parnaiba':'Parnaíba',
 'Atlantische Oceaan':'North Atlantic Ocean','Grote Oceaan':'North Pacific Ocean',
 'Caribische Zee':'Caribbean Sea','Golf van Mexico':'Gulf of Mexico',
 'Golf van California':'Gulf of California','Paraná':'Parana','Mexico-Stad':'Mexico City',
 'La Paz/El Alto':'La Paz'}
# Salinas Grandes staat naamloos in de zoutvlaktelaag; deze drie vormen samen het gebied.
SALINAS = [18, 19, 32]

def vind_stad(naam, kader):
    """Steden komen vaak meermaals voor (Leon in Mexico en in Spanje). Kies
    daarom alleen kandidaten binnen het kaartkader, en daarvan de grootste."""
    lon0, lon1, lat0, lat1 = kader
    idx, _ = laag('ne_10m_populated_places')
    kandidaten = []
    for kand in (naam, VERTAAL.get(naam), naam.split('/')[0].strip()):
        if kand: kandidaten += idx.get(K(kand), [])
    binnen = []
    for f in kandidaten:
        c = f['geometry']['coordinates']
        lo, la = (c[0], c[1]) if isinstance(c[0], (int, float)) else (c[0][0], c[0][1])
        if lon0 <= lo <= lon1 and lat0 <= la <= lat1:
            p = f['properties']
            inw = max(p.get('POP_MAX') or 0, p.get('POP_EST') or 0, p.get('GN_POP') or 0)
            binnen.append((inw, f))
    if not binnen: return None
    return max(binnen, key=lambda t: t[0])[1]['geometry']


def in_kader(geom, kader):
    """Ligt deze vorm (deels) binnen het kaartkader?"""
    lon0, lon1, lat0, lat1 = kader
    xs, ys = [], []
    def loop(c):
        if isinstance(c[0], (int, float)): xs.append(c[0]); ys.append(c[1])
        else: [loop(x) for x in c]
    loop(geom['coordinates'])
    return not (max(xs) < lon0 or min(xs) > lon1 or max(ys) < lat0 or min(ys) > lat1)


def vind(naam, rubriek, kader=None):
    if rubriek == 'Plaatsen' and kader:
        return vind_stad(naam, kader)
    if naam == 'Salinas Grandes':
        _, feats = laag('ne_10m_playas')
        return {'type':'MultiPolygon','coordinates':[
            f['geometry']['coordinates'] if f['geometry']['type']=='Polygon' else c
            for i in SALINAS for f in [feats[i]]
            for c in ([f['geometry']['coordinates']] if f['geometry']['type']=='Polygon'
                      else f['geometry']['coordinates'])]}
    for f in LAGEN[rubriek]:
        idx, _ = laag(f)
        for kand in (naam, VERTAAL.get(naam), naam.split('(')[0].strip(), naam.split('/')[0].strip()):
            if not kand: continue
            for feat in idx.get(K(kand), []):
                if kader is None or in_kader(feat['geometry'], kader):
                    return feat['geometry']
    return None

def rdp(pts, eps):
    if len(pts) < 3: return pts
    (x0,y0), (x1,y1) = pts[0], pts[-1]
    dx, dy = x1-x0, y1-y0
    nn = math.hypot(dx,dy) or 1e-9
    verst, imax = 0, 0
    for i,(x,y) in enumerate(pts[1:-1],1):
        d = abs(dy*x - dx*y + x1*y0 - y1*x0)/nn
        if d > verst: verst, imax = d, i
    if verst <= eps: return [pts[0], pts[-1]]
    return rdp(pts[:imax+1], eps)[:-1] + rdp(pts[imax:], eps)

def rdp_ring(pts, eps):
    """Vereenvoudig een gesloten ring. Recht-toe-recht-aan RDP werkt hier niet:
    begin- en eindpunt vallen samen, dus lijkt elk punt op de lijn te liggen.
    Daarom eerst splitsen bij het punt dat het verst van het begin ligt."""
    if len(pts) < 4: return pts
    if pts[0] == pts[-1]: pts = pts[:-1]
    if len(pts) < 4: return pts
    i = max(range(len(pts)), key=lambda k: (pts[k][0]-pts[0][0])**2 + (pts[k][1]-pts[0][1])**2)
    if i == 0: return pts
    eerste = rdp(pts[:i+1], eps)
    tweede = rdp(pts[i:] + [pts[0]], eps)
    return eerste[:-1] + tweede[:-1]


def bouw(bestand, items, kader, extra_vertaling=None, eps=0.45, breed=900.0):
    geoms = {}
    ontbreekt = []
    if extra_vertaling: VERTAAL.update(extra_vertaling)
    for naam, rub, niveau in items:
        g = vind(naam, rub, kader)
        (geoms.__setitem__((naam,rub), (g, niveau)) if g else ontbreekt.append((naam,rub)))
    if ontbreekt: print('  NIET GEVONDEN:', ontbreekt)
    lon0, lon1, lat0, lat1 = kader
    latm = math.radians((lat0+lat1)/2)
    schaal = breed/((lon1-lon0)*math.cos(latm))
    hoog = (lat1-lat0)*schaal
    def P(lon,lat): return ((lon-lon0)*math.cos(latm)*schaal, (lat1-lat)*schaal)

    def knip(pts, gesloten):
        """Snijd een vorm af op de rand van de kaart (Sutherland-Hodgman)."""
        R = 4.0
        vlak = [(-R,-R), (breed+R,-R), (breed+R,hoog+R), (-R,hoog+R)]
        mid = (breed/2, hoog/2)
        def kruis(p, a, b):
            return (b[0]-a[0])*(p[1]-a[1]) - (b[1]-a[1])*(p[0]-a[0])
        def binnen(p, a, b):
            # 'binnen' is de kant waar het midden van de kaart ligt
            return kruis(p, a, b) * kruis(mid, a, b) >= 0
        def snij(p, q, a, b):
            x1,y1,x2,y2 = p[0],p[1],q[0],q[1]; x3,y3,x4,y4 = a[0],a[1],b[0],b[1]
            n = (x1-x2)*(y3-y4)-(y1-y2)*(x3-x4)
            if abs(n) < 1e-12: return q
            t = ((x1-x3)*(y3-y4)-(y1-y3)*(x3-x4))/n
            return (x1+t*(x2-x1), y1+t*(y2-y1))
        uit = pts
        for i in range(4):
            a, b = vlak[i], vlak[(i+1) % 4]
            in_, uit = uit, []
            if not in_: break
            vorig = in_[-1] if gesloten else None
            for j, punt_ in enumerate(in_):
                if j == 0 and not gesloten: vorig = punt_
                if binnen(punt_, a, b):
                    if vorig is not None and not binnen(vorig, a, b): uit.append(snij(vorig, punt_, a, b))
                    uit.append(punt_)
                elif vorig is not None and binnen(vorig, a, b):
                    uit.append(snij(vorig, punt_, a, b))
                vorig = punt_
        return uit

    def ringen(g):
        t, c = g['type'], g['coordinates']
        if t == 'Point': return [('punt', P(*c[:2]))]
        if t == 'MultiPoint': return [('punt', P(*c[0][:2]))]
        uit = []
        stukken = c if t.startswith('Multi') else [c]
        for st in stukken:
            lijnen = st if t.endswith('Polygon') else [st]
            for ring in lijnen:
                pts = [P(x,y) for x,y in (ring if isinstance(ring[0], list) else [ring])]
                gesloten = t.endswith('Polygon')
                pts = rdp_ring(pts, eps) if gesloten else rdp(pts, eps)
                pts = knip(pts, gesloten)
                if len(pts) >= (3 if gesloten else 2):
                    uit.append(('vlak' if gesloten else 'lijn', pts))
        return uit

    groepen, tel = [], {}
    # Tekenvolgorde: land onderop, dan provincies en gebergten, dan rivieren en
    # zeeen, en de steden bovenop. Anders dekt een landvorm de stadsstippen af.
    VOLGORDE = {'Landen':1, 'Provincies':2, 'Gebergten':3, 'Wateren':4, 'Plaatsen':5}

    def is_zee(naam, rub):
        """Oceanen en zeeen zijn zo groot dat ze het land zouden afdekken.
        Ze gaan onderop, zodat je ze kunt aanklikken zonder landen te blokkeren."""
        if rub != 'Wateren': return False
        g = geoms[(naam, rub)][0]
        for soort, pts in ringen(g):
            if soort != 'vlak': continue
            xs = [x for x,_ in pts]; ys = [y for _,y in pts]
            if (max(xs)-min(xs))*(max(ys)-min(ys)) > 0.008*breed*hoog: return True
        return False

    def rang(sleutel):
        naam, rub = sleutel
        return (0 if is_zee(naam, rub) else VOLGORDE[rub], naam)

    for (naam, rub), (g, niveau) in sorted(geoms.items(), key=lambda t: rang(t[0])):
        vormen = ringen(g)
        id_ = ''.join(ch for ch in N(naam).replace(' ','-').replace('/','-') if ch.isalnum() or ch=='-')
        if rub in ('Plaatsen',): id_ += ''
        elif (naam, ) and sum(1 for (n2,_) in geoms if n2 == naam) > 1: id_ += '-' + rub.lower()
        klasse = {'Plaatsen':'city','Wateren':'water','Gebergten':'gebergte'}.get(rub,'land')
        binnen = []
        for soort, p in vormen:
            if soort == 'punt':
                # Als pad en niet als <circle>: de site leest alleen <path> uit de kaart.
                cx, cy, r = p[0], p[1], 3.4
                binnen.append(f'      <path d="M {cx-r:.2f},{cy:.2f} a {r},{r} 0 1,0 {2*r},0 '
                              f'a {r},{r} 0 1,0 {-2*r},0 Z"/>')
            elif soort == 'vlak':
                # Zeeen en oceanen zijn enorm. Ze krijgen een eigen klasse zodat ze
                # de blauwe ondergrond niet overschilderen zolang ze niet gevraagd zijn.
                xs = [x for x,_ in p]; ys = [y for _,y in p]
                groot = (max(xs)-min(xs))*(max(ys)-min(ys)) > 0.008*breed*hoog
                kl = ' class="zeevlak"' if (rub == 'Wateren' and groot) else ''
                binnen.append(f'      <path{kl} d="M ' + ' L '.join(f'{x:.1f},{y:.1f}' for x,y in p) + ' Z"/>')
            else:
                # Een rivier is een haarlijn. Daaronder komt een brede onzichtbare
                # kopie, anders is hij vrijwel niet aan te klikken.
                d = 'M ' + ' L '.join(f'{x:.1f},{y:.1f}' for x,y in p)
                binnen.append(f'      <path class="raakvlak" d="{d}"/>')
                binnen.append(f'      <path class="lijn" d="{d}"/>')
        toon = VERDUIDELIJK.get((naam, rub))
        namen = [toon, naam] if toon else [naam]
        regels = ''.join(f'      <awnser>{n}</awnser>\n' for n in namen)
        groepen.append(f'    <g id="{id_}" class="{klasse} question" category="{rub}" niveau="{niveau}">\n'
                       + regels + '\n'.join(binnen) + '\n    </g>')
        tel[rub] = tel.get(rub,0)+1

    # achtergrond: alle landen in beeld, niet aanklikbaar
    _, landen = laag('ne_50m_admin_0_countries')
    acht = []
    for f in landen:
        d = ringen(f['geometry'])
        stukjes = [p for s,p in d if s=='vlak' and any(0<=x<=breed and 0<=y<=hoog for x,y in p)]
        for p in stukjes:
            acht.append('      <path d="M ' + ' L '.join(f'{x:.1f},{y:.1f}' for x,y in p) + ' Z"/>')
    # De zee is de ondergrond van de hele kaart; het land ligt daar bovenop. De
    # oceaanvormen van Natural Earth zijn labelvlakken, geen echte kustlijnen,
    # dus die dienen alleen als klikgebied en krijgen dezelfde kleur als de zee.
    svg = (f'<?xml version="1.0" encoding="utf-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
           f'width="{breed:.0f}" height="{hoog:.0f}" viewBox="0 0 {breed:.0f} {hoog:.0f}">\n  <g id="map">\n'
           f'    <g class="background">\n      <rect class="zee" width="{breed:.0f}" height="{hoog:.0f}"/>\n'
           + '\n'.join(acht) + '\n    </g>\n'
           + '\n'.join(groepen) + '\n  </g>\n</svg>\n')
    open(bestand,'w').write(svg)
    print(f'  {bestand}: {len(groepen)} vormen, {len(acht)} achtergrondvormen, {len(svg)//1024} kB, {breed:.0f}x{hoog:.0f}')
    print(f'    {tel}')

print('Noord-Amerika:')
bouw('Noord-Amerika.svg', noord(), (-172, -50, 6, 84),
     {'Atlantische Oceaan':'North Atlantic Ocean', 'Grote Oceaan':'North Pacific Ocean'})
print('Zuid-Amerika:')
bouw('Zuid-Amerika.svg', zuid(), (-82, -33, -56, 14),
     {'Atlantische Oceaan':'South Atlantic Ocean', 'Grote Oceaan':'South Pacific Ocean'})

# ---------------------------------------------------------------------------
# Hoe je dit draait
#
#   Deze kaarten zijn gemaakt uit Natural Earth (naturalearthdata.com), publiek
#   domein. Download de benodigde lagen naar een map 'ne/' naast dit script:
#
#     https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/<laag>.geojson
#
#   met <laag> uit LAGEN hierboven, plus ne_50m_admin_0_countries en
#   ne_10m_populated_places. Draai daarna: python3 genereer_amerika.py
#
#   De vragenlijsten komen uit de topografiedocumenten van de sectie
#   aardrijkskunde (4 havo en 4 vwo) via lijsten.py.
# ---------------------------------------------------------------------------
