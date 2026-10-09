"""Cross-game chat vocabulary and conservative wrapped-message assembly."""
import re
import unicodedata
from statistics import median
from functools import lru_cache
from .glossary import restore_terms
from .types import OCRLine
from .layout import bounds

CHAT_TERMS={
    'gg wp':'打得漂亮','ggwp':'打得漂亮','gg ez':'輕鬆贏了',
    'gl hf':'祝好運，玩得開心','glhf':'祝好運，玩得開心',
    'well played':'打得漂亮','nice shot':'好槍法','gg':'打得好','wp':'打得漂亮','ty':'謝啦','thx':'謝啦','np':'沒問題',
    'nt':'好嘗試','mb':'我的錯','brb':'馬上回來','afk':'暫離',
    'lfg':'找隊伍','lfm':'隊伍徵人','oom':'魔力耗盡','omw':'正在趕來','otw':'正在趕來',
    'wts':'出售','wtb':'收購','dps':'輸出','hp':'生命值','mp':'魔力值',
    'ult':'大招','rez':'復活','buff':'增益效果','debuff':'減益效果',
    'lag':'延遲','dc':'斷線','mats':'材料','ammo':'彈藥','asap':'儘快',
    'potion':'藥水','potions':'藥水','healer':'補師',
    'loot':'戰利品','bandage':'繃帶','bandages':'繃帶','mana':'魔力','health':'生命值',
    'spawn point':'重生點','reload':'換彈','gear':'裝備','bag':'背包',
    'gate':'大門','coin':'硬幣','coins':'硬幣','boss':'首領',
    'party':'隊伍',
    'raid':'團隊副本','raids':'團隊副本',
}

# Familiar multiplayer shorthand can stay English, as requested. Protect it
# inside sentences too, while ordinary English still goes through translation.
CHAT_SHORTHAND=frozenset(('gg wp','ggwp','gg ez','gl hf','glhf','gg','wp','ty','thx',
    'np','nt','mb','brb','afk','lfg','lfm','oom','omw','otw','wts','wtb','dps','hp','mp','dc'))
CHAT_TERMS.update({term:term.upper() for term in CHAT_SHORTHAND})

def only_shorthand(text):
    remainder=text
    for term in sorted(CHAT_SHORTHAND,key=len,reverse=True):
        remainder=re.sub(r'(?<![A-Za-z0-9_])'+re.escape(term)+r'(?![A-Za-z0-9_])','',remainder,flags=re.I)
    return not re.search(r'[A-Za-z\u3400-\u9fff]',remainder)

PREFIX=re.compile(r'^(\[[^\]]+\]\s*[^:：]{1,40}[:：]|[^:：]{1,35}[:：])\s*(.+)$')
def split_message(text):
    match=PREFIX.match(text)
    return (match[1],match[2]) if match else ('',text)


def filter_decorations(lines):
    """Exclude tiny isolated geometric marks relative to observed chat text.

    No language or brightness threshold: names, quantities, punctuation and
    emoji remain eligible. Unknown geometry and a symbol-only ROI fail open.
    Full-size shapes and shapes sent under a speaker prefix remain messages.
    """
    heights=[]
    for line in lines:
        box=bounds(line)
        if box and any(ch.isalnum() for ch in line.text):heights.append(box[3]-box[1])
    if not heights:return list(lines),0
    typical=median(heights);kept=[];removed=0
    for line in lines:
        box=bounds(line);text=line.text.strip()
        geometric=bool(text) and all('\u2580'<=ch<='\u259f' or '\u25a0'<=ch<='\u25ff' for ch in text)
        if (geometric and box and box[3]-box[1]<typical*.5
                and box[2]-box[0]<typical*1.2):removed+=1
        else:kept.append(line)
    return kept,removed

def message_key(text):
    # OCR can insert spaces or switch fullwidth punctuation as a row scrolls.
    # Keep letters, case, quantities, speaker and meaningful punctuation intact.
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',text)).rstrip('.。')

@lru_cache(maxsize=1)
def _chat_script_converter():
    from opencc import OpenCC
    return OpenCC('s2t')


def _overlap_body(text):
    # Comparison only. Keep speakers, numbers, negation and question marks.
    # OCR commonly switches Chinese glyph variants or a comma to a middle dot.
    prefix,body=split_message(text)
    if not prefix:return text
    body=_chat_script_converter().convert(body)
    body=re.sub(r'(?<=[\u3400-\u9fff])—(?=[\u3400-\u9fff])','一',body)
    body=re.sub(r'(?<=[A-Za-z0-9%])[,，·](?=[\u3400-\u9fff])',',',body)
    body=re.sub(r'(?<=[A-Za-z])["“”](?=[\u3400-\u9fff])','',body)
    return prefix+body


def anchored_overlap(previous,current):
    """One OCR spelling wobble may not resend an otherwise anchored scroll.

    Require two matching surrounding rows after spelling-only normalization;
    at most one remaining OCR wobble. Never ignore a quantity, Latin word or
    Chinese negation change. Isolated rows use exact comparison. This assumes
    ordinary append/scroll chat, not editable messages.
    """
    from difflib import SequenceMatcher
    previous,current=[_overlap_body(t) for t in previous],[_overlap_body(t) for t in current]
    equal=[a==b for a,b in zip(previous,current)]
    if sum(equal)<2:return False
    if all(equal):return True
    if equal.count(False)!=1:return False
    a,b=next((a,b) for a,b in zip(previous,current) if a!=b)
    pa,ba=split_message(a);pb,bb=split_message(b)
    if not pa or not pb:return False
    if ba==bb:return (len(pa)==len(pb) and sum(x!=y for x,y in zip(pa,pb))==1
                      and SequenceMatcher(None,pa,pb,autojunk=False).ratio()>=.8)
    if pa!=pb:return False
    if min(len(ba),len(bb))<10:return False
    sensitive=lambda text:re.findall(r'[A-Za-z0-9_]+|[不勿別未沒]|[+\-−]\d+',text)
    if sensitive(ba)!=sensitive(bb):return False
    return SequenceMatcher(None,ba,bb,autojunk=False).ratio()>=.95

def complete_rule(text,dictionary):
    # Only complete, known shorthand or mixed Chinese text. Unknown English
    # sentences still need the model; this is not a per-fixture answer table.
    from .semantic_rules import dialog_rule,_atoms
    rule=dialog_rule(text,dictionary)
    if rule is not None:return rule
    # Complete, parameterized player intents. Any trailing condition, negation,
    # unknown item or partial glossary override stays on the model path.
    status=re.fullmatch(r'(?:is (?:the )?)?(party) (full|ready|empty)\?',text.strip(),re.I)
    if status:
        targets=_atoms(text,{'party':(status[1],'隊伍'),'status':(status[2],{'full':'滿了','ready':'準備好了','empty':'沒有隊員'}[status[2].lower()])},dictionary)
        if targets is not None:return targets['party']+targets['status']+'嗎？'
    focus=re.fullmatch(r'(?:focus|target) (?:the )?(healer|tank|boss) first[.!]?',text.strip(),re.I)
    if focus:
        targets=_atoms(text,{'role':(focus[1],{'healer':'補師','tank':'坦克','boss':'首領'}[focus[1].lower()])},dictionary)
        if targets is not None:return '優先集火'+targets['role']+'。'
    reserve=re.fullmatch(r'(?:save|keep|reserve) (\d+|one|two|three|four|five|six|seven|eight|nine|ten) ([A-Za-z]+) for (me|us|the next player)[.!]?',text.strip(),re.I)
    if reserve:
        protected,mapping=dictionary.protect(reserve[2])
        if protected in mapping:
            chinese={'one':'一','two':'兩','three':'三','four':'四','five':'五','six':'六','seven':'七','eight':'八','nine':'九','ten':'十'}
            quantity=chinese.get(reserve[1].lower(),reserve[1])
            targets=_atoms(text,{'item':(reserve[2],mapping[protected])},dictionary)
            if targets is not None:return '留'+quantity+'個'+targets['item']+'給'+{'me':'我','us':'我們','the next player':'下一位玩家'}[reserve[3].lower()]+'。'
    pause=re.fullmatch(r'(can|could) (we|you) (pause|wait) for (\d+(?:\.\d+)?) (minutes?|mins?|seconds?|secs?)\?',text.strip(),re.I)
    if pause and not dictionary.protect(text)[1]:
        unit='分鐘' if pause[5].lower().startswith('min') else '秒'
        return ('我們' if pause[2].lower()=='we' else '你')+'可以'+('暫停' if pause[3].lower()=='pause' else '等')+pause[4]+unit+'嗎？'
    timed=re.fullmatch(r'(brb|afk)\s+(\d+)\s*(min(?:s|utes?)?|sec(?:s|onds?)?)\.?',text.strip(),re.I)
    if timed:
        protected,mapping=dictionary.protect(timed[1])
        if protected in mapping:
            unit='分鐘' if timed[3].lower().startswith('min') else '秒'
            return mapping[protected]+' '+timed[2]+' '+unit
    protected,mapping=dictionary.protect(text)
    rest=re.sub(r'\[GL\d+\]','',protected)
    # Quantity markers are literals; do not translate an x into an item name.
    rest=re.sub(r'(?<![A-Za-z0-9_])[xX×]\s*\d+(?![A-Za-z0-9_])','',rest)
    if mapping and not re.search(r'[A-Za-z]',rest):return restore_terms(protected,mapping)
    return None

def messages(lines):
    """Join indented unprefixed wraps under one speaker, with bounded geometry.

    Unprefixed ordinary lines remain independent unless a nearby speaker row
    and continuation indent support a wrap. Never guess a lost speaker.
    """
    groups=[]
    for line in lines:
        prefix,_=split_message(line.text);box=bounds(line)
        if groups and not prefix and box:
            prior=groups[-1];old=bounds(prior[-1]);head=bounds(prior[0])
            if old and head and split_message(prior[0].text)[0]:
                h=max(box[3]-box[1],old[3]-old[1])
                if (box[0]>=head[0]+max(8,h*.25) and -h*.15<=box[1]-old[3]<=h*1.1 and
                        .65<=(box[3]-box[1])/(old[3]-old[1])<=1.45 and len(prior)<8):
                    prior.append(line);continue
        groups.append([line])
    output=[]
    for group in groups:
        if len(group)==1:output.append(group[0]);continue
        rectangles=[bounds(line) for line in group]
        x0,y0=min(b[0] for b in rectangles),min(b[1] for b in rectangles)
        x1,y1=max(b[2] for b in rectangles),max(b[3] for b in rectangles)
        output.append(OCRLine(' '.join(line.text for line in group),((x0,y0),(x1,y0),(x1,y1),(x0,y1)),min(l.confidence for l in group)))
    return output
