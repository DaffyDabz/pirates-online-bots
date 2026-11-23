def run(H):
    from pirates.quest import QuestParser
    from pirates.distributed import InteractGlobals
    for d in ('quest_tut_darby_ship1',):
        sid = InteractGlobals.getNPCTutorial(d) or d
        H.ev('script', sid=sid, lines=QuestParser.lineDict.get(sid))
    yield 1
