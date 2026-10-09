from dataclasses import dataclass
import re

_CODE_NAME = re.compile(r'(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+(?![A-Za-z0-9_])')


@dataclass(frozen=True)
class Entry:
    source: str
    target: str
    domain: str = 'shared'


class Dictionary:
    def __init__(self, entries=()):
        self.entries = sorted(entries,key=lambda e:len(e.source),reverse=True)

    def protect(self, text):
        mapping = {}
        occupied = set(re.findall(r'\[GL\d+\]',text))
        index = 0
        def token(target):
            nonlocal index
            while f'[GL{index}]' in occupied:
                index += 1
            name = f'[GL{index}]'
            index += 1
            occupied.add(name)
            mapping[name] = target
            return name
        for entry in self.entries:
            pattern = re.compile(r'(?<![A-Za-z0-9_])'+re.escape(entry.source)+r'(?![A-Za-z0-9_])',re.IGNORECASE)
            # Previously generated and literal tokens must never be matched by
            # a later user term such as GL0.
            pieces = re.split(r'(\[GL\d+\])',text)
            text = ''.join(piece if re.fullmatch(r'\[GL\d+\]',piece) else
                           pattern.sub(lambda m:token(entry.target),piece) for piece in pieces)
        text = _CODE_NAME.sub(lambda m:token(m.group(0)),text)
        return text,mapping


def restore_terms(text, mapping):
    for token in mapping:
        if text.count(token) != 1:
            raise ValueError('譯文未完整保留名稱或詞庫標記，已保留原文。')
    for token,target in mapping.items():
        text = text.replace(token,target)
    return text
