"""Offline test of s_activities.tradeIn (row 18, 11-22). TRADEUP2: his Light Sloop (bought by TRADEUP1) showed state ''
after the server restart (setGameState is not a db field), tradeIn wanted 'Off', so he tried to buy a 4th ship and
failed before O'Malley's Upgrade was ever pressed. A ship with state '' / None is in its bottle; one at sea is not.
Run: python3.9 t_tradein.py <dir holding s_activities.py>"""
import ast, os, sys

D = os.path.abspath(sys.argv[1])
src = open(os.path.join(D, 's_activities.py'), encoding='utf-8').read()
tree = ast.parse(src)
ns = {}
for node in tree.body:     # just the constants and the pure function: s_activities imports the game at the top
    if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') in ('KEEP_SHIPS', 'PUT_AWAY') for t in node.targets):
        exec(compile(ast.Module([node], []), 's_activities', 'exec'), ns)
    if isinstance(node, ast.FunctionDef) and node.name == 'tradeIn':
        exec(compile(ast.Module([node], []), 's_activities', 'exec'), ns)
tradeIn = ns['tradeIn']
L1, L2 = 1, 2
# TRADEUP2's own TRADE-START list (11-22 03:36)
ships = [(100001055, 1, 'Scarlet Hawk', '', []), (100000632, 1, 'Riptide Cutter', ''), (100000043, 1, 'Red Leopard', '')]
ships = [s if len(s) == 5 else s + ([],) for s in ships]
got = tradeIn(ships, L1)
assert got == 100001055, 'TRADEUP2: no sloop to trade in (%s); state %r is a ship in its bottle' % (got, ships[0][3])
assert tradeIn([(5, L1, 'a', None, [])], L1) == 5
assert tradeIn([(5, L1, 'a', 'Off', [])], L1) == 5
for sea in ('ShipPilot', 'InBattle', 'Sunk', 'Docked'):
    assert tradeIn([(5, L1, 'a', sea, [])], L1) is None, sea                        # out at sea: not offered
assert tradeIn([(100000043, L1, 'kept', '', [])], L1) is None                     # a kept ship never
assert tradeIn([(100000173, L1, 'kept', 'Off', [])], L1) is None
assert tradeIn([(5, L2, 'sloop', '', [])], L1) is None                            # not a Light Sloop
assert "in PUT_AWAY, 15, 'new sloop owner view'" in src, 'buySloop still waits for exactly Off'
print('tradein ok')
