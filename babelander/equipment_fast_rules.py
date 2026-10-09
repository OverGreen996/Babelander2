"""Whole-sentence rules for unambiguous timed stat bonuses; never split clauses."""
from collections import Counter
import re

_STATS = {
    'attack power': '攻擊力', 'attack speed': '攻擊速度',
    'critical rate': '暴擊率', 'critical chance': '暴擊率',
    'critical damage': '暴擊傷害', 'maximum health': '最大生命值',
    'physical damage': '物理傷害', 'magic damage': '魔法傷害',
    'defense': '防禦力', 'damage': '傷害', 'armor': '護甲',
    'movement speed': '移動速度', 'fire resistance': '火焰抗性',
    'cold resistance': '冰冷抗性', 'lightning resistance': '閃電抗性',
    'strength':'力量','vitality':'體能','agility':'敏捷','dexterity':'敏捷','damage to elites':'對精英傷害',
    'attack':'攻擊力','health':'生命值','magic':'魔法','physical':'物理','fire':'火焰','lightning':'閃電',
    'poison':'毒素','bleed':'出血','frost':'冰霜','cold damage':'冰冷傷害',
    'attack damage':'攻擊傷害','magic power':'法術強度','maximum mana':'最大魔力值',
    'magazine':'彈匣容量','accuracy':'準確度','fire rate':'射速','weapon score':'武器評分',
    'power':'功率','heat':'熱量','load':'負載','capacity':'容量','recovery':'恢復速度','delay':'延遲',
}
_STAT_PATTERN = '|'.join(re.escape(s) for s in sorted(_STATS, key=len, reverse=True))
_FIELD_LABELS={**_STATS,'durability':'耐久度','item level':'物品等級','required level':'需求等級',
               'level requirement':'需求等級','damage per second':'每秒傷害','sell price':'售價',
               'level':'等級','gem level':'寶石等級','quality':'品質','total cost':'總價','condition':'狀況','value':'價值'}
NUMBER=r'[+\-−]?\s*\d+(?:,\d{3})*(?:\.\d+)?%?(?:\s*/\s*\d+(?:,\d{3})*(?:\.\d+)?%?)?'
LITERAL_NUMBER=re.compile(NUMBER)
AFFIX_FIELD=re.compile(r'(?P<value>[+\-−]\s*\d+(?:,\d{3})*(?:\.\d+)?%?)\s+(?P<label>[A-Za-z][A-Za-z ]{0,40})')
SPACED_FIELD=re.compile(r'(?P<label>[A-Za-z][A-Za-z ]{0,40})\s+(?P<value>'+NUMBER+')')
ATOMIC_UI=re.compile(r'^(?:item level|required level|level requirement|classes|sell price|durability|gem level|quality|condition|value|weight)\b|^(?:weapon|armor|jewelry)\s*:|^(?:(?:empty|ruby|sapphire|prismatic) socket|binds on pickup|gem sockets|crafting materials|field notes|field equipment|passive|active|equipped|candidate|installed components|module output|gem properties|socket effects|unit / elemental|spell / restoration)$',re.I)
NUMERIC_FIELD=re.compile(r'(?P<label>[A-Za-z][A-Za-z ]{0,40})\s*:\s*'
    r'(?P<value>[+\-−]?\d+(?:,\d{3})*(?:\.\d+)?%?(?:\s*/\s*\d+(?:,\d{3})*(?:\.\d+)?%?)?)')


def numeric_field(text,dictionary):
    """Complete known label/value rows only; preserve explicit glossary terms."""
    value_first=False;colon=True
    match=NUMERIC_FIELD.fullmatch(text.strip().replace('：',':'))
    if match is None:
        match=AFFIX_FIELD.fullmatch(text.strip());value_first=match is not None;colon=False
    if match is None:match=SPACED_FIELD.fullmatch(text.strip())
    if match is None:return None
    label=match['label'].strip()
    if label.casefold() not in _FIELD_LABELS:return None
    protected,mapping=dictionary.protect(label)
    if mapping and protected not in mapping:return None
    if Counter(dictionary.protect(text)[1].values())!=Counter(mapping.values()):return None
    target=mapping[protected] if protected in mapping else _FIELD_LABELS[label.casefold()]
    if value_first:return re.sub(r'\s+','',match['value'])+' '+target
    return target+('：' if colon else ' ')+match['value']


_SLOTS={'weapon':'武器','armor':'防具','jewelry':'飾品'}
_SLOT_STAT=re.compile(r'(?P<slot>weapon|armor|jewelry)\s*[:：]\s*(?P<value>'+NUMBER+r')\s+(?P<stat>[A-Za-z ]+)',re.I)
_COLORS={'blue':'藍色','white':'白色','red':'紅色','green':'綠色','purple':'紫色','yellow':'黃色'}
_FITS=re.compile(r'Fits\s*[:：]\s*(?P<a>blue|white|red|green|purple|yellow)(?:\s+(?P<link>or|and)\s+(?P<b>blue|white|red|green|purple|yellow))?\s+sockets?\.?',re.I)


def slot_field(text,dictionary):
    """Whole socket fields only; never interpret an unknown or conditional bonus."""
    match=_FITS.fullmatch(text.strip())
    if match:
        if dictionary.protect(text)[1]:return None
        target=_COLORS[match['a'].casefold()]
        if match['b']:target+=('或' if match['link'].casefold()=='or' else '及')+_COLORS[match['b'].casefold()]
        return '適用插槽：'+target
    match=_SLOT_STAT.fullmatch(text.strip())
    if match is None or match['stat'].strip().casefold() not in _STATS:return None
    chosen=[];all_mapping=[]
    for field,vocabulary in ((match['slot'],_SLOTS),(match['stat'].strip(),_STATS)):
        protected,mapping=dictionary.protect(field)
        if mapping and protected not in mapping:return None
        chosen.append(mapping[protected] if protected in mapping else vocabulary[field.casefold()])
        all_mapping+=list(mapping.values())
    if Counter(dictionary.protect(text)[1].values())!=Counter(all_mapping):return None
    return chosen[0]+'：'+match['value']+' '+chosen[1]


_LEVEL_RESTRICTION=re.compile(r"(?:do not|don't|don’t) equip this item before level (?P<level>\d+)\.?",re.I)


def level_restriction(text,dictionary):
    """Exact grammar only: preserve both prohibition and the level threshold."""
    match=_LEVEL_RESTRICTION.fullmatch(text.strip())
    if not match or dictionary.protect(text)[1]:return None
    return f'未達等級 {match["level"]} 前，請勿裝備此物品。'
_TIMED_BONUS = re.compile(
    rf'Gain\s+(?P<amount>[+\-−]?\d+(?:\.\d+)?%?)\s+'
    rf'(?P<stat>{_STAT_PATTERN})\s+for\s+(?P<duration>\d+(?:\.\d+)?)\s+seconds?\.?',
    re.IGNORECASE,
)


def timed_bonus(text, dictionary):
    match = _TIMED_BONUS.fullmatch(text.strip())
    if not match:
        return None
    stat = match['stat']
    protected, mapping = dictionary.protect(stat)
    # Honor only a complete explicit stat override. Partial terms and glossary
    # overrides elsewhere in the sentence belong to the existing model path.
    if mapping and protected not in mapping:
        return None
    if Counter(dictionary.protect(text)[1].values()) != Counter(mapping.values()):
        return None
    translated = mapping[protected] if protected in mapping else _STATS[stat.casefold()]
    return f'獲得 {match["amount"]} {translated}，持續 {match["duration"]} 秒。'
