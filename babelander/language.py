"""Normalize ordinary output to Taiwan Traditional Chinese, preserve overrides."""
import re
import threading
from opencc import OpenCC

class ChineseOutput:
    def __init__(self):
        self.converter=OpenCC('s2twp')
        self.lock=threading.Lock()
    def convert(self,text,preserve=()):
        with self.lock:
            words=sorted(set(word for word in preserve if word),key=len,reverse=True)
            if not words:return self.converter.convert(text)
            pattern=re.compile('('+'|'.join(re.escape(word) for word in words)+')')
            reserved=set(words)
            return ''.join(piece if piece in reserved else self.converter.convert(piece) for piece in pattern.split(text))
