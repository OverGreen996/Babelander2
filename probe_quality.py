"""Additional real local examples; record warnings rather than hide failures."""
from pathlib import Path
from dataclasses import asdict
import json
import tempfile
from babelander.settings import load_settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.types import Mode,Cancellation
cases=[
    (Mode.DIALOG,'Do not enter the dungeon yet.'),
    (Mode.DIALOG,'Do not follow Player_007 unless Player_007 asks for help.'),
    (Mode.DIALOG,'Meet Player_007 near Gate_02 at X:-12 Y:34.'),
    (Mode.DIALOG,'If the bridge is closed, wait by the northern gate. Otherwise, cross the river.'),
    (Mode.DIALOG,'Never open the chest before the guard leaves.'),
    (Mode.EQUIPMENT,'If health is above 30%, gain +12% Movement Speed for 5 seconds. Otherwise, gain +3% Fire Resistance.'),
    (Mode.EQUIPMENT,'Gain -15% Attack Speed for 10 seconds.'),
    (Mode.EQUIPMENT,'Gain +12.5% Fire Resistance for 2.5 seconds.'),
    (Mode.EQUIPMENT,'When you block an attack, restore 12 health. This cannot occur more than once every 5 seconds.'),
    (Mode.QUEST,'Collect 3/10 moonstones before 01:30. Do not leave the area.'),
    (Mode.QUEST,'Defeat 7 wolves, then return to Gate_02.'),
    (Mode.QUEST,'Do not use the portal unless all 3 players are ready.'),
    (Mode.QUEST,'Wait for 2 minutes before activating the shrine.'),
    (Mode.CHAT,'Do not start the raid. I will return in 5 minutes.'),
    (Mode.CHAT,'Player_007 will meet us near Gate_02 in 10 seconds.'),
    (Mode.CHAT,'If the boss targets you, move away from the group.'),
    (Mode.REPLY,'我五分鐘後回來，請不要開始。'),
    (Mode.REPLY,'請在 X:-12 Y:34 等我，不要使用傳送門。'),
    (Mode.REPLY,'我們還需要 3 個人，等 2 分鐘再開始。'),
    (Mode.SCREEN,'Please read the update notes before entering the dungeon.'),
    (Mode.SCREEN,'This menu does not save changes automatically. Press Apply to confirm.'),
    (Mode.SCREEN,'The maintenance window lasts 10 minutes. Do not close the application during this time.'),
]
root=Path(__file__).resolve().parent;rows=[]
with tempfile.TemporaryDirectory(prefix='Babelander2-quality-') as directory:
    settings=load_settings(directory);store=Store(directory);engine=Engine(settings,store,KeyVault(directory),directory)
    try:
        for mode,source in cases:
            try:
                result=engine.request(source,mode,Cancellation())
                rows.append({'mode':mode.value,**asdict(result),'guard_preserves_source':not result.warning or result.target==source})
            except Exception as error:rows.append({'mode':mode.value,'source':source,'error_type':type(error).__name__})
    finally:engine.close();engine.join();store.close()
report={'passed':all(r.get('guard_preserves_source',False) for r in rows),'cases':len(rows),'translated':sum(not r.get('warning') and 'target' in r for r in rows),'preserved_original':sum(bool(r.get('warning')) for r in rows),'results':rows,'note':'Additional synthetic examples; passed means no transport failure and any guard warning preserves original. It does not certify semantic correctness or a game-wide accuracy rate.'}
(root/'test-results/quality.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(not report['passed'])
