"""Strict whole-sentence grammars for locations, follow conditions and stat branches."""
from collections import Counter
import re
from .equipment_fast_rules import _STATS, _STAT_PATTERN

_NAME = r'[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+'
_NUMBER = r'[+\-−]?\d+(?:\.\d+)?'
_MEET = re.compile(rf'Meet (?P<name>{_NAME})(?: near (?P<place>{_NAME}))? '
                   rf'at X:(?P<x>{_NUMBER}) Y:(?P<y>{_NUMBER})\.?', re.IGNORECASE)
_FOLLOW = re.compile(rf'Do not follow (?P<name>{_NAME}) unless (?P<requester>{_NAME}) asks for help\.?',
                     re.IGNORECASE)
_WAIT_ENTRY = re.compile(r'Do not (?P<action>enter|leave|cross|open|close|start) (?:the )?(?P<place>dungeon|room|area|river|bridge|gate|door|chest|raid|battle|fight) yet\.?',re.I)
_BRANCH = re.compile(
    rf'If health is (?P<comparison>below|above) (?P<threshold>\d+(?:\.\d+)?%), '
    rf'gain (?P<amount>{_NUMBER}%?) (?P<stat>{_STAT_PATTERN}) '
    rf'for (?P<duration>\d+(?:\.\d+)?) seconds?\. Otherwise, '
    rf'gain (?P<otherwise_amount>{_NUMBER}%?) (?P<otherwise_stat>{_STAT_PATTERN})\.?',
    re.IGNORECASE,
)


def _atoms(text, atoms, dictionary):
    """Honor whole glossary overrides; partial or unrelated overrides defer."""
    targets, allowed = {}, Counter()
    for key, (source, default) in atoms.items():
        protected, mapping = dictionary.protect(source)
        if mapping and protected not in mapping:
            return None
        allowed.update(mapping.values())
        targets[key] = mapping.get(protected, default)
    if Counter(dictionary.protect(text)[1].values()) != allowed:
        return None
    return targets


def dialog_rule(text, dictionary):
    match = _WAIT_ENTRY.fullmatch(text.strip())
    if match:
        verb,noun=match['action'].casefold(),match['place'].casefold()
        supported={'enter':('dungeon','room','area'),'leave':('dungeon','room','area'),
                   'cross':('river','bridge'),'open':('gate','door','chest'),'close':('gate','door'),
                   'start':('raid','battle','fight')}
        if noun not in supported[verb]:return None
        action={'enter':'進入','leave':'離開','cross':'越過','open':'打開','close':'關閉','start':'開始'}[verb]
        place={'dungeon':'地牢','room':'房間','area':'區域','river':'河流','bridge':'橋樑',
               'gate':'大門','door':'門','chest':'寶箱','raid':'團隊副本','battle':'戰鬥','fight':'戰鬥'}[noun]
        targets=_atoms(text,{'action':(match['action'],action),'place':(match['place'],place)},dictionary)
        if targets is not None:return f'暫時不要{targets["action"]}{targets["place"]}。'
    match = _MEET.fullmatch(text.strip())
    if match:
        atoms = {'name': (match['name'], match['name'])}
        if match['place']:
            atoms['place'] = (match['place'], match['place'])
        targets = _atoms(text, atoms, dictionary)
        if targets is None:
            return None
        near = f'（{targets["place"]} 附近）' if match['place'] else ' '
        return f'請在 X:{match["x"]} Y:{match["y"]}{near}與 {targets["name"]} 會合。'
    match = _FOLLOW.fullmatch(text.strip())
    if match and match['name'] == match['requester']:
        targets = _atoms(text, {'name': (match['name'], match['name']),
                               'requester': (match['requester'], match['requester'])}, dictionary)
        if targets is not None:
            return f'不要跟隨 {targets["name"]}，除非 {targets["requester"]} 請求協助。'
    return None


def conditional_bonus(text, dictionary):
    match = _BRANCH.fullmatch(text.strip())
    if not match:
        return None
    targets = _atoms(text, {key: (match[key], _STATS[match[key].casefold()])
                            for key in ('stat', 'otherwise_stat')}, dictionary)
    if targets is None:
        return None
    comparison = '低於' if match['comparison'].casefold() == 'below' else '高於'
    return (f'若生命值{comparison} {match["threshold"]}，獲得 {match["amount"]} {targets["stat"]}，'
            f'持續 {match["duration"]} 秒；否則獲得 {match["otherwise_amount"]} {targets["otherwise_stat"]}。')
