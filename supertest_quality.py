"""Novel conditional/temporal intent probes. Markers do not certify full semantics."""
from bootstrap import prepare
prepare()
from pathlib import Path
from dataclasses import asdict
import argparse,json,tempfile,re
from babelander import __version__
from babelander.settings import Settings
from babelander.storage import Store
from babelander.security import KeyVault
from babelander.engine import Engine
from babelander.types import Mode,Cancellation
parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);args=parser.parse_args()
root=Path(__file__).parent;assets=root.parent/'recovery/test-assets'
cases=[(Mode.CHAT,'If the boss targets you, move away from the group.',[r'首領|Boss',r'遠離|離開']),
(Mode.CHAT,'Do not sell the last 6 potions.',[r'不|勿|別',r'6']),
(Mode.CHAT,'Save the last potion for the healer, not for me.',[r'留|保留',r'補師']),
(Mode.DIALOG,'The bridge is closed, but the eastern gate is still open.',[r'橋',r'門',r'但|仍|還']),
(Mode.DIALOG,"Don't enter until all 3 players are ready.",[r'不|勿|別',r'3']),
(Mode.QUEST,'Collect 4 crystals before speaking to the captain.',[r'4',r'水晶|晶體',r'(?:收集|蒐集)[^。]{0,20}4[^。]{0,25}(?:再|然後|之後|前|之前|先)[^。]{0,20}(?:船長|隊長|指揮官)|(?:船長|隊長|指揮官)[^。]{0,12}(?:說話|對話)(?:之)?前[^。]{0,20}(?:收集|蒐集)[^。]{0,15}4']),
(Mode.QUEST,'Defeat 5 wolves, then return to the camp.',[r'5',r'狼',r'營地|營區']),
(Mode.EQUIPMENT,'When poisoned, gain +17% Fire Resistance for 8 seconds.',[r'中毒|毒',r'17',r'8']),
(Mode.EQUIPMENT,'Restore 13 health when blocking an attack. This cannot occur more than once every 7 seconds.',[r'13',r'7',r'格擋|阻擋|防禦']),
(Mode.REPLY,'請等我7分鐘，不要離開隊伍。',[r'wait',r'7',r"not|don.t|cannot",r'party|team|group']),
(Mode.REPLY,'我們需要6瓶藥水，先別開門。',[r'6',r'potion',r"not|don.t|cannot",r'gate|door']),
(Mode.SCREEN,'Server maintenance starts in 9 minutes. Unsaved progress will be lost.',[r'9',r'維護',r'丟失|遺失|失去'])]
rows=[]
with tempfile.TemporaryDirectory(prefix='Babelander-quality-') as directory:
    store=Store(directory);engine=Engine(Settings(hotkeys={},model_path=str(next((assets/'models').glob('*.gguf'))),server_path=str(assets/'runtime/llama-server.exe')),store,KeyVault(directory),directory)
    try:
        for mode,source,markers in cases:
            t=engine.request(source,mode,Cancellation());rows.append({**asdict(t),'mode':mode.value,'markers':markers,'markers_passed':not t.warning and all(re.search(m,t.target,re.I) for m in markers)})
    finally:engine.close();engine.join();store.close()
report={'version':__version__,'cases':rows,'marker_passed_count':sum(r['markers_passed'] for r in rows),'all_critical_markers_passed':all(r['markers_passed'] for r in rows),'semantic_accuracy_scored':False,'note':'New sentences outside complete-rule grammars. Review full outputs: marker presence is necessary, not sufficient for meaning.'}
p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'cases':len(rows),'marker_passed_count':report['marker_passed_count']}),flush=True)
