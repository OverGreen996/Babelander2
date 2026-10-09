"""Render the independently composed fixture originals with their real ratios."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from bootstrap import prepare
prepare()
import json
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QRect
from PySide6.QtGui import QFontDatabase,QImage,QPainter,QColor,QFont
from equipment_game_fixtures import fixtures
ROOT=Path(__file__).resolve().parent
app=QApplication([])
for name in ('arial.ttf','georgia.ttf','times.ttf','consola.ttf','trebuc.ttf','segoeui.ttf','cour.ttf','msjh.ttc'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
items=fixtures();out=ROOT/'assets/equipment-game-structures-preview';out.mkdir(exist_ok=True)
overview=QImage(1700,1260,QImage.Format.Format_RGB32);p=QPainter(overview)
p.fillRect(overview.rect(),QColor('#111827'));p.setPen(QColor('#edf0f8'))
font=QFont('Microsoft JhengHei UI');font.setPixelSize(18);p.setFont(font)
bad=[]
for i,f in enumerate(items):
    f.image.save(str(out/(f.identifier+'.png')))
    for a in f.rows:
        x0,y0,x1,y1=a['bounds']
        if not (0<=x0<x1<=f.image.width() and 0<=y0<y1<=f.image.height()):bad.append((f.identifier,'outside',a))
    for j,a in enumerate(f.rows):
        for b in f.rows[j+1:]:
            x,y=a['bounds'],b['bounds']
            if min(x[2],y[2])>max(x[0],y[0]) and min(x[3],y[3])-max(x[1],y[1])>2:bad.append((f.identifier,'overlap',a['text'],b['text']))
    if i%2==0:
        idx=i//2;cell=QRect((idx%5)*340+12,(idx//5)*630+10,316,552)
        scaled=f.image.scaled(cell.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        p.drawImage(cell.x()+(cell.width()-scaled.width())//2,cell.y()+(cell.height()-scaled.height())//2,scaled)
        p.drawText(cell.x(),cell.y()+582,f.theme.split(' · ')[0])
        p.drawText(cell.x(),cell.y()+608,f.pattern)
p.end();overview.save(str(out/'overview.png'))
html=['<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>真正不同結構的遊戲物品框</title><style>body{background:#101723;color:#dbe6f5;font:17px system-ui;margin:28px}article{padding:22px;background:#1b2636;border-radius:16px;margin:30px 0}img{max-width:100%;height:auto}p{line-height:1.7}</style><h1>10 種結構 · 20 張物品介面</h1><p>自製遊戲風格原圖。橫向槍械、左右比較、卡牌、寶石、配方與模組；各自獨立排版，保持原圖比例。翻譯結果另行實測。</p><img src="overview.png" alt="十種物品框結構總覽">']
for f in items:
    html.append(f'<article><h2>{f.theme}</h2><p>'+ ' · '.join(f.structural_features)+f'</p><img src="{f.identifier}.png" alt="{f.theme} 自製原圖"></article>')
(out/'gallery.html').write_text(''.join(html),encoding='utf8')
print(json.dumps({'cases':len(items),'fixture_errors':bad},ensure_ascii=True))
assert not bad,bad
