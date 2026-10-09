"""Conservative OCR paragraph assembly using the observed boxes and grammar.

This reconstructs reading blocks, not the game's original decorative layout.
"""
from dataclasses import dataclass
import math
import re

from .types import OCRLine
from .equipment_fast_rules import NUMERIC_FIELD,AFFIX_FIELD,LITERAL_NUMBER,ATOMIC_UI


@dataclass(frozen=True)
class OCRBlock:
    lines: tuple[OCRLine, ...]
    warning: str = ''

    @property
    def text(self):
        return '\n'.join(line.text for line in self.lines)

    @property
    def inference_text(self):
        return re.sub(r'\s+',' ',self.text).strip()

    @property
    def confidence(self):
        scores = [line.confidence if math.isfinite(line.confidence) else 0 for line in self.lines]
        return min(max(0,min(1,score)) for score in scores)


def bounds(line):
    if not line.box or len(line.box)<4:
        return None
    try:
        xs,ys = zip(*line.box)
        result = min(xs),min(ys),max(xs),max(ys)
        return result if all(math.isfinite(v) for v in result) and result[2]>result[0] and result[3]>result[1] else None
    except (TypeError,ValueError):
        return None


CONDITION = re.compile(r'\b(?:if|when|unless)\b',re.I)
BRANCH = re.compile(r'^(?:otherwise|else)\b',re.I)
NEW_EFFECT = re.compile(r'^(?:if|when|gain|lose|collect|meet|kill|equip|use|requires?|do not)\b',re.I)
BULLET = re.compile(r'^(?:[•●▪*]|[-–]\s|\d+[.)]\s)')
ACTION = re.compile(r'\b(?:gain|lose|deal|restore|increase|reduce|collect|kill|use|equip)\b',re.I)
CARD_HEADING=re.compile(r'^(?:legendary|unique|epic|rare|uncommon|common|mythic|'
    r'(?:one|two)[- ]handed (?:sword|axe|mace)|longbow|shortbow|bow|dagger|sword|axe|'
    r'mace|staff|wand|shield|pendant|amulet|ring|lantern|helmet|boots|gloves)\.?$',re.I)


def continues(lines, current, separate_fields=False):
    previous = lines[-1].text.rstrip()
    text = current.text.strip()
    whole = ' '.join(line.text for line in lines)
    if separate_fields and any(CARD_HEADING.fullmatch(t) for t in (text,previous.strip())):return False
    if separate_fields and (NUMERIC_FIELD.fullmatch(text) or NUMERIC_FIELD.fullmatch(previous.strip())):
        return False
    if separate_fields and any(AFFIX_FIELD.fullmatch(t) or LITERAL_NUMBER.fullmatch(t) or ATOMIC_UI.search(t)
                               for t in (text,previous.strip())):
        return False
    if BULLET.match(text):
        return False
    if BRANCH.match(text):
        return bool(CONDITION.search(whole))
    if text.lower().startswith('unless '):
        return previous.lower().startswith(('do not','don\'t')) or not re.search(r'[.!?。！？]$',previous)
    if re.search(r'[.!?。！？]$',previous):
        return False
    if NEW_EFFECT.match(text):
        # A wrapped condition followed by its first action is one effect.
        return bool(CONDITION.search(whole)) and not ACTION.search(whole)
    return True


def card_blocks(lines, separate_fields=False, boundary=None):
    """Join adjacent wraps within a column; keep bullets/effects independent."""
    rows = []
    unplaced = []
    for line in lines:
        box = bounds(line)
        if box is None:
            unplaced.append(OCRBlock((line,)))
        else:
            rows.append((line,box))
    rows.sort(key=lambda item:(item[1][1],item[1][0]))
    # A label with a separate numeric cell on its baseline belongs to a field,
    # not a paragraph made from the labels above and below it.
    atomic_labels=set()
    if separate_fields:
        for line,box in rows:
            if len(line.text)>40 or CONDITION.search(line.text) or ACTION.search(line.text):continue
            for peer,other in rows:
                h=min(box[3]-box[1],other[3]-other[1])
                if peer is not line and LITERAL_NUMBER.fullmatch(peer.text.strip()) and abs((box[1]+box[3]-other[1]-other[3])/2)<=h*.4:
                    atomic_labels.add(id(line));break
    # Adjacent OCR fragments on the same baseline can be one detected row.
    merged = []
    for line,box in rows:
        candidates = []
        for index,(prior,old) in enumerate(merged):
            h = min(box[3]-box[1],old[3]-old[1])
            same_row = abs((box[1]+box[3]-old[1]-old[3])/2)<=h*.35
            gap = box[0]-old[2]
            if separate_fields and (LITERAL_NUMBER.fullmatch(line.text.strip()) or
                                    LITERAL_NUMBER.fullmatch(prior.text.strip()) or
                                    id(line) in atomic_labels or id(prior) in atomic_labels or
                                    max(box[3]-box[1],old[3]-old[1])>h*1.35):
                continue
            if same_row and 0<=gap<=h*1.2:
                candidates.append((gap,index))
        if candidates:
            _,index = min(candidates)
            prior,old = merged[index]
            union = min(old[0],box[0]),min(old[1],box[1]),max(old[2],box[2]),max(old[3],box[3])
            x,y,right,bottom = union
            joined = OCRLine(prior.text+' '+line.text,((x,y),(right,y),(right,bottom),(x,bottom)),min(prior.confidence,line.confidence))
            merged[index] = joined,union
        else:
            merged.append((line,box))
    groups = []
    for line,box in sorted(merged,key=lambda item:(item[1][1],item[1][0])):
        candidates = []
        for index,group in enumerate(groups):
            old = bounds(group[-1])
            h = max(box[3]-box[1],old[3]-old[1])
            gap = box[1]-old[3]
            aligned = abs(box[0]-old[0])<=max(12,h*.7)
            if separate_fields:
                aligned |= abs((box[0]+box[2]-old[0]-old[2])/2)<=max(8,h*.35)
                if id(line) in atomic_labels or id(group[-1]) in atomic_labels:continue
            same_size = .65 <= (box[3]-box[1])/(old[3]-old[1]) <= 1.45
            if separate_fields and any(old[3]<=between[1] and between[3]<=box[1] and
                    min(box[2],between[2])>max(box[0],between[0]) for _,between in merged):
                continue  # Do not jump over an intervening atomic field.
            if aligned and same_size and -h*.15<=gap<=h*1.4 and continues(group,line,separate_fields):
                if boundary is not None and boundary(group[-1],line):continue
                candidates.append((gap,index))
        if candidates:
            groups[min(candidates)[1]].append(line)
        else:
            groups.append([line])
    output = []
    for group in groups:
        warning = '條件分支缺少相鄰前文；請擴大框選或確認原文。' if BRANCH.match(group[0].text.strip()) else ''
        output.append(OCRBlock(tuple(group),warning))
    return output+unplaced
