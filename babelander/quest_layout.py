"""One-shot quest UI: keep fields/buttons independent, join narrative wraps."""
import re
import unicodedata
import cv2
import numpy as np
from .layout import card_blocks, bounds, CONDITION, BRANCH
from .equipment_layout import colors, decoration_on_rule, solid_gem_shape
from .types import OCRLine

LITERAL = re.compile(r'\d+(?:\s*[/：:]\s*\d+)?%?')

def numeric_lines(frame,lines):
    """Repair only a pixel-proven slash; never guess missing numeric values.

    A solid oblique stroke is distinct from a vertical digit 1. Ambiguous crops
    remain unchanged. Merge adjacent numeric fragments on the same baseline.
    """
    result=[];scanned=0
    for line in lines:
        text=unicodedata.normalize('NFKC',line.text).strip();box=bounds(line)
        if box and re.fullmatch(r'[\d/:% ]{1,12}',text) and scanned<32:
            scanned+=1
            x0,y0,x1,y1=map(int,box)
            if 0<=x0<x1<=frame.shape[1] and 0<=y0<y1<=frame.shape[0] and x1-x0<=256 and y1-y0<=64:
                _,fg=colors(frame,box)
                ink=(np.max(np.abs(frame[y0:y1,x0:x1].astype(np.int16)-np.array(fg[::-1])),axis=2)<=80).astype(np.uint8)
                count,labels,stats,_=cv2.connectedComponentsWithStats(ink,8)
                components=sorted((i for i in range(1,count) if stats[i,4]>=6 and stats[i,3]>=(y1-y0)*.4),key=lambda i:stats[i,0])
                compact=text.replace(' ','')
                if len(components)==len(compact):
                    characters=list(compact)
                    for index,i in enumerate(components):
                        if characters[index]!='1':continue
                        ys,xs=np.where(labels==i)
                        slope=float(np.polyfit(ys,xs,1)[0])
                        residual=float(np.std(xs-(slope*ys+np.mean(xs-slope*ys))))
                        if -.7<slope<-.20 and residual<1.15 and np.ptp(xs)>=np.ptp(ys)*.2:
                            characters[index]='/'
                    text=''.join(characters)
            line=OCRLine(text,line.box,line.confidence)
        result.append(line)
    merged=[]
    for line in sorted(result,key=lambda l:((bounds(l) or (0,0,0,0))[1],(bounds(l) or (0,0,0,0))[0])):
        a=bounds(line);joined=False
        for i,prior in enumerate(merged):
            b=bounds(prior)
            if not a or not b or not re.fullmatch(r'[\d/:% ]+',line.text+prior.text):continue
            h=min(a[3]-a[1],b[3]-b[1])
            if -h*.2<=a[0]-b[2]<=h*.8 and abs((a[1]+a[3]-b[1]-b[3])/2)<=h*.35:
                candidate=prior.text+line.text
                if not LITERAL.fullmatch(candidate) or '/' not in candidate:continue
                x0,y0,x1,y1=min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])
                merged[i]=OCRLine(candidate,((x0,y0),(x1,y0),(x1,y1),(x0,y1)),min(line.confidence,prior.confidence));joined=True;break
        if not joined:merged.append(line)
    return merged

# Exact UI labels only. Objectives and narrative remain on the model path.
LABELS = {
    'objectives':'任務目標', 'objective':'任務目標', 'rewards':'獎勵',
    'quest rewards':'任務獎勵', 'description':'任務說明', 'quest details':'任務詳情',
    'accept':'接受', 'decline':'拒絕', 'complete quest':'完成任務', 'track':'追蹤',
    'untrack':'取消追蹤', 'abandon':'放棄', 'close':'關閉', 'optional':'選擇性目標',
    'daily quests':'每日任務', 'main quest':'主線任務', 'side quest':'支線任務',
    'time remaining':'剩餘時間', 'progress':'進度', 'mission briefing':'任務簡報',
    'quest journal':'任務日誌', 'bounty contract':'懸賞合約', 'recommended level':'建議等級',
}

def label_rule(text, mapping):
    if mapping:return None  # Explicit glossary always takes precedence.
    clean=text.strip()
    value=LABELS.get(clean.rstrip(':：').casefold())
    return value+('：' if clean.endswith((':','：')) else '') if value else None

def quest_blocks(frame, lines):
    samples={}
    def sample(line):
        box=bounds(line)
        if box not in samples:samples[box]=colors(frame,box)[1] if box else (0,0,0)
        return samples[box]
    def boundary(previous,current):
        a,b=bounds(previous),bounds(current)
        if a is None or b is None:return True
        # Color belongs to each observed text block, never a hardcoded palette.
        if np.linalg.norm(np.array(sample(previous))-np.array(sample(current)))>40:return True
        if max(a[3]-a[1],b[3]-b[1])>min(a[3]-a[1],b[3]-b[1])*1.18:return True
        words=previous.text.split()
        if (len(words)<=8 and sum(w[:1].isupper() for w in words)>=2 and
                not re.search(r'[.!?,;:]|\b(?:if|when|unless)\b',previous.text,re.I) and
                re.search(r'[.!?]$',current.text.strip())):return True
        for line in (previous,current):
            text=line.text.strip().rstrip(':：').casefold()
            if text in LABELS:return True
        # Tracker objectives/progress are independent events, not prose wraps.
        if re.search(r'\d+\s*/\s*\d+|\d+\s*:\s*\d+',previous.text+current.text):return True
        # Do not detach a conditional alternative from its narrative context.
        if BRANCH.match(current.text) and CONDITION.search(previous.text):return False
        return False
    return card_blocks([line for line in lines if not decoration_on_rule(frame,line) and not solid_gem_shape(frame,line)],
                       separate_fields=True,boundary=boundary)
