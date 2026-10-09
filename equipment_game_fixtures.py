"""Ten separately authored game UI structures, not palette variants of a card.

QPainter fixtures supply known source text for evaluation only. The OCR pipeline
receives pixels, never these coordinates or expected translations.
"""
from dataclasses import dataclass
import numpy as np
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QImage,QPainter,QFont,QFontMetrics,QColor,QPen,QBrush,QPolygonF,QLinearGradient

@dataclass
class GameFixture:
    identifier:str
    theme:str
    pattern:str
    image:QImage
    frame:np.ndarray
    rows:list
    art_bounds:tuple
    markers:tuple
    art_regions:tuple
    structural_features:tuple

class Canvas:
    def __init__(self,w,h,bg,fg,accent,family='Arial'):
        self.w,self.h,self.bg,self.fg,self.accent,self.family=w,h,bg,fg,accent,family
        self.rows=[];self.art=[]
        self.image=QImage(w,h,QImage.Format.Format_BGR888)
        self.p=QPainter(self.image);self.p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.p.fillRect(QRectF(0,0,w,h),QColor(*bg))
    def rect(self,x,y,w,h,fill,stroke=None,radius=0):
        self.p.setBrush(QColor(*fill) if fill else Qt.BrushStyle.NoBrush)
        self.p.setPen(QPen(QColor(*stroke),1) if stroke else Qt.PenStyle.NoPen)
        if radius:self.p.drawRoundedRect(QRectF(x,y,w,h),radius,radius)
        else:self.p.drawRect(QRectF(x,y,w,h))
    def polygon(self,points,fill,stroke=None):
        self.p.setPen(QPen(QColor(*stroke),1.5) if stroke else Qt.PenStyle.NoPen)
        self.p.setBrush(QColor(*fill));self.p.drawPolygon(QPolygonF([QPointF(*p) for p in points]))
    def rule(self,x,y,w,color=None):
        self.p.setPen(QPen(QColor(*(color or self.accent)),1));self.p.drawLine(QPointF(x,y),QPointF(x+w,y))
    def text(self,content,x,y,size=20,color=None,width=None,align='left',panel='main',group='field',italic=False,family=None):
        font=QFont(family or self.family);font.setPixelSize(size);font.setItalic(italic)
        metrics=QFontMetrics(font);self.p.setFont(font);self.p.setPen(QColor(*(color or self.fg)))
        limit=width or self.w-x-24;parts=[];row=''
        for word in content.split():
            test=(row+' '+word).strip()
            if row and metrics.horizontalAdvance(test)>limit:parts.append(row);row=word
            else:row=test
        if row:parts.append(row)
        for part in parts:
            advance=metrics.horizontalAdvance(part)
            left=x-advance/2 if align=='center' else x-advance if align=='right' else x
            self.p.drawText(QPointF(left,y),part);box=metrics.boundingRect(part)
            self.rows.append({'text':part,'bounds':[round(left+box.x()),round(y+box.y()),round(left+box.x()+box.width()),round(y+box.y()+box.height())],
                'font_pixels':size,'group':group,'color':color or self.fg,'panel':panel,'alignment':align})
            y+=metrics.height()+5
        return y
    def icon(self,rect,kind='shield',color=None):
        x0,y0,x1,y1=rect;w,h=x1-x0,y1-y0;cx=x0+w/2;cy=y0+h/2;accent=color or self.accent
        self.rect(x0,y0,w,h,tuple(min(255,c+8) for c in self.bg),None,8)
        if kind=='gun':
            self.polygon([(x0+w*.1,cy-h*.13),(x0+w*.68,cy-h*.13),(x0+w*.68,cy-h*.22),
                (x0+w*.82,cy-h*.22),(x0+w*.82,cy-h*.02),(x0+w*.92,cy-h*.02),
                (x0+w*.92,cy+h*.07),(x0+w*.45,cy+h*.07),(x0+w*.4,cy+h*.29),
                (x0+w*.29,cy+h*.27),(x0+w*.31,cy+h*.06),(x0+w*.1,cy+h*.06)],(137,151,165))
            self.rect(x0+w*.43,cy-h*.08,w*.21,h*.09,accent)
            self.polygon([(x0+w*.13,cy+h*.08),(x0+w*.24,cy+h*.08),(x0+w*.2,cy+h*.24),(x0+w*.1,cy+h*.22)],(64,76,94))
        elif kind=='shield':
            self.polygon([(cx,y0+h*.08),(x0+w*.83,y0+h*.22),(x0+w*.77,y0+h*.65),
                (cx,y0+h*.92),(x0+w*.23,y0+h*.65),(x0+w*.17,y0+h*.22)],(112,126,147),accent)
            self.polygon([(cx,y0+h*.23),(cx+w*.17,cy),(cx,y0+h*.75),(cx-w*.17,cy)],accent)
        elif kind=='chip':
            self.rect(x0+w*.25,y0+h*.22,w*.50,h*.55,(50,76,90),accent,4)
            self.rect(x0+w*.37,y0+h*.35,w*.26,h*.28,accent,None,3)
            for i in range(4):
                self.rect(x0+w*.09,y0+h*(.27+i*.13),w*.14,h*.045,(96,127,143))
                self.rect(x0+w*.77,y0+h*(.27+i*.13),w*.14,h*.045,(96,127,143))
        elif kind=='bottle':
            self.rect(cx-w*.16,y0+h*.10,w*.32,h*.12,accent,None,3)
            self.polygon([(cx-w*.14,y0+h*.22),(cx+w*.14,y0+h*.22),(cx+w*.14,y0+h*.34),
                (cx+w*.32,y0+h*.48),(cx+w*.30,y0+h*.84),(cx-w*.30,y0+h*.84),
                (cx-w*.32,y0+h*.48),(cx-w*.14,y0+h*.34)],(141,182,164),accent)
            self.rect(cx-w*.28,y0+h*.60,w*.56,h*.21,accent,None,4)
        elif kind=='helmet':
            self.polygon([(cx,y0+h*.12),(x0+w*.78,y0+h*.30),(x0+w*.80,y0+h*.73),
                (cx+w*.1,y0+h*.88),(cx,y0+h*.61),(cx-w*.1,y0+h*.88),
                (x0+w*.20,y0+h*.73),(x0+w*.22,y0+h*.30)],(151,143,124),accent)
            self.rect(cx-w*.23,cy-h*.03,w*.46,h*.10,(39,42,47))
        elif kind=='bag':
            self.rect(x0+w*.20,y0+h*.24,w*.6,h*.63,(112,91,61),accent,12)
            self.rect(x0+w*.28,y0+h*.51,w*.44,h*.23,(142,116,73),(74,59,41),4)
            self.rect(cx-w*.14,y0+h*.09,w*.28,h*.20,None,accent,8)
            self.rect(x0+w*.15,y0+h*.30,w*.09,h*.42,(72,60,45),None,2)
            self.rect(x0+w*.76,y0+h*.30,w*.09,h*.42,(72,60,45),None,2)
        else:
            self.polygon([(cx,y0+h*.13),(x0+w*.84,cy),(cx,y0+h*.86),(x0+w*.16,cy)],accent,(217,224,230))
            self.polygon([(cx,y0+h*.25),(x0+w*.66,cy),(cx,y0+h*.69)],(202,226,242))
        self.art.append(tuple(rect))
    def bar(self,x,y,w,value,color):
        self.rect(x,y,w,7,(48,55,64),None,2);self.rect(x,y,w*value,7,color,None,2)
        self.art.append((x,y,x+w,y+7))
    def finish(self,key,title,structure,features,markers=()):
        self.p.end()
        frame=np.frombuffer(self.image.bits(),np.uint8).reshape(self.h,self.image.bytesPerLine())[:,:self.w*3].reshape(self.h,self.w,3).copy()
        return GameFixture(key,title,structure,self.image,frame,self.rows,self.art[0],tuple(markers),tuple(self.art),tuple(features))

def rune_scroll(v):
    c=Canvas(440,730,(18,16,26),(224,218,234),(166,141,212),'Georgia')
    c.polygon([(8,28),(28,8),(412,8),(432,28),(432,700),(412,722),(28,722),(8,700)],(25,20,36),(120,100,160))
    c.rule(36,96,368);c.rule(36,263,368);c.rule(36,410,368);c.rule(36,566,368)
    c.text(('Frost Spear','Ashen Ring')[v],220,53,27,(203,165,244),width=390,align='center',panel='header',group='title')
    c.text(('Runed weapon','Ancient relic')[v],220,82,17,width=390,align='center',panel='header')
    for i,s in enumerate((f'Physical Damage: {83+v*16}',f'Cold Damage: {24+v*9}',f'Critical Chance: {8+v*3}%',f'Required Level: {42+v*6}')):
        c.text(s,220,129+i*36,20,width=380,align='center',panel='base')
    for i,s in enumerate((f'+{18+v*6}% Attack Speed',f'+{34+v*8}% Critical Damage',f'+{22+v*5} Dexterity')):
        c.text(s,220,301+i*37,20,(137,196,248),width=390,align='center',panel='affixes')
    c.text(('Attacks slow nearby enemies for 4 seconds.','When you block, gain 6% armor for 3 seconds.')[v],220,449,19,(188,169,232),width=340,align='center',panel='effect')
    c.text(('Do not use while frozen.','Do not equip this item before level 48.')[v],220,524,18,width=360,align='center',panel='restriction')
    c.icon((185,589,255,655),'gem',(134,178,234))
    c.text(('The winter remembers.','Ash hides the last light.')[v],220,693,16,(176,170,187),width=375,align='center',panel='flavor',italic=True)
    return c.finish(f'rune-scroll-{v}','符文流派 · 中置窄長卷軸','centered_scroll',('中置標頭／屬性','多層水平分隔','下方符文寶石','置中斜體敘述'),('negative',)+(('level_timing',) if v else ()))

def looter_weapon(v):
    c=Canvas(760,430,(23,26,38),(237,241,247),(233,89,201),'Trebuchet MS')
    c.polygon([(0,0),(735,0),(760,25),(760,91),(0,91)],(102,32,119))
    c.polygon([(0,91),(320,91),(275,276),(0,276)],(32,38,57))
    c.text(('BURST CARBINE','ARC SHOTGUN')[v],26,44,29,panel='header',group='title')
    c.text(('Epic burst rifle','Rare energy shotgun')[v],28,75,18,(243,170,232),panel='header')
    c.icon((21,111,285,245),'gun',(227,99,196))
    c.text('Weapon score',26,321,18,panel='score')
    c.text(str(386+v*74),28,369,43,(255,227,142),group='literal',panel='score')
    fields=(('Damage',146+v*35,.84),('Magazine',24+v*12,.59),('Accuracy',71+v*5,.71),('Fire rate',8+v*2,.47))
    for i,(label,value,amount) in enumerate(fields):
        y=126+i*53;c.text(label,348,y,19,panel='metrics');c.text(str(value),717,y,22,align='right',group='literal',panel='metrics')
        c.bar(348,y+12,370,amount,(186,104,223))
    c.rect(326,338,414,70,(39,45,64),None,5)
    c.text(('Reloading boosts damage by 12%.','Shots pierce 2 enemies.')[v],345,366,17,width=377,panel='perk')
    return c.finish(f'looter-weapon-{v}','射擊刷寶 · 橫向槍械性能面板','horizontal_weapon',('斜切稀有度色帶','左側橫向武器','右側性能條','獨立武器分數／技能區'))

def souls_inspection(v):
    c=Canvas(760,525,(31,30,27),(221,216,202),(166,150,110),'Times New Roman')
    c.rect(8,8,744,509,(31,30,27),(104,94,75));c.rect(9,9,742,67,(50,46,38))
    c.text(('Worn Knight Helm','Tower Guard Shield')[v],30,51,29,panel='header',group='title')
    c.icon((32,110,241,326),'helmet' if v==0 else 'shield',(163,143,99))
    c.text('Equipment weight',34,378,19,panel='art_caption');c.text(f'{4.8+v*2:.1f}',235,378,22,align='right',group='literal',panel='art_caption')
    c.text('DEFENSE',303,114,18,(178,162,126),panel='defense')
    for i,(label,value) in enumerate((('Physical',82+v*31),('Magic',39+v*13),('Fire',44+v*19),('Lightning',31+v*21))):
        y=154+i*38;c.text(label,305,y,20,panel='defense');c.text(str(value),494,y,22,align='right',group='literal',panel='defense')
    c.rule(289,285,225)
    c.text('RESISTANCE',543,114,17,(178,162,126),panel='resistance')
    for i,(label,value) in enumerate((('Poison',65+v*18),('Bleed',47+v*24),('Frost',29+v*33))):
        y=154+i*38;c.text(label,543,y,20,panel='resistance');c.text(str(value),719,y,22,align='right',group='literal',panel='resistance')
    c.rule(285,328,442)
    c.text('Required attributes',301,360,20,(178,162,126),panel='requirements')
    c.text(f'Strength: {16+v*8}',303,397,20,panel='requirements');c.text(f'Dexterity: {11+v*3}',529,397,20,panel='requirements')
    c.rule(28,432,703)
    c.text(('A battered helm worn by the gate guards.','A heavy shield bearing the mark of a forgotten king.')[v],29,473,20,width=700,panel='description',italic=True)
    return c.finish(f'souls-inspection-{v}','硬派動作 · 圖像與抗性檢視頁','inspection_sheet',('大圖居左','雙組抗性資料','底部需求欄','橫向描述／石質矩形框'))

def jrpg_compare(v):
    c=Canvas(760,640,(16,23,40),(229,235,250),(114,161,233),'Segoe UI')
    c.text('EQUIPMENT COMPARISON',25,41,24,(151,187,245),panel='banner',group='title')
    for index,(x,color) in enumerate(((14,(94,151,230)),(390,(232,190,99)))):
        c.rect(x,64,356,557,(28,39,63),color,14);c.rect(x+1,65,354,47,tuple(int(n*.37) for n in color),None,12)
        c.text(('Equipped','Candidate')[index],x+178,96,19,color,width=315,align='center',panel=f'card{index}-heading')
        name=(('Bronze Guard','Silver Guard'),('Moon Pendant','Sun Pendant'))[v][index]
        c.text(name,x+178,148,25,width=319,align='center',panel=f'card{index}-title',group='title')
        c.icon((x+119,177,x+237,294),'shield' if v==0 else 'gem',color)
        c.rule(x+22,319,310,color)
        for row,(label,value) in enumerate((('Attack',63+v*18+index*12),('Defense',88+v*13+index*21),('Magic',24+v*15+index*9))):
            y=358+row*47;c.text(label,x+24,y,20,panel=f'card{index}-stats');c.text(str(value),x+325,y,23,align='right',group='literal',panel=f'card{index}-stats')
        c.rect(x+20,482,316,68,(22,31,51),None,8)
        c.text(('No special effect.','Gain +8% fire resistance.')[index] if v==0 else ('Gain +5% armor.','Gain +9% magic damage.')[index],x+34,510,18,width=288,panel=f'card{index}-effect')
        c.text(f'Required Level: {20+v*12+index*4}',x+23,591,18,panel=f'card{index}-footer')
    return c.finish(f'jrpg-compare-{v}','角色扮演 · 左右裝備替換比較','side_by_side_compare',('兩張獨立完整卡','兩個獨立裝備圖','左右數值關聯','各自效果與需求'))

def mmo_socketed(v):
    c=Canvas(435,750,(13,22,36),(225,235,250),(125,175,234),'Arial')
    c.rect(5,5,425,740,(16,27,44),(70,110,168),5)
    c.icon((21,25,102,112),'shield' if v==0 else 'helmet',(107,149,205))
    c.text(('Sentinel Guard','Skywatch Helm')[v],121,57,24,(150,191,242),width=291,panel='title',group='title')
    c.text('Binds on pickup',121,93,17,panel='bind')
    c.text(('Off-hand shield','Plate armor')[v],24,154,20,panel='basic');c.text(f'Armor: {263+v*49}',24,187,20,panel='basic')
    c.text(f'+{38+v*7} Strength',24,230,21,(149,217,161),panel='affixes')
    c.text(f'+{56+v*9} Vitality',24,264,21,(149,217,161),panel='affixes')
    c.rule(22,293,389,(58,90,139));c.text('GEM SOCKETS',24,323,17,(149,173,205),panel='sockets_heading')
    for index,(label,color) in enumerate((('Ruby socket',(218,84,89)),('Sapphire socket',(81,143,220)),('Prismatic socket',(168,117,224)))):
        y=365+index*49;c.icon((24,y-24,50,y+3),'gem',color);c.text(label,65,y,18,panel='sockets')
    c.rect(21,504,393,115,(20,42,35),None,5)
    c.text(('Equip: blocking restores 3% health.','Equip: gain 14% cold resistance.')[v],33,534,18,(139,219,153),width=368,panel='equip_effect')
    c.text(('Use: gain +20% armor for 8 seconds.','Use: restore 12% health.')[v],33,580,18,(139,219,153),width=368,panel='use_effect')
    c.text(f'Requires level {45+v*7}',23,660,19,(234,145,144),panel='requirement')
    c.text(f'Durability: {86+v*9} / 100',23,696,18,panel='footer')
    c.text('Sell Price: 12,450',23,726,17,(196,201,213),panel='footer')
    return c.finish(f'mmo-sockets-{v}','多人線上 · 綁定與彩色插槽提示','socket_tooltip',('左上圖示與右側名稱','綁定規則','獨立彩色寶石列','綠色裝備／使用效果框'))

def moba_grid(v):
    c=Canvas(700,615,(233,239,235),(30,52,42),(49,121,90),'Segoe UI')
    c.rect(10,10,680,595,(243,247,243),(150,180,164),16)
    c.rect(11,11,678,83,(27,75,56),None,15)
    c.text(('Verdant Blade','Storm Talisman')[v],32,51,27,(225,246,233),panel='header',group='title')
    c.text(f'Total cost: {2450+v*650}',35,80,17,(173,224,192),panel='header')
    c.icon((31,123,167,255),'gem' if v else 'shield',(57,144,105))
    c.text(('Attack item','Support item')[v],191,147,20,panel='identity')
    c.text(('Built for sustained combat.','Protect allies with a burst of magic.')[v],191,187,18,width=452,panel='identity')
    values=(('+45','Attack Damage'),('+25%','Attack Speed'),('+250','Health')) if v==0 else (('+35','Magic Power'),('+15%','Movement Speed'),('+300','Health'))
    for index,(value,label) in enumerate(values):
        x=31+index*221;c.rect(x,283,200,96,(219,233,225),None,9)
        c.text(value,x+100,323,29,(33,112,75),width=175,align='center',group='literal',panel=f'stat{index}')
        c.text(label,x+100,359,17,width=184,align='center',panel=f'stat{index}')
    c.text('PASSIVE',32,423,17,(56,122,89),panel='passive')
    c.text(('Attacks deal 18 bonus damage to enemies.','When you heal an ally, gain 8% movement speed.')[v],32,457,20,width=635,panel='passive')
    c.rule(31,500,637,(165,190,174))
    c.text('ACTIVE',32,533,17,(56,122,89),panel='active')
    c.text(('Gain +12% movement speed for 5 seconds.','Restore 15% health to nearby allies.')[v],32,569,19,width=637,panel='active')
    return c.finish(f'moba-grid-{v}','競技對戰 · 三格屬性與主被動','attribute_grid',('橫向價格標頭','圖像加用途描述','三格大數值屬性','主動與被動分區'))

def scifi_modules(v):
    c=Canvas(760,635,(8,24,32),(200,234,239),(58,203,215),'Consolas')
    c.polygon([(9,34),(34,9),(717,9),(750,42),(750,606),(728,626),(9,626)],(11,31,43),(55,129,145))
    c.text(('REACTOR MOD KIT','SHIELD EMITTER')[v],30,56,29,(96,224,230),panel='header',group='title')
    c.text(('Power systems / auxiliary','Defensive systems / core')[v],31,88,17,panel='header')
    c.icon((33,124,237,334),'chip',(65,181,191))
    c.rect(266,124,464,210,(13,44,56),None,5)
    c.text(('MODULE OUTPUT','SHIELD PARAMETERS')[v],283,157,19,(86,207,222),panel='parameters')
    labels=(('Power','180'),('Heat','24%'),('Load','67%')) if v==0 else (('Capacity','340'),('Recovery','19%'),('Delay','6'))
    for i,(label,value) in enumerate(labels):
        y=202+i*45;c.text(label,285,y,20,panel='parameters');c.text(value,703,y,25,align='right',group='literal',panel='parameters')
    c.rule(31,361,696);c.text('INSTALLED COMPONENTS',33,394,18,(90,171,187),panel='components_header')
    for i,name in enumerate((('Cooling unit','Power relay','Control chip') if v==0 else ('Field coil','Shield relay','Sensor chip'))):
        x=31+i*236;c.rect(x,415,223,100,(17,43,53),(43,92,108),3)
        c.text(name,x+14,445,17,width=196,panel=f'module{i}')
        c.text(f'Level: {3+v+i}',x+14,485,19,panel=f'module{i}')
    c.text(('Do not activate while overheated.','Do not remove while the shield is active.')[v],32,564,19,(244,183,107),width=695,panel='warning')
    c.text(f'Required Level: {26+v*10}',33,604,18,panel='footer')
    return c.finish(f'scifi-modules-{v}','科幻裝配 · 模組與運作參數','modular_dashboard',('切角科技框','左側晶片示意','右側參數看板','底部三個元件格'),('negative',))

def survival_paper(v):
    c=Canvas(625,745,(216,205,173),(56,48,33),(131,95,52),'Georgia')
    c.polygon([(14,9),(604,15),(616,726),(30,735),(9,47)],(230,220,189),(158,138,103))
    c.rect(31,27,184,28,(173,151,109),None,2)
    c.text('FIELD EQUIPMENT',43,47,16,(49,45,34),panel='label')
    c.text(('Trail Pack','Herbal Remedy')[v],31,102,31,panel='header',group='title')
    c.text(('Survival gear','Medical consumable')[v],33,138,18,panel='header')
    c.icon((379,69,584,248),'bag' if v==0 else 'bottle',(111,135,70))
    for i,s in enumerate((f'Weight: {2.4-v*1.8:.1f} kg',f'Condition: {67+v*22} / 100',f'Value: {48+v*37}')):
        c.text(s,33,189+i*36,20,panel='metadata')
    c.rule(31,302,558,(162,145,112));c.text('CRAFTING MATERIALS',33,335,18,(117,84,48),panel='recipe_heading')
    ingredients=(('Leather','Cloth','Iron')) if v==0 else ('Herbs','Water','Cloth')
    for i,name in enumerate(ingredients):
        x=32+i*191;c.rect(x,358,177,78,(210,199,162),(167,151,115),4)
        c.text(name,x+14,389,19,panel=f'ingredient{i}');c.text(str((3,2,1)[i]+v),x+151,418,20,align='right',group='literal',panel=f'ingredient{i}')
    c.text('FIELD NOTES',34,489,18,(117,84,48),panel='notes_heading')
    c.text(('A sturdy pack with room for tools and supplies.','A bitter mixture prepared from wild plants.')[v],34,525,20,width=546,panel='notes',italic=True)
    c.text(('Carry 6 additional items.','Restore 25% health over 10 seconds.')[v],35,600,20,width=545,panel='effect')
    c.rect(30,638,565,65,(224,208,166),None,4)
    c.text(('Do not store near an open fire.','Do not use while bleeding.')[v],42,671,19,width=538,panel='warning')
    return c.finish(f'survival-paper-{v}','生存製作 · 材料配方與野外筆記','crafting_note',('不規則紙張輪廓','裝備圖在右上','三個材料需求格','斜體筆記／警告框'),('negative',))

def battle_card(v, health=7):
    c=Canvas(425,680,(22,27,42),(226,235,248),(139,162,218),'Georgia')
    c.rect(9,9,407,661,(29,41,64),(147,164,202),23)
    c.rect(18,18,389,87,(47,63,94),None,19)
    c.rect(22,25,53,58,(46,92,164),(133,191,247),17)
    c.text(str(3+v*2),48,67,33,(225,238,255),align='center',width=48,group='literal',panel='cost')
    c.text(('Flame Guardian','Healing Wave')[v],244,66,25,width=323,align='center',panel='name',group='title')
    c.icon((30,123,394,346),'shield' if v==0 else 'bottle',(217,135,72) if v==0 else (113,213,183))
    c.rect(31,355,362,34,(52,70,105),None,7)
    c.text(('UNIT / ELEMENTAL','SPELL / RESTORATION')[v],212,379,16,(181,205,244),width=340,align='center',panel='type')
    c.rect(31,403,362,172,(23,32,51),None,12)
    if v==0:
        c.text('When summoned, deal 3 damage to all enemies.',47,440,19,width=329,panel='ability')
        c.text('Do not attack friendly units.',47,515,18,(239,191,130),width=327,panel='restriction')
    else:
        c.text('Restore 8 health to an ally.',47,440,19,width=329,panel='ability')
        c.text('If the ally is frozen, remove the effect first.',47,500,18,(153,224,198),width=327,panel='conditional')
    c.rule(32,593,361,(94,113,149))
    if v==0:
        c.rect(30,608,154,48,(134,70,49),None,14);c.rect(241,608,154,48,(71,112,83),None,14)
        c.text('Attack',44,638,16,panel='attack');c.text('4',165,643,27,align='right',group='literal',panel='attack')
        c.text('Health',255,638,16,panel='health');c.text(str(health),374,643,27,align='right',group='literal',panel='health')
    else:
        c.text('A calm sea restores the spirit.',212,640,16,(166,190,211),width=359,align='center',italic=True,panel='flavor')
    return c.finish(f'battle-card-{v}','卡牌戰鬥 · 費用、技能與攻防角標','portrait_battle_card',('費用角標','中央大幅卡圖','技能區與類型帶','獨立攻擊／生命值或風味敘述'),('negative',) if v==0 else ())

def socket_gem(v):
    c=Canvas(750,620,(19,19,31),(229,227,244),(179,136,233),'Segoe UI')
    c.rect(10,10,730,600,(25,24,41),(112,84,167),10)
    c.rect(11,11,728,63,(57,37,86),None,9)
    c.text(('AMETHYST CORE','RUBY OF VIGOR')[v],30,52,27,(217,181,255),panel='header',group='title')
    c.icon((29,99,264,321),'gem',(166,106,228) if v==0 else (226,90,110))
    c.text(('Rare violet gem','Flawless red gem')[v],146,359,18,(198,160,231),width=235,align='center',panel='gem_caption')
    c.text('GEM PROPERTIES',309,118,18,(192,159,236),panel='properties')
    c.text(f'Gem Level: {4+v*3}',311,157,21,panel='properties')
    c.text(f'Quality: +{12+v*6}%',311,197,21,panel='properties')
    c.text(('Fits: blue or white sockets','Fits: red or white sockets')[v],311,237,18,width=393,panel='properties')
    c.text(f'Required Level: {36+v*14}',311,293,20,panel='requirements')
    c.rule(29,389,692,(97,75,132));c.text('SOCKET EFFECTS',30,425,19,(191,149,238),panel='effects_header')
    c.text(('Weapon: +18% magic damage','Weapon: +24% physical damage')[v],31,462,21,(158,205,247),panel='weapon_effect')
    c.text(('Armor: +12% cold resistance','Armor: +10% fire resistance')[v],31,502,21,(161,224,192),panel='armor_effect')
    c.text(('Jewelry: +9% maximum health','Jewelry: +15% critical chance')[v],31,542,21,(235,209,157),panel='jewelry_effect')
    c.text('Remove safely before replacing the gem.',32,587,17,(179,179,200),width=670,panel='note')
    return c.finish(f'socket-gem-{v}','寶石鑲嵌 · 品質與裝備部位效果','gem_properties',('大型切面寶石','等級／品質／插槽條件','武器／防具／飾品各自效果','取下與替換提示'))

BUILDERS=(rune_scroll,looter_weapon,souls_inspection,jrpg_compare,mmo_socketed,moba_grid,scifi_modules,survival_paper,battle_card,socket_gem)
def fixtures():return [builder(v) for builder in BUILDERS for v in range(2)]
