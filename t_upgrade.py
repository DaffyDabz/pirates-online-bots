"""Offline test of s_upgrade.pick + have (UPG1, 11-21): the story pirate's biggest ship for his level and gold.
Prices and levels as boats' EVERY-START rows logged them from the game (11-20/21).
Run: python3.9 t_upgrade.py <dir holding s_upgrade.py>"""
import os, sys

sys.path.insert(0, os.path.abspath(sys.argv[1]))
import s_upgrade as U

COST = {1: 100, 11: 300, 21: 800, 2: 1000, 12: 3500, 22: 5000, 3: 20000, 13: 40000, 23: 60000}
LVL = {1: 0, 11: 0, 21: 0, 2: 5, 12: 5, 22: 5, 3: 15, 13: 15, 23: 15}
pick = lambda g, l: U.pick(g, l, COST.get, LVL.get)
assert pick(24068, 15) == 3          # MAIN5's pirate after the level word: the War Sloop, as the brain said
assert pick(24068, 7) == 22          # without the word: the Frigate
assert pick(70000, 15) == 23
assert pick(50, 15) is None
assert U.pick(24068, 15, lambda c: None, LVL.get) is None
ships = [(100000598, 1, 'Dark-sail King', '')]
assert U.have(ships, 3) is None      # a Light Sloop is not a War Sloop: buy
assert U.have(ships + [(100000900, 3, 'x', '')], 3) == 100000900
assert U.have(ships + [(100000901, 23, 'x', '')], 3) == 100000901    # a bigger one is kept
assert U.have([(100000173, 23, 'x', '')], 3) is None                  # never his ship
print('upgrade ok')
