"""Small built-in item lexicon, applied after all explicit user glossary terms."""
import re

_TERMS = {'defeated enemies': '被擊敗的敵人', 'projectiles': '投射物', 'projectile': '投射物',
          'shields': '盾牌', 'shield': '盾牌',
          'legendary':'傳奇','rare':'稀有','uncommon':'魔法','common':'普通',
          'two-handed sword':'雙手劍','one-handed sword':'單手劍','empty socket':'空插槽'}
_TERMS.update({'weapon damage':'武器傷害','divine strike':'神聖打擊','heavy attacks':'重攻擊',
               'paladin':'聖騎士','warrior':'戰士','classes':'職業','bane':'剋星','lantern':'提燈',
               'longbow':'長弓','dagger':'匕首','pendant':'墜飾','boots':'靴子','ring':'戒指'})
_TERMS.update({'epic':'史詩','burst rifle':'點放步槍','burst carbine':'點放卡賓槍','carbine':'卡賓槍','shotgun':'霰彈槍','rifle':'步槍',
    'weapon':'武器','spear':'長矛','helm':'頭盔','amethyst':'紫水晶','ruby':'紅寶石','core':'核心'})
_NAME_TERMS={'bronze':'青銅','silver':'白銀','copper':'銅','iron':'鐵','steel':'鋼',
             'guard':'守衛','pack':'背包','trail':'小徑','runed':'符文'}
_NAME_PATTERN=re.compile(r'(?<![A-Za-z0-9_])(?:'+'|'.join(_NAME_TERMS)+r')(?![A-Za-z0-9_])',re.I)
# Common interface vocabulary, never complete fixture titles or effect answers.
_LABELS={'passive':'被動','active':'主動','gem sockets':'寶石插槽','gem properties':'寶石屬性',
    'socket effects':'鑲嵌效果','crafting materials':'製作材料','field equipment':'野外裝備','field notes':'野外筆記',
    'installed components':'已安裝元件','module output':'模組輸出','parameters':'參數','equipped':'已裝備',
    'candidate':'待比較','equipment comparison':'裝備比較','defense':'防禦','resistance':'抗性',
    'required attributes':'需求屬性','binds on pickup':'拾取後綁定','ruby socket':'紅寶石插槽',
    'sapphire socket':'藍寶石插槽','prismatic socket':'稜彩插槽','unit / elemental':'單位／元素',
    'spell / restoration':'法術／恢復'}
_PATTERN = re.compile(r'(?<![A-Za-z0-9_])(?:' + '|'.join(re.escape(s) for s in sorted(_TERMS, key=len, reverse=True))
                      + r')(?![A-Za-z0-9_])', re.IGNORECASE)


class EquipmentDictionary:
    def __init__(self, dictionary):
        self.dictionary = dictionary

    def __getattr__(self, name):
        return getattr(self.dictionary, name)

    def protect(self, text):
        protected, mapping = self.dictionary.protect(text)
        mapping = dict(mapping)
        occupied = set(mapping) | set(re.findall(r'\[GL\d+\]', protected))
        index = len(mapping)
        def replace(match):
            nonlocal index
            while f'[GL{index}]' in occupied:
                index += 1
            token = f'[GL{index}]'
            index += 1
            occupied.add(token)
            mapping[token] = _TERMS[match.group(0).casefold()]
            return token
        if protected.strip().casefold() in _LABELS:
            while f'[GL{index}]' in occupied:index+=1
            token=f'[GL{index}]'
            mapping[token]=_LABELS[protected.strip().casefold()]
            return token,mapping
        protected=_PATTERN.sub(replace, protected)
        if len(text.split())<=8 and not re.search(r'[.!?。！？]|\b(?:if|when|unless|gain|lose|deal|restore|use|equip|do not)\b',text,re.I):
            def name_part(match):
                nonlocal index
                while f'[GL{index}]' in occupied:index+=1
                token=f'[GL{index}]';index+=1;occupied.add(token)
                mapping[token]=_NAME_TERMS[match.group().casefold()];return token
            protected=_NAME_PATTERN.sub(name_part,protected)
        return protected,mapping
