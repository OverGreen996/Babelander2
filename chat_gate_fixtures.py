"""Two pre-rendered animation phases per chat frame, five motion families."""
import numpy as np
from chat_fixtures import STYLES

SCENES=('jitter14','waves','translucent','particles','jitter8')

def variants(frame,index):
    scene=SCENES[index//20];rng=np.random.default_rng(331+index)
    bg=np.array(STYLES[index//20][4][::-1],dtype=np.int16)
    ink=np.any(frame!=bg,axis=2);yy,xx=np.indices(frame.shape[:2]);result=[]
    for phase in range(2):
        if scene.startswith('jitter'):
            amplitude=int(scene[6:])
            image=np.clip(frame.astype(np.int16)+rng.integers(-amplitude,amplitude+1,frame.shape,dtype=np.int16),0,255).astype(np.uint8)
        else:
            wave=(25+22*np.sin(xx/80+phase*.8)+15*np.sin(yy/100-phase*.5)).astype(np.int16)
            image=np.clip(bg+wave[:,:,None],0,255).astype(np.uint8)
            image[ink]=frame[ink]
            if scene=='translucent':image=np.clip(frame.astype(np.int16)+wave[:,:,None],0,255).astype(np.uint8)
            if scene=='particles':
                for j in range(25):
                    x=(j*97+phase*19)%(frame.shape[1]-8);y=(j*71+phase*11)%(frame.shape[0]-8)
                    image[y:y+5,x:x+5]=(120,130,150)
                image[ink]=frame[ink]
        result.append(image)
    return result
