"""Test: wat gebeurt er als mensen tegelijk op een duel klikken?

Draaien vanuit de map `app`:

    python tests/test_duel_tegelijk.py

Elke situatie wordt vele keren met echte threads tegelijk gestart, zodat een
fout in de volgorde ook echt voorkomt.
"""
import os
import sys
import threading

from helpers import Checks, loadApp

loadApp()

from src.duel import DuelManager, DuelPlayer  # noqa: E402

check = Checks()
RONDES = 200


def speler(nummer: int) -> DuelPlayer:
    return DuelPlayer(nummer, f'Speler{nummer}', 1000, 1)


def tegelijk(*taken):
    """Start alle taken op precies hetzelfde moment en wacht tot ze klaar zijn."""
    start = threading.Barrier(len(taken))
    uitkomst = [None] * len(taken)

    def draai(i, taak):
        start.wait()
        try:
            uitkomst[i] = taak()
        except ValueError as e:
            uitkomst[i] = e
    draden = [threading.Thread(target=draai, args=(i, t)) for i, t in enumerate(taken)]
    for d in draden:
        d.start()
    for d in draden:
        d.join()
    return uitkomst


def maak(manager, nummer):
    return manager.createDuel(speler(nummer), 'Europa', 'MultipleChoise', ['Landen'],
                              questionCount=3)


def inHoeveelDuels(manager, userId):
    return sum(1 for d in manager.duels.values()
               if d.state != 'finished' and d.playerFor(userId) is not None)


# --- 1. Twee mensen klikken tegelijk op hetzelfde open duel -----------------
fout = 0
for _ in range(RONDES):
    m = DuelManager()
    duel = maak(m, 1)
    a, b = tegelijk(lambda: m.join(duel, speler(2)), lambda: m.join(duel, speler(3)))
    gelukt = [u for u in (a, b) if not isinstance(u, Exception)]
    if len(gelukt) != 1 or len(duel.players) != 2:
        fout += 1
check('twee tegelijk op hetzelfde duel: precies een komt erin', fout == 0, f'{fout} keer mis')

# --- 2. Twee mensen klikken tegelijk op elkaars duel ------------------------
fout = 0
for _ in range(RONDES):
    m = DuelManager()
    vanA, vanB = maak(m, 1), maak(m, 2)
    tegelijk(lambda: m.join(vanB, speler(1)), lambda: m.join(vanA, speler(2)))
    if inHoeveelDuels(m, 1) > 1 or inHoeveelDuels(m, 2) > 1:
        fout += 1
check('tegelijk op elkaars duel: niemand zit in twee duels', fout == 0, f'{fout} keer mis')

# --- 3. Iemand met een eigen open duel doet mee met dat van een ander -------
m = DuelManager()
eigen = maak(m, 1)
ander = maak(m, 2)
m.join(ander, speler(1))
check('meedoen elders: je eigen open duel verdwijnt', m.getDuel(eigen.code) is None)
try:
    m.join(eigen, speler(3))
    check('daarna kan niemand meer in dat oude duel', False)
except ValueError:
    check('daarna kan niemand meer in dat oude duel', True)

# --- 4. Al in een lopend duel, dan niet ook nog in een tweede ---------------
m = DuelManager()
eerste = maak(m, 1)
m.join(eerste, speler(2))
tweede = maak(m, 3)
try:
    m.join(tweede, speler(2))
    check('wie al in een duel zit, kan niet in een tweede', False)
except ValueError as e:
    check('wie al in een duel zit, kan niet in een tweede', 'al in een' in str(e), str(e))

# --- 5. Terugkomen in je eigen duel blijft werken ---------------------------
m = DuelManager()
duel = maak(m, 1)
m.join(duel, speler(2))
check('terugkomen in je eigen duel mag', m.join(duel, speler(2)).userId == 2)

# --- 6. Het duel start maar een keer, ook als beide spelers tegelijk binnenkomen
fout = 0
for _ in range(RONDES):
    m = DuelManager()
    duel = maak(m, 1)
    m.join(duel, speler(2))
    starts = tegelijk(duel.claimStart, duel.claimStart, duel.claimStart)
    if starts.count(True) != 1:
        fout += 1
check('het aftellen start maar een keer', fout == 0, f'{fout} keer mis')

sys.exit(check.report())
