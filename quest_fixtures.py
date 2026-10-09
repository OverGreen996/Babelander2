"""Independently authored quest structures. Ground truth is evaluation only."""
from equipment_game_fixtures import Canvas

DARK=(20,27,36); WHITE=(232,237,244); GOLD=(245,205,125); BLUE=(134,204,246); GREEN=(133,220,171)

def npc(v):
    c=Canvas(800,620,DARK,WHITE,GOLD,'Georgia')
    c.rect(8,8,784,604,(26,33,43),GOLD,12)
    c.icon((28,104,212,354),'helmet',GOLD)
    c.text(('Captain Rowan','Keeper of the Gate')[v],28,63,25,GOLD,panel='header')
    c.text(('The Missing Patrol','A Quiet Rescue')[v],242,132,27,GOLD,panel='story',group='title')
    c.text(('Our scouts vanished near the bridge. Bring them home before nightfall.',
            'The prisoners are still alive. Do not enter the dungeon until the guard leaves.')[v],242,182,22,width=516,panel='story',group='paragraph')
    c.rule(242,286,510)
    c.text('Objectives',242,330,22,GOLD,panel='goals')
    c.text(('Find the missing scouts.','Rescue the prisoners.')[v],242,369,22,BLUE,panel='goals')
    c.text(f'{v+1} / 3',242,408,22,GREEN,panel='progress',group='literal')
    c.text('Rewards',28,475,22,GOLD,panel='rewards')
    c.text(f'{250+v*100} gold',28,516,22,panel='rewards')
    c.rect(242,548,190,45,(40,73,56),GREEN,7);c.rect(556,548,194,45,(64,42,46),(187,139,146),7)
    c.text('Accept',286,579,22,GREEN,panel='accept');c.text('Decline',599,579,22,panel='decline')
    return c.finish(f'npc-{v}','NPC 委託面板','npc_dialog',('左側頭像','右側敘述與目標','底部雙按鈕','進度保留'),('negative',) if v else ())

def tracker(v):
    c=Canvas(420,490,(12,20,29),WHITE,GOLD)
    c.rect(6,6,408,478,(19,29,39),(65,83,104),9)
    c.text('Main Quest',24,45,21,GOLD,panel='header')
    c.text(('Cross the Broken Bridge','Return to the Watchtower')[v],24,84,23,GOLD,width=365,panel='quest1',group='title')
    c.rect(25,138,12,12,None,GOLD)
    c.text(('Find a safe crossing.','Speak to the captain.')[v],48,152,20,width=350,panel='goal1')
    c.text(f'{v+1} / 4',48,188,20,GREEN,panel='progress1',group='literal');c.bar(48,207,330,.25*(v+1),GREEN)
    c.rule(24,239,370)
    c.text('Side Quest',24,278,21,BLUE,panel='header2')
    c.text(('Gather Healing Herbs','Repair the Beacon')[v],24,319,23,BLUE,panel='quest2',group='title')
    c.text(('Collect 5 herbs.','Collect 8 crystals.')[v],48,362,20,panel='goal2')
    c.text(f'{2+v} / {5+v*3}',48,400,20,GREEN,panel='progress2',group='literal');c.bar(48,419,330,.4,GREEN)
    c.text('Track',300,465,20,BLUE,panel='button')
    return c.finish(f'tracker-{v}','HUD 側邊快捷任務欄','hud_tracker',('窄版置右','雙任務區','勾選框','進度條'))

def journal(v):
    c=Canvas(980,670,DARK,WHITE,BLUE)
    c.text('Quest Journal',32,49,28,BLUE,panel='header')
    c.rule(30,72,920)
    c.rect(24,100,220,540,(29,40,54),(61,82,107),7)
    c.text('Main Quest',42,144,20,GOLD,panel='nav')
    c.text(('The Lost Village','Beyond the Walls')[v],42,186,21,width=185,panel='nav')
    c.text('Side Quest',42,275,20,BLUE,panel='nav2')
    c.icon((50,360,217,548),'shield',BLUE)
    c.text(('The Lost Village','Beyond the Walls')[v],278,135,29,GOLD,panel='intro',group='title')
    c.text('Description',278,183,21,BLUE,panel='intro')
    c.text(('A storm has cut off the village. The survivors need food and medicine.',
            'The walls are damaged. Help the villagers prepare before the next attack.')[v],278,226,22,width=650,panel='intro',group='paragraph')
    c.rule(278,321,650)
    c.text('Objectives',278,365,22,BLUE,panel='goals')
    c.text(('Deliver 6 supplies to the village.','Repair 4 gates before sunset.')[v],278,409,22,panel='goals')
    c.text('Optional',278,464,21,GREEN,panel='optional')
    c.text(('Speak to the wounded scout.','Find the missing carpenter.')[v],278,508,22,panel='optional')
    c.text('Rewards',278,574,21,GOLD,panel='rewards')
    c.text(f'{600+v*200} gold',278,615,22,panel='rewards')
    c.text('Abandon',796,615,22,(247,163,163),panel='button')
    return c.finish(f'journal-{v}','任務日誌介紹欄','journal_two_columns',('左側任務清單','右側段落','選擇性目標','放棄按鈕'))

def parchment(v):
    c=Canvas(560,660,(223,210,179),(53,44,34),(110,62,26),'Georgia')
    c.rect(12,12,536,636,(230,219,191),(130,98,58),12)
    c.text('Bounty Contract',280,64,28,(110,62,26),align='center',panel='header')
    c.rule(36,88,488,(130,98,58))
    c.text(('The Bandit King','The Stolen Relic')[v],280,137,27,(110,62,26),align='center',panel='title')
    c.text(('Defeat the bandit leader and return with proof. Do not harm the villagers.',
            'Recover the relic from the ruins. Do not sell it before returning to the shrine.')[v],40,186,23,width=475,panel='story',group='paragraph')
    c.text('Objectives',40,345,22,(110,62,26),panel='goals')
    c.text(('Defeat the leader.','Recover the relic.')[v],40,388,23,panel='goals')
    c.text('Rewards',40,451,22,(110,62,26),panel='rewards')
    c.text(f'{900+v*300} gold',40,493,23,panel='rewards')
    c.icon((415,435,515,535),'gem',(109,65,34))
    c.rule(36,562,488,(130,98,58))
    c.text('Accept',68,611,23,(110,62,26),panel='accept');c.text('Decline',370,611,23,panel='decline')
    return c.finish(f'parchment-{v}','羊皮紙懸賞','parchment_offer',('淺色紙面深字','置中標題','長敘述','封印與簽署'),('negative',))

def terminal(v):
    c=Canvas(820,520,(8,20,26),(182,236,227),(92,223,216),'Consolas')
    c.rect(10,10,800,500,(11,27,34),(92,223,216))
    c.text('Mission Briefing',28,51,28,panel='header');c.icon((660,90,790,217),'chip')
    c.text(('Secure the Relay','Disable the Turrets')[v],28,118,27,panel='title')
    c.text(('Restore the relay before the signal is lost.','Disable the turrets without damaging the reactor.')[v],28,162,22,width=596,panel='story',group='paragraph')
    c.rule(28,245,755)
    c.text('Time remaining',28,290,22,panel='timer_label');c.text(('01:30','02:45')[v],475,290,24,(255,200,135),panel='timer',group='literal')
    c.text('Progress',28,338,22,panel='progress_label');c.text(f'{v+1} / 4',475,338,24,panel='progress',group='literal')
    c.bar(28,364,730,.25*(v+1),(92,223,216))
    c.text('Rewards',28,414,22,panel='reward_label');c.text(f'{500+v*250} credits',400,414,22,panel='reward')
    c.text('Track',28,483,22,panel='track');c.text('Close',660,483,22,panel='close')
    return c.finish(f'terminal-{v}','科幻終端任務表','terminal_rows',('等寬字','欄位與右側數值','倒數','資料板與晶片'))

def banner(v):
    c=Canvas(1040,300,(31,39,41),WHITE,GREEN)
    c.rect(5,5,1030,290,(31,39,41),(97,150,125),12)
    c.icon((24,78,150,230),'bag',GREEN)
    c.text(('World Event: Supply Run','World Event: Safe Passage')[v],178,58,29,GREEN,panel='header')
    c.text(('Deliver 3 supply crates.','Escort 2 caravans.')[v],178,119,24,panel='goal')
    c.text(f'{v+1} / {3-v}',178,165,23,GREEN,panel='progress',group='literal');c.bar(178,190,490,.35,GREEN)
    c.text(('Stay near the wagon.','Do not leave the road.')[v],178,244,22,width=490,panel='hint')
    c.rect(747,90,258,175,(43,58,54),(97,150,125),9)
    c.text('Rewards',770,127,23,GREEN,panel='rewards');c.text(f'{100+v*100} gold',770,171,23,panel='rewards')
    c.text('Track',770,237,23,GREEN,panel='button')
    return c.finish(f'banner-{v}','世界事件橫幅','world_event_banner',('寬橫幅','左圖示','中目標','獨立右獎勵區'),('negative',) if v else ())

def board(v):
    c=Canvas(1010,390,(25,22,37),WHITE,(209,182,251))
    c.text('Daily Quests',26,48,28,(209,182,251),panel='header')
    for i in range(3):
        x=20+i*330;panel=f'tile{i}'
        c.rect(x,78,310,292,(36,31,49),(116,98,148),10)
        c.icon((x+220,99,x+289,168),'gem',(209,182,251))
        c.text(('Supply Run','Night Watch','Herb Hunt')[i],x+17,135,23,(209,182,251),width=196,panel=panel,group='title')
        c.text((f'Deliver {3+v} crates.',f'Defeat {5+v} enemies.',f'Collect {8+v} herbs.')[i],x+17,212,21,width=280,panel=panel,group='goal')
        c.text(f'{v+1} / {3+v+i*2}',x+17,254,21,GREEN,panel=panel,group='literal')
        c.bar(x+17,277,270,.3,GREEN)
        c.text('Track',x+17,340,21,(209,182,251),panel=panel)
    return c.finish(f'board-{v}','每日委託三格看板','daily_tiles',('三個獨立卡片','個別圖示','各自進度','各自按鈕'))

def briefing(v):
    c=Canvas(680,680,(35,42,49),WHITE,GOLD)
    c.text('Mission Briefing',24,50,28,GOLD,panel='header');c.rule(24,78,630)
    c.icon((24,108,162,254),'helmet',GOLD)
    c.text(('Commander Vale','Scout Mira')[v],194,137,25,GOLD,panel='npc')
    c.text(('The Last Beacon','A Way Through')[v],194,186,26,width=450,panel='title')
    c.text(('Light the beacon so the fleet can find the harbor.',
            'Find a path through the forest before the storm arrives.')[v],24,306,23,width=630,panel='story',group='paragraph')
    c.text('Objectives',24,420,23,GOLD,panel='goals')
    c.text(('Activate 2 beacons.','Find 3 trail markers.')[v],24,463,23,panel='goals')
    c.text('Optional',24,522,23,BLUE,panel='optional')
    c.text(('Do not alert the guards.','Do not cross the river yet.')[v],24,565,23,panel='optional')
    c.text('Complete Quest',24,638,23,GREEN,panel='complete');c.text('Close',560,638,23,panel='close')
    return c.finish(f'briefing-{v}','直式任務介紹','portrait_briefing',('上方頭像名牌','下方完整任務敘述','選擇目標','完成按鈕'),('negative',))

def fixtures():
    return [factory(v) for factory in (npc,tracker,journal,parchment,terminal,banner,board,briefing) for v in range(2)]
