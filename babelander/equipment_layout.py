"""Single-capture, immutable original-position equipment layout metadata."""
import re
import numpy as np
import cv2
from .layout import OCRBlock,card_blocks,bounds,CONDITION,ACTION,BRANCH
from .types import EquipmentLayout,EquipmentSlot
from .equipment_fast_rules import LITERAL_NUMBER,AFFIX_FIELD,NUMERIC_FIELD,ATOMIC_UI


def colors(frame,box):
    h,w=frame.shape[:2]
    x0,y0,x1,y1=box
    x0,y0=max(0,int(x0)),max(0,int(y0))
    x1,y1=min(w,int(np.ceil(x1))),min(h,int(np.ceil(y1)))
    if x1<=x0 or y1<=y0:raise ValueError('裝備文字位置超出框選範圍。')
    patch=frame[max(0,y0-3):min(h,y1+3),max(0,x0-3):min(w,x1+3),:3]
    # Sample the border, not glyph interiors. Retain the captured decorations
    # outside recognized text, without a full-size inpainting model.
    border=np.concatenate((patch[:2].reshape(-1,3),patch[-2:].reshape(-1,3),
                           patch[:,:2].reshape(-1,3),patch[:,-2:].reshape(-1,3)))
    background=np.median(border,axis=0)
    glyph=frame[y0:y1,x0:x1,:3].reshape(-1,3)
    contrast=np.max(np.abs(glyph.astype(np.float32)-background),axis=1)
    selected=glyph[contrast>=max(24,float(np.percentile(contrast,85)))]
    if len(selected):
        # A few highlighted numbers must not recolor an otherwise gray/white
        # paragraph. Pick the dominant hue family before its opaque pixels.
        delta=selected.astype(np.float32)-background
        # Antialias pixels lie on the same background-to-foreground direction.
        # Group those directions rather than crossing HSV saturation/hue bins.
        directions=delta/np.maximum(1,np.max(np.abs(delta),axis=1))[:,None]
        quantized=np.rint(directions*4).astype(np.int16)+4
        groups=quantized[:,0]*81+quantized[:,1]*9+quantized[:,2]
        chosen=int(np.argmax(np.bincount(groups,minlength=729)))
        center=directions[groups==chosen].mean(axis=0)
        selected=selected[np.linalg.norm(directions-center,axis=1)<=.35]
        strength=np.max(np.abs(selected.astype(np.float32)-background),axis=1)
        selected=selected[strength>=float(np.max(strength))*.97]
        values,counts=np.unique(selected,axis=0,return_counts=True)
        foreground=values[np.argmax(counts)]
    else:foreground=np.array((240,240,240))
    return tuple(int(v) for v in background),tuple(int(v) for v in foreground[::-1])


def decoration_on_rule(frame,line):
    box=bounds(line)
    if box is None or line.confidence>=.60 or len(line.text.strip())!=1 or not line.text.strip().isalpha():return False
    x0,y0,x1,y1=map(int,box);height=y1-y0
    if height>18 or x1-x0>18:return False
    image=frame
    for y in range(max(4,(y0+y1)//2-4),min(len(image)-4,(y0+y1)//2+5)):
        contrast=np.max(np.abs(image[y].astype(np.int16)-
            (image[y-4].astype(np.int16)+image[y+4].astype(np.int16))//2),axis=1)>18
        edges=np.flatnonzero(np.diff(np.r_[False,contrast,False]))
        if len(edges) and max(edges[1::2]-edges[::2])>max(80,height*6):return True
    return False


def equipment_decoration(line,lines):
    """Geometric false detections; never discard a number or a signed affix."""
    box=bounds(line)
    if box is None:return False
    text=line.text.strip();x0,y0,x1,y1=box;w,h=x1-x0,y1-y0
    # An underscore glyph is horizontal. A tall underscore detection inside
    # artwork is a shape, and erasing it would damage the captured illustration.
    if text=='_' and h>w*1.25:return True
    if text not in ('O','o','○') or not .75<=w/h<=1.3:return False
    for other in lines:
        if other is line or not re.fullmatch(r'empty\s+socket',other.text.strip(),re.I):continue
        b=bounds(other)
        if b and 0<=b[0]-x1<=h and abs((y0+y1-b[1]-b[3])/2)<=h*.4:return True
    return False


def solid_gem_shape(frame,line):
    """A filled convex diamond is artwork, even when OCR calls it '4' or 'A'.

    Text identity is never sufficient: hollow/stroked glyphs and high-confidence
    detections stay untouched. Inspect only small single-glyph crops.
    """
    box=bounds(line)
    if box is None or line.confidence>=.85 or len(line.text.strip())!=1:return False
    x0,y0,x1,y1=map(int,box);w,h=x1-x0,y1-y0
    if not (12<=w<=256 and 12<=h<=256 and .65<=w/h<=1.5):return False
    patch=frame[max(0,y0):y1+1,max(0,x0):x1+1,:3]
    if not patch.size:return False
    border=np.concatenate((patch[:2].reshape(-1,3),patch[-2:].reshape(-1,3),patch[:,:2].reshape(-1,3),patch[:,-2:].reshape(-1,3)))
    background=np.median(border,axis=0)
    ink=(np.max(np.abs(patch.astype(np.int16)-background),axis=2)>24).astype(np.uint8)
    contours,_=cv2.findContours(ink,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours:return False
    contour=max(contours,key=cv2.contourArea);area=cv2.contourArea(contour)
    if area<w*h*.12 or area/max(1,cv2.contourArea(cv2.convexHull(contour)))<.93:return False
    polygon=cv2.approxPolyDP(contour,.045*cv2.arcLength(contour,True),True).reshape(-1,2)
    if len(polygon)!=4:return False
    bx,by,bw,bh=cv2.boundingRect(polygon);cx,cy=bx+bw/2,by+bh/2
    top=polygon[np.argmin(polygon[:,1])];bottom=polygon[np.argmax(polygon[:,1])]
    left=polygon[np.argmin(polygon[:,0])];right=polygon[np.argmax(polygon[:,0])]
    if (abs(top[0]-cx)>bw*.22 or abs(bottom[0]-cx)>bw*.22 or
            abs(left[1]-cy)>bh*.22 or abs(right[1]-cy)>bh*.22):return False
    filled=np.zeros_like(ink);cv2.drawContours(filled,[contour],-1,1,-1)
    return bool(ink[filled>0].mean()>=.93)


def luminance(rgb):
    channels=np.asarray(rgb,dtype=float)/255
    return float(np.dot(np.where(channels<=.04045,channels/12.92,((channels+.055)/1.055)**2.4),[.2126,.7152,.0722]))


def contrast(a,b):
    x,y=sorted((luminance(a),luminance(b)))
    return (y+.05)/(x+.05)


def readable_color(preferred,background):
    """Retain semantic gold/blue hues, adapting their luminance to the card."""
    rgb=background[::-1]
    if contrast(preferred,rgb)>=4.5:return preferred
    alternate={(230,190,111):(113,70,20),(229,185,98):(113,70,20),
               (134,202,231):(24,74,112),(211,215,217):(34,39,44)}.get(preferred,(34,39,44))
    if contrast(alternate,rgb)>=4.5:return alternate
    # Mid-tone cards may need a stronger foreground than either theme palette.
    return max(((12,16,20),(250,250,250)),key=lambda color:contrast(color,rgb))


def padding_overlap(frame,a,b):
    width=min(a[2],b[2])-max(a[0],b[0])
    if width>min(a[3]-a[1],b[3]-b[1])*.6 or width>min(a[2]-a[0],b[2]-b[0])*.15:return False
    x0,y0=int(np.ceil(max(a[0],b[0]))),int(np.ceil(max(a[1],b[1])))
    x1,y1=int(min(a[2],b[2])),int(min(a[3],b[3]))
    patch=frame[y0:y1,x0:x1]
    if not patch.size:return True
    background,_=colors(frame,a)
    # Only tolerate empty OCR margins, never actual overlapping glyph pixels.
    return bool(np.max(np.abs(patch.astype(float)-background))<24)


def horizontal_decorations(frame):
    """Preserve long rules and performance bars even inside loose OCR padding."""
    gray=cv2.cvtColor(frame[:,:,:3],cv2.COLOR_BGR2GRAY)
    if len(gray)<25:return np.zeros(gray.shape,np.uint8)
    values=gray.astype(np.int16)
    above=np.abs(values-np.roll(values,6,axis=0))
    below=np.abs(values-np.roll(values,-6,axis=0))
    ink=(np.minimum(above,below)>16).astype(np.uint8)
    ink[:12]=0;ink[-12:]=0
    mask=cv2.morphologyEx(ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(80,1)))
    return cv2.dilate(mask,cv2.getStructuringElement(cv2.MORPH_RECT,(5,9)))


def equipment_blocks(frame,lines,on_ignored=None):
    samples={}
    def sample(box):
        if box not in samples:samples[box]=colors(frame,box)
        return samples[box]
    selected=[]
    for line in lines:
        if decoration_on_rule(frame,line) or equipment_decoration(line,lines) or solid_gem_shape(frame,line):
            if on_ignored:on_ignored(line)
        else:selected.append(line)
    def boundary(previous,current):
        text=previous.text.strip()
        if len(text)>60 or CONDITION.search(text) or ACTION.search(text) or BRANCH.match(text):return False
        a,b=bounds(previous),bounds(current)
        if a is None or b is None:return False
        _,color_a=sample(a);_,color_b=sample(b)
        return ((a[3]-a[1])>1.2*(b[3]-b[1]) or
                np.linalg.norm(np.array(color_a)-np.array(color_b))>60)
    blocks=card_blocks(selected,separate_fields=True,boundary=boundary)
    output=[]
    for block in blocks:
        if len(block.lines)>1:
            first,second=block.lines[:2]
            a,b=bounds(first),bounds(second)
            text=first.text.strip()
            if a and b and len(text)<=60 and not (CONDITION.search(text) or ACTION.search(text) or BRANCH.match(text)):
                _,color_a=sample(a);_,color_b=sample(b)
                title=(a[3]-a[1])>1.2*(b[3]-b[1]) or np.linalg.norm(np.array(color_a)-np.array(color_b))>60
                if title:
                    output.append(OCRBlock((first,)))
                    output.append(OCRBlock(block.lines[1:],block.warning))
                    continue
        output.append(block)
    return blocks if not output else output


def capture_layout(region,frame,blocks,reserved_boxes=(),literal_pattern=LITERAL_NUMBER):
    samples={}
    def sample(box):
        if box not in samples:samples[box]=colors(frame,box)
        return samples[box]
    height,width=frame.shape[:2]
    if (width,height)!=(region.width,region.height):raise ValueError('裝備擷取尺寸與框選範圍不一致。')
    boxes=[]
    for block in blocks:
        rectangles=[bounds(line) for line in block.lines]
        if not rectangles or any(box is None for box in rectangles):raise ValueError('裝備文字缺少位置，無法原位覆蓋。')
        rectangle=(min(b[0] for b in rectangles),min(b[1] for b in rectangles),
                   max(b[2] for b in rectangles),max(b[3] for b in rectangles))
        if rectangle[0]<0 or rectangle[1]<0 or rectangle[2]>width or rectangle[3]>height:
            raise ValueError('裝備文字位置超出框選範圍。')
        boxes.append(rectangle)
    for index,a in enumerate(boxes):
        for b in boxes[index+1:]:
            overlap_y=min(a[3],b[3])-max(a[1],b[1])
            if (min(a[2],b[2])>max(a[0],b[0]) and overlap_y>min(a[3]-a[1],b[3]-b[1])*.25
                    and not padding_overlap(frame,a,b)):
                raise ValueError('裝備文字區塊互相重疊，請核對辨識畫面。')
    backdrop=frame[:,:,:3].copy()
    decorations=horizontal_decorations(frame)
    for block in blocks:
        if len(block.lines)==1 and literal_pattern.fullmatch(block.text.strip()):continue
        for line in block.lines:
            box=bounds(line);background,_=sample(box)
            x0,y0,x1,y1=box
            # Cover the complete OCR rectangle plus a two-pixel antialias rim.
            left,top=max(0,int(x0)-2),max(0,int(y0)-2)
            right,bottom=min(width,int(np.ceil(x1))+2),min(height,int(np.ceil(y1))+2)
            patch=backdrop[top:bottom,left:right]
            patch[decorations[top:bottom,left:right]==0]=background
    # Adjacent labels' antialias padding must not touch a preserved number.
    for block in blocks:
        if len(block.lines)==1 and literal_pattern.fullmatch(block.text.strip()):
            x0,y0,x1,y1=bounds(block.lines[0])
            x0,y0=int(x0),int(y0);x1,y1=int(np.ceil(x1)),int(np.ceil(y1))
            backdrop[y0:y1,x0:x1]=frame[y0:y1,x0:x1,:3]
    slots=[]
    for index,(block,box) in enumerate(zip(blocks,boxes)):
        x0,y0,x1,y1=box
        glyph_height=float(np.median([bounds(line)[3]-bounds(line)[1] for line in block.lines]))
        right=float(width-2)
        for other in reserved_boxes:
            if other[0]>=x1 and min(other[3],y1)-max(other[1],y0)>min(other[3]-other[1],y1-y0)*.25:
                right=min(right,other[0]-2)
        for other in boxes:
            if other is box:continue
            if min(other[3],y1)-max(other[1],y0)>min(other[3]-other[1],y1-y0)*.25:
                if other[0]>box[0] and other[0]>=x1-min(glyph_height*.6,(x1-box[0])*.15):right=min(right,other[0]-2)
                elif other[0]<box[0] and other[2]>x0:x0=max(x0,other[2]+2)
        # Keep paragraphs in their observed vertical band. Empty space below
        # a tooltip is not permission to enlarge a translated effect forever.
        bottom=min(float(height-2),y1+max(4,glyph_height*.5))
        for other in boxes:
            if other[1]>y0+glyph_height*.5 and other[0]<right and other[2]>x0:bottom=min(bottom,other[1]-1)
        # Do not extend a translated label into the performance bar beneath it.
        low=max(0,int(y0+glyph_height*.8));high=min(height,int(np.ceil(bottom)))
        band=decorations[low:high,max(0,int(x0)):min(width,int(right))]
        if band.size:
            barriers=np.flatnonzero(band.mean(axis=1)>.35)
            if len(barriers):bottom=min(bottom,float(low+barriers[0]))
        if right<=x0 or bottom<=y0:raise ValueError('裝備文字區塊互相重疊，請核對辨識畫面。')
        background,foreground=sample(bounds(block.lines[0]))
        literal=block.text.strip() if len(block.lines)==1 and literal_pattern.fullmatch(block.text.strip()) else ''
        # Preserve each observed text color; never impose a semantic palette.
        rectangles=[bounds(line) for line in block.lines]
        centers=[(r[0]+r[2])/2 for r in rectangles]
        centered=(len(rectangles)>1 and max(centers)-min(centers)<glyph_height*.35 and
                  max(r[0] for r in rectangles)-min(r[0] for r in rectangles)>glyph_height*.7)
        centered |= abs(centers[0]-width/2)<glyph_height*.35 and box[0]>width*.15 and box[2]<width*.85
        alignment='center' if centered and not literal else 'left'
        if alignment=='center':right=min(right,box[2])
        slots.append(EquipmentSlot(box,(x0,y0,right,bottom),foreground,max(8,glyph_height*.90),literal,alignment))
    return EquipmentLayout(region,width,height,backdrop.tobytes(),tuple(slots))
