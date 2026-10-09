"""Procedural, labelled equipment UI fixtures. No OCR coordinates enter the app."""
from dataclasses import dataclass
import numpy as np
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QFontMetrics,QLinearGradient,QPen,QBrush,QPolygonF

STYLES=[
    ('dark_gold','暗黑奇幻金框','Georgia',(23,20,17),(239,230,208),(233,186,90)),
    ('mmo_blue','大型多人奇幻藍框','Arial',(20,29,48),(231,238,247),(128,203,244)),
    ('souls_iron','古典硬派鐵框','Times New Roman',(25,25,24),(207,205,188),(203,183,133)),
    ('scifi_cyan','科幻終端青框','Consolas',(10,23,31),(217,237,236),(82,225,218)),
    ('comic_loot','漫畫射擊紫框','Trebuchet MS',(39,22,53),(251,240,237),(255,201,74)),
    ('light_parchment','亮色羊皮紙','Georgia',(231,220,187),(43,32,21),(125,69,20)),
    ('minimal_white','亮色策略資訊框','Segoe UI',(230,235,241),(29,40,55),(30,74,128)),
    ('retro_green','復古生存綠框','Courier New',(14,24,17),(210,226,187),(131,211,134)),
]
LAYOUTS=('standard','two_columns','conditions','compact')

@dataclass
class Fixture:
    identifier:str
    theme:str
    pattern:str
    image:QImage
    frame:np.ndarray
    rows:list
    art_bounds:tuple
    markers:tuple

def make(theme_index,pattern_index):
    key,title,family,bg,fg,accent=STYLES[theme_index]
    pattern=LAYOUTS[pattern_index];ordinal=theme_index*4+pattern_index
    w,h=(760,780) if pattern=='two_columns' else (460,720) if pattern=='compact' else (640,780)
    image=QImage(w,h,QImage.Format.Format_BGR888)
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient=QLinearGradient(0,0,w,h)
    gradient.setColorAt(0,QColor(*bg));gradient.setColorAt(1,QColor(*[max(0,min(255,c+(9 if theme_index%2 else -7))) for c in bg]))
    painter.fillRect(QRectF(0,0,w,h),QBrush(gradient))
    # Fine grain and diagonal lighting stay below text contrast; fixed seed.
    painter.setPen(QColor(*bg,90))
    for y in range(15,h-15,17):painter.drawLine(12,y,w-12,y+12)
    painter.setPen(QPen(QColor(*accent),3));painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(7,7,w-14,h-14),12,12)
    painter.setPen(QPen(QColor(*accent,110),1));painter.drawRoundedRect(QRectF(13,13,w-26,h-26),8,8)
    for x,y,sx,sy in ((17,17,1,1),(w-17,17,-1,1),(17,h-17,1,-1),(w-17,h-17,-1,-1)):
        painter.drawLine(x,y,x+27*sx,y);painter.drawLine(x,y,x,y+27*sy)
    rows=[];body_size=16 if pattern=='compact' else 20
    def text(content,x,y,size=None,color=None,max_width=None,group='field',italic=False):
        font=QFont(family);font.setPixelSize(size or body_size);font.setItalic(italic)
        metrics=QFontMetrics(font);painter.setFont(font);painter.setPen(QColor(*(color or fg)))
        limit=max_width if max_width is not None else w-x-28
        parts=[];current=''
        for word in content.split():
            test=(current+' '+word).strip()
            if current and metrics.horizontalAdvance(test)>limit:parts.append(current);current=word
            else:current=test
        if current:parts.append(current)
        lead=metrics.height()+4
        for part in parts:
            painter.drawText(x,y,part)
            box=metrics.boundingRect(part)
            rows.append({'text':part,'bounds':[x+box.x(),y+box.y(),x+box.x()+box.width(),y+box.y()+box.height()],
                         'group':group,'font_pixels':font.pixelSize(),'color':color or fg})
            y+=lead
        return y
    item=('Silver Longbow','Iron Dagger','Guardian Pendant','Old Lantern')[pattern_index]
    text(item,27,43,28 if pattern!='compact' else 24,accent,max_width=w-175,group='title')
    text('Legendary',28,75,18 if pattern!='compact' else 16,accent,group='rarity')
    text(('Longbow','Dagger','Pendant','Lantern')[pattern_index],28,101,group='type')
    text(f'Item Level {101+ordinal}',28,130,group='level')
    power=str(721+ordinal*13)
    text(power,28,188,43 if pattern!='compact' else 36,group='literal')
    text('Attack Power',145,180,group='power_label',max_width=w-300)
    text('Attack Speed',28,223,group='speed_label',max_width=180)
    text(f'{.91+ordinal/100:.2f}',230,223,group='literal')
    # A stylised weapon illustration, not text or a generated model image.
    art=(w-135,35,w-30,190)
    painter.setPen(QPen(QColor(*accent),1));painter.setBrush(QColor(*bg))
    painter.drawRoundedRect(QRectF(art[0],art[1],105,155),5,5)
    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(145,156,169))
    cx=w-82
    painter.drawPolygon(QPolygonF([QPointF(cx,48),QPointF(cx+15,132),QPointF(cx,145),QPointF(cx-12,129)]))
    painter.setBrush(QColor(*accent));painter.drawRoundedRect(QRectF(cx-25,133,50,8),3,3)
    painter.setBrush(QColor(104,77,49));painter.drawRoundedRect(QRectF(cx-5,141,10,30),3,3)
    if pattern=='two_columns':
        for i,(left,right) in enumerate(zip(
            [f'Damage: {125+ordinal}',f'Critical Chance: {12+ordinal}%',f'Durability: {130+ordinal} / {130+ordinal}'],
            [f'Armor: {84+ordinal}',f'Fire Resistance: {18+ordinal}%',f'Required Level: {60+ordinal}'])):
            text(left,28,272+i*40,max_width=320,group='left_column')
            text(right,402,272+i*40,max_width=330,group='right_column')
        y=406
    else:
        for i,affix in enumerate([f'+ {132+ordinal} Strength',f'+ {89+ordinal} Vitality',
                                  f'+ {14+ordinal}% Critical Chance',f'+ {26+ordinal}% Critical Damage']):
            text(affix,28,266+i*(27 if pattern=='compact' else 31),group='affix')
        y=400 if pattern!='compact' else 387
    markers=[]
    if pattern=='conditions':
        for part in ['If health is below 30%,',f'gain +{12+ordinal}% movement speed for 5 seconds.',
                     f'Otherwise, gain +{3+ordinal}% fire resistance.']:
            y=text(part,28,y,max_width=w-60,group='condition')
        markers.append('otherwise')
    elif pattern=='compact':
        y=text(f'Do not equip this item before level {70+ordinal}.',28,y,max_width=w-60,group='negative')
        markers.extend(('negative','level_timing'))
        y=text('When you block an attack, restore 10% health.',28,y+12,max_width=w-60,group='long_effect')
    else:
        y=text(f'Gain +{12+ordinal}% movement speed for 5 seconds.',28,y,max_width=w-60,group='effect')
    y+=18
    for i in range(2):
        painter.setPen(QPen(QColor(*accent),1));painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(28,y-16,18,18))
        y=text('Empty Socket',59,y,max_width=w-90,group='socket')+8
    # Footers are anchored, keeping clear of the deliberately dense main body.
    footer=max(y+18,h-105)
    if footer>h-88:footer=h-88
    painter.setPen(QColor(*accent,160));painter.drawLine(25,footer-23,w-25,footer-23)
    text(f'Required Level: {70+ordinal}',28,footer,group='required')
    text('Classes: Warrior, Paladin',28,footer+26,group='classes')
    footer_size=14 if pattern=='compact' else 16
    text(f'Durability: {130+ordinal} / {130+ordinal}',28,h-27,footer_size,group='bottom_left',max_width=w*.55-35)
    text(f'Sell Price: {56320+ordinal*71:,}',round(w*.57),h-27,footer_size,group='bottom_right',max_width=w*.43-27)
    painter.end()
    # QImage rows can be padded: copy only visible BGR pixels.
    frame=np.frombuffer(image.bits(),np.uint8).reshape(h,image.bytesPerLine())[:,:w*3].reshape(h,w,3).copy()
    return Fixture(f'{key}-{pattern}',title,pattern,image,frame,rows,art,tuple(markers))

def fixtures():return [make(theme,pattern) for theme in range(len(STYLES)) for pattern in range(len(LAYOUTS))]
