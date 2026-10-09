"""100 ordinary cross-game chat messages; authored evaluation, no title lexicon."""
from dataclasses import dataclass
from PySide6.QtGui import QImage,QPainter,QFont,QFontMetrics,QColor
from PySide6.QtCore import QPointF
import numpy as np

TEXTS=[
 # Party / items / quantities
 'I need potions x4.', 'Can you drop 3 arrows?', 'I need item x4.', 'Anyone got a spare shield?',
 'Trade 2 gems for 5 coins?', 'Save one potion for me.', 'Need 10 wood and 6 stone.', 'Please give me 4 bandages.',
 'I have 2 keys left.', 'Do not sell the quest item.', 'Loot is on the ground.', 'Bag full, wait a sec.',
 'Take the loot, I already have it.', 'Need ammo ASAP.', 'I need mana, not health.', 'GG', 'gg wp', 'ty', 'np', 'brb 2 min',
 # Team tactics / competitive
 'Push left, two enemies there.', 'Hold the point for 30 seconds.', 'Do not push yet.', 'Enemy behind us!',
 'Cover me while I reload.', 'Heal me please, HP 20%.', 'Focus the healer first.', 'My ult is ready.',
 'Ult in 10 sec.', 'Need one more tank.', 'We need DPS, not another healer.', 'Low HP, fall back.',
 'Stay out of the red circle.', 'Do not pull the boss.', 'Pull in 3, 2, 1.', 'GL HF', 'nt', 'mb', 'afk 1 min', 'gg ez',
 # Cooperative / survival / matchmaking
 'LFG for a dungeon.', 'LFM 2 players, need a healer.', 'Invite me pls.', 'Party full?',
 'Where is the spawn point?', 'Respawn in 15 sec.', 'Meet at X:-12 Y:34.', 'Mark the exit on the map.',
 'Follow Player_007.', 'Do not open the gate until everyone is ready.', 'I am OOM.', 'OMW, wait for me.',
 'My ping is 180 ms.', 'Lag spike, sorry.', 'Can we pause for 2 minutes?', 'dc, back in a sec.',
 'Need mats for crafting.', 'Repair your gear before we leave.', 'Stack on me, then spread out.', 'Do not leave me behind.',
 # Traditional / mixed-language chatter
 '我需要道具X4', '我需要 potion x4', '等等，我還有 2 個任務。', '補師先不要拉怪',
 'GG 大家辛苦了', 'ty，救到我了', '我 OOM 了，等一下', '先別 push，隊友還沒到',
 '這把 lag 很嚴重', '我需要 3 個人來幫忙', 'DPS 集火右邊', 'HP 10%，快救我',
 'brb 2 min，我去拿水', '請在 Gate_02 等我', '不要賣掉 Item_X', '可以 trade 4 potions 嗎？',
 '剛剛 dc，現在回來了', 'boss 還有 5% HP', '這個 buff 只剩 10 sec', '今天最後一場，GL HF',
 # Ambiguity / chat brevity / longer wraps
 'nice shot!', 'good game everyone', 'well played', 'thanks for the carry',
 'I can tank, but I cannot heal.', 'The boss targets you, run away from the group.',
 'Keep the buff on the tank.', 'Need a rez near the bridge.', 'Do not waste the revive on me.',
 'WTS 4 gems, 200 gold each.', 'WTB 2 potions.', 'Need 3 more kills for the quest.',
 'Take 2, leave 4 for the next player.', 'Not enough ammo for another fight.',
 'We are not ready yet.', 'If the door is locked, wait here. Otherwise, follow me.',
 'Please do not trade away the four potions I dropped. Keep them for the healer until the next fight starts.',
 'When the boss turns toward the healer, the tank should move closer and the rest of us should stay behind the pillar.',
 'GG', 'GG',
]
assert len(TEXTS)==100

STYLES=[('party','[Party]',1080,25,(18,26,37),(133,205,248)),
        ('team','[Team]',820,24,(16,23,24),(148,224,167)),
        ('coop','[Group]',970,23,(34,27,24),(245,202,138)),
        ('mixed','[Guild]',1080,24,(28,22,38),(208,180,247)),
        ('compact','',710,23,(19,23,32),(236,188,161))]

def prefix(index):
    style=STYLES[index//20]
    return (style[1]+' ' if style[1] else '')+f'P{index+1:03d}:'

def chat_frame(indices):
    style=STYLES[indices[-1]//20];name,channel,width,size,bg,accent=style
    height=600
    image=QImage(width,height,QImage.Format.Format_BGR888);image.fill(QColor(*bg))
    painter=QPainter(image);font=QFont('Microsoft JhengHei UI');font.setPixelSize(size)
    painter.setFont(font);metrics=QFontMetrics(font);y=45;rows=[]
    for index in indices:
        content=prefix(index)+' '+TEXTS[index];parts=[];part=''
        # Word wrap without ever feeding the expected rows to the app.
        for word in content.split(' '):
            proposed=(part+' '+word).strip()
            if part and metrics.horizontalAdvance(proposed)>width-44:parts.append(part);part=word
            else:part=proposed
        if part:parts.append(part)
        for row_index,part in enumerate(parts):
            x=18 if row_index==0 else 48
            color=accent if row_index==0 else (233,238,245)
            painter.setPen(QColor(*color));painter.drawText(QPointF(x,y),part)
            rows.append({'index':index,'text':part,'x':x,'y':y,'color':color,'continuation':row_index>0})
            y+=metrics.height()+8
        y+=6
    assert y<height,(indices,y)
    painter.end()
    frame=np.frombuffer(image.bits(),np.uint8).reshape(height,image.bytesPerLine())[:,:width*3].reshape(height,width,3).copy()
    return image,frame,rows
