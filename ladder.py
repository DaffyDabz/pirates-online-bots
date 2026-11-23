import sys, os, builtins
builtins.__dev__ = False
sys.path.insert(0, os.getcwd())
from pirates.quest import QuestLadderDB, QuestDB
from pirates.quest.QuestDNA import QuestDNA
ms = QuestLadderDB.FameQuestLadderDict['MainStory'] if hasattr(QuestLadderDB,'FameQuestLadderDict') and 'MainStory' in QuestLadderDB.FameQuestLadderDict else None
if ms is None:
    for k in dir(QuestLadderDB):
        v = getattr(QuestLadderDB,k)
        if isinstance(v, dict) and 'MainStory' in v: ms = v['MainStory']; print('dict',k); break
def walk(n, d=0):
    nm = n.getName() if hasattr(n,'getName') else getattr(n,'name','?')
    kind = type(n).__name__
    if isinstance(n, QuestDNA):
        tasks = [type(t).__name__ for t in n.getTasks()]
        fin = n.getFinalizeInfo() if hasattr(n,'getFinalizeInfo') else None
        print('  '*d + '%s %s %s fin=%s' % (kind, n.getQuestId(), tasks, [f.get('type') for f in fin] if fin else None))
    else:
        print('  '*d + '%s %s' % (kind, nm))
        for c in n.getContainers() if hasattr(n,'getContainers') else n.containers:
            walk(c, d+1)
walk(ms)
