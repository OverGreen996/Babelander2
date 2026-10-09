"""Serial offscreen release checks; avoid concurrent model/CPU benchmarks."""
import os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
steps=[
    ('burst',['probe_chat_poll.py','--child','--scan-ms','100','--period-ms','350','--out','chat-poll-burst-a22']),
    ('resources',['probe_chat_poll_resources.py']),
    ('settings',['probe_settings_a22.py']),
    ('modes',['supertest_modes.py','--out','test-results/a22-modes']),
    ('chat-events',['probe_chat_events.py','--out','test-results/a22-chat-events']),
    ('ocr-edges',['probe_chat_ocr_edges.py']),
    ('package',['supertest.py','--phase','package']),
]
for name,args in steps:
    print('START '+name,flush=True)
    subprocess.run([sys.executable,*args],cwd=ROOT,env=env,check=True,
                   creationflags=subprocess.CREATE_NO_WINDOW,timeout=300)
    print('PASS '+name,flush=True)
