"""Dump the main world's islands (uid, name, world pos) from worldData/piratesWorld.py.
Run from the client tree: ppython <harness>/islands.py"""
import sys, os, builtins
builtins.__dev__ = False
sys.path.insert(0, os.getcwd())
from pirates.leveleditor.worldData import piratesWorld as W

objs = W.objectStruct['Objects']
for wuid, w in objs.items():
    for uid, o in w.get('Objects', {}).items():
        if o.get('Type') == 'Island':
            p = o.get('Pos')
            print('%-28s %-24s %8.0f %8.0f  %s' % (uid, o.get('Name', ''), p[0], p[1], o.get('File', '')))
