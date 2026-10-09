"""Inspect geometric false glyphs in recorded OCR; no model or desktop."""
import json,cv2,numpy as np
from babelander.equipment_layout import solid_gem_shape,colors
from babelander.types import OCRLine
from pathlib import Path
p=Path(__file__).parent/'test-results/equipment-structures-a11-baseline'
d=json.loads((p/'report.json').read_text(encoding='utf8'))
for r in d['runs']:
    im=cv2.imread(str(p/(r['id']+'-original.png')))
    for l in r.get('ocr_lines',[]):
        if len(l['text'])!=1 or l['confidence']>.85:continue
        q=np.array(l['box'],np.float32);x,y,w,h=cv2.boundingRect(q)
        crop=im[y:y+h,x:x+w];mask=np.zeros((h,w),np.uint8)
        cv2.fillConvexPoly(mask,np.rint(q-[x,y]).astype(np.int32),1)
        bg=np.median(np.concatenate((crop[:2].reshape(-1,3),crop[-2:].reshape(-1,3),crop[:,:2].reshape(-1,3),crop[:,-2:].reshape(-1,3))),axis=0)
        ink=np.max(np.abs(crop.astype(float)-bg),axis=2)>24
        contours,_=cv2.findContours(ink.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        c=max(contours,key=cv2.contourArea);polygon=cv2.approxPolyDP(c,.045*cv2.arcLength(c,True),True)
        filled=np.zeros_like(mask);cv2.drawContours(filled,[c],-1,1,-1)
        print(json.dumps({'id':r['id'],'text':l['text'],'confidence':l['confidence'],'ignored':solid_gem_shape(im,OCRLine(l['text'],l['box'],l['confidence'])),'background':colors(im,(x,y,x+w-1,y+h-1))[0],'ink_fraction':round(float(ink[mask>0].mean()),3),'solidity':cv2.contourArea(c)/max(1,cv2.contourArea(cv2.convexHull(c))),'coverage':float(ink[filled>0].mean()),'polygon':polygon.reshape(-1,2).tolist(),'box':l['box']},ensure_ascii=True))
