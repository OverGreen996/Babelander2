"""Bounded numeric-field retries from the same captured equipment image.

Proposals contain geometry only, never guessed values. Unmatched artwork and
uncertain recognition remain original pixels. This is not general text recovery.
"""
from dataclasses import dataclass
import re
import cv2
import numpy as np
from .layout import bounds
from .equipment_layout import colors,solid_gem_shape,equipment_decoration
from .types import OCRLine

MAX_CANDIDATES = 6
MAX_FIELD_SCANS = 16
DIGITS = re.compile(r'[0-9]{1,4}')
FIELDS = frozenset(('attack', 'health', 'defense', 'defence', 'armor', 'armour',
                    'damage', 'magic', 'strength', 'dexterity', 'vitality', 'mana',
                    'cost', 'power', 'durability', 'weight', 'level', 'quality',
                    'resistance', 'value', 'energy', 'speed'))


@dataclass(frozen=True)
class NumericCandidate:
    box: tuple
    replace_index: int | None = None


def overlaps(a, b, margin=2):
    return min(a[2]+margin,b[2])>max(a[0]-margin,b[0]) and min(a[3]+margin,b[3])>max(a[1]-margin,b[1])


def proposals(image, lines):
    height,width=image.shape[:2]
    boxes=[bounds(line) for line in lines]
    result=[]
    def near_field(box):
        return any(b is not None and line.confidence>=.90 and line.text.strip().rstrip(':').lower() in FIELDS
                   and 0<=box[0]-b[2]<=180 and abs((box[1]+box[3]-b[1]-b[3])/2)<(b[3]-b[1])*.65
                   for line,b in zip(lines,boxes))
    for index,(line,box) in enumerate(zip(lines,boxes)):
        if box is None or not all(np.isfinite(box)):continue
        x0,y0,x1,y1=box
        if not (0<=x0<x1<=width and 0<=y0<y1<=height):continue
        if (DIGITS.fullmatch(line.text.strip()) and line.confidence<.90 and x1-x0<=128 and 8<=y1-y0<=64
                and near_field(box) and not solid_gem_shape(image,line) and not equipment_decoration(line,lines)):
            result.append(NumericCandidate(box,index))
            if len(result)==MAX_CANDIDATES:return result
    scans=0
    for line,box in zip(lines,boxes):
        if box is None or line.confidence<.90 or line.text.strip().rstrip(':').lower() not in FIELDS:continue
        x0,y0,x1,y1=box;glyph_height=y1-y0
        if not (0<=x0<x1<=width and 0<=y0<y1<=height and 10<=glyph_height<=48):continue
        if scans==MAX_FIELD_SCANS:break
        scans+=1
        left=int(np.ceil(x1+2));right=min(width,int(x1+min(180,glyph_height*7)))
        top=max(0,int(y0-glyph_height*.35));bottom=min(height,int(np.ceil(y1+glyph_height*.5)))
        if right<=left:continue
        patch=image[top:bottom,left:right,:3]
        background,foreground=colors(image,box)
        foreground=np.asarray(foreground[::-1],dtype=np.int16)
        if np.max(np.abs(foreground-np.asarray(background)))<48:continue
        ink=(np.max(np.abs(patch.astype(np.int16)-foreground),axis=2)<=36).astype(np.uint8)
        count,labels,stats,_=cv2.connectedComponentsWithStats(ink,8)
        components=[]
        # Reject busy areas before making recognition requests; no unbounded crops.
        if count>128:continue
        for sx,sy,sw,sh,area in stats[1:]:
            if not (max(7,glyph_height*.45)<=sh<=glyph_height*1.7 and 2<=sw<=sh*1.3 and area>=12):continue
            occupancy=area/(sw*sh)
            if not .08<=occupancy<=.72:continue  # solid gems, bars and badges
            candidate=(int(left+sx),int(top+sy),int(left+sx+sw),int(top+sy+sh))
            if solid_gem_shape(image,OCRLine('?',((candidate[0],candidate[1]),(candidate[2],candidate[1]),
                                                  (candidate[2],candidate[3]),(candidate[0],candidate[3])),0)):continue
            if abs((candidate[1]+candidate[3]-y0-y1)/2)>glyph_height*.65:continue
            if any(b is not None and overlaps(candidate,b) for b in boxes):continue
            components.append(candidate)
        components.sort()
        groups=[]
        for component in components:
            if groups and component[0]-groups[-1][2]<=glyph_height*.55 and abs(component[1]-groups[-1][1])<=glyph_height*.35:
                a=groups[-1];groups[-1]=(a[0],min(a[1],component[1]),component[2],max(a[3],component[3]))
            else:groups.append(component)
        for candidate in groups:
            if candidate[2]-candidate[0]>min(128,glyph_height*3.5):continue
            if any(overlaps(candidate,c.box) for c in result):continue
            result.append(NumericCandidate(candidate))
            if len(result)==MAX_CANDIDATES:return result
    return result


def crops(image, candidates):
    height,width=image.shape[:2]
    output=[]
    for candidate in candidates:
        x0,y0,x1,y1=candidate.box
        patch=image[max(0,int(y0)-8):min(height,int(np.ceil(y1))+8),
                    max(0,int(x0)-8):min(width,int(np.ceil(x1))+8),:3].copy()
        output.append(patch)
    return output


def accept(lines, candidates, first, second):
    output=list(lines);accepted=0
    if (first.txts is None or first.scores is None or second.txts is None or second.scores is None
            or not all(len(values)==len(candidates) for values in (first.txts,first.scores,second.txts,second.scores))):
        return output,accepted
    for candidate,a,sa,b,sb in zip(candidates,first.txts,first.scores,second.txts,second.scores):
        if not isinstance(a,str) or not isinstance(b,str):continue
        a,b=a.strip(),b.strip()
        if a!=b or not DIGITS.fullmatch(a) or not np.isfinite(sa) or not np.isfinite(sb) or min(sa,sb)<.98:continue
        x0,y0,x1,y1=candidate.box
        recovered=OCRLine(a,((x0,y0),(x1,y0),(x1,y1),(x0,y1)),float(min(sa,sb)))
        if candidate.replace_index is None:output.append(recovered)
        else:output[candidate.replace_index]=recovered
        accepted+=1
    return sorted(output,key=lambda line:(round(min(p[1] for p in line.box)/12),min(p[0] for p in line.box))),accepted
