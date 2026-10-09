from collections import Counter
import re
import unicodedata

from .glossary import _CODE_NAME

NUMBER = re.compile(r'(?<![A-Za-z0-9_])(?:[+\-−]\s*)?\d+(?:\.\d+)?%?(?![A-Za-z0-9_])')
TIME = re.compile(r'(?<![A-Za-z0-9_:])\d{1,3}:\d{2}(?::\d{2})?(?![A-Za-z0-9_:])')
PROGRESS = re.compile(r'(?<![A-Za-z0-9_/])\d+\s*/\s*\d+(?![A-Za-z0-9_/])')
COORDINATE = re.compile(r'\b([XY])\s*:\s*([+\-−]?\d+(?:\.\d+)?)',re.IGNORECASE)


def normalize_time_quantities(text):
    # Only quantities directly attached to time units are normalized. Names,
    # identifiers and idioms containing Chinese number characters are untouched.
    digits = {'零':0,'〇':0,'一':1,'二':2,'兩':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    units = {'十':10,'百':100,'千':1000}
    def chinese(match):
        value = match[0]
        if not any(c in units for c in value):
            return ''.join(str(digits[c]) for c in value)
        total,current = 0,0
        for character in value:
            if character in digits:
                current = digits[character]
            else:
                total += (current or 1)*units[character]
                current = 0
        return str(total+current)
    text = re.sub(r'[零〇一二兩三四五六七八九十百千]+(?=\s*(?:分鐘|秒鐘|秒|小時|天))',chinese,text)
    english = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
    return re.sub(r'\b(?:one|two|three|four|five|six|seven|eight|nine|ten)(?=\s+(?:minutes?|seconds?|hours?|days?)\b)',lambda m:str(english[m[0].lower()]),text,flags=re.I)


def validate(source, target, reply=False, chat=False):
    if not target.strip():
        raise ValueError('翻譯服務回傳空白內容。')
    source_normal = normalize_time_quantities(unicodedata.normalize('NFKC',_CODE_NAME.sub('',source)))
    target_normal = normalize_time_quantities(unicodedata.normalize('NFKC',_CODE_NAME.sub('',target)))
    if chat:
        # Chat quantities x4 / 4x must be compared against translated 4 too.
        # Alphanumeric model numbers and underscore identifiers stay untouched.
        def quantity(text):
            text=re.sub(r'(?<![A-Za-z0-9_])[xX×]\s*(\d+)(?![A-Za-z0-9_])',r' \1 ',text)
            return re.sub(r'(?<![A-Za-z0-9_])(\d+)\s*[xX×](?![A-Za-z0-9_])',r' \1 ',text)
        source_normal,target_normal=quantity(source_normal),quantity(target_normal)
    for pattern, message in ((NUMBER,'數值或正負號改變'),(TIME,'時間格式改變'),(PROGRESS,'進度配對改變')):
        normalize = lambda value: re.sub(r'\s+','',value).replace('−','-')
        if Counter(normalize(v) for v in pattern.findall(source_normal)) != Counter(normalize(v) for v in pattern.findall(target_normal)):
            raise ValueError(message+'，已保留原文。')
    if Counter((a.upper(),b) for a,b in COORDINATE.findall(source_normal)) != Counter((a.upper(),b) for a,b in COORDINATE.findall(target_normal)):
        raise ValueError('座標軸或數值改變，已保留原文。')
    duration = re.compile(r'(?<![A-Za-z0-9_])([+\-−]?\d+(?:\.\d+)?)\s*(minutes?\b|mins?\b|seconds?\b|secs?\b|hours?\b|hrs?\b|分鐘|秒鐘|秒|小時)',re.I)
    def durations(text):
        def unit(value):
            value = value.lower()
            return 'minute' if value.startswith('min') or value=='分鐘' else 'hour' if value.startswith(('hour','hr')) or value=='小時' else 'second'
        return Counter((number.replace('−','-'),unit(value)) for number,value in duration.findall(text))
    if durations(source_normal) != durations(target_normal):
        raise ValueError('時間單位改變，已保留原文。')
    # Conservative guard against common dropped negation. This is deliberately
    # not advertised as a general semantic or translation-quality proof.
    english_negative = re.compile(r"\b(?:do\s+not|does\s+not|did\s+not|don['’]t|doesn['’]t|didn['’]t|never|must\s+not)\b",re.I)
    chinese_negative = re.compile(r'不(?:要|可|能|會|得|應)|禁止|請勿|切勿|別|從不|絕不')
    if reply and chinese_negative.search(source) and not english_negative.search(target):
        # Ordinary English 'not' covers 'will not', 'cannot' and contractions.
        if not re.search(r"\b(?:not|cannot|can['’]t|won['’]t|shouldn['’]t)\b",target,re.I):
            # "Wait N minutes before starting" preserves the specific
            # "wait ... 不要開始" restriction without a literal don't.
            # This does not excuse arbitrary omitted prohibitions or actions.
            deferred_start=(len(chinese_negative.findall(source))==1 and
                re.search(r'等|等待|稍候|稍等',source) and
                re.search(r'(?:不要|請勿|別)開始[，。！？!?,.\s]*$',source) and
                re.search(r'\bwait\b[^.!?;]{0,100}\bbefore\s+(?:starting|(?:you|we)\s+start)\b',target,re.I))
            if not deferred_start:raise ValueError('英文回覆可能遺漏否定，已保留原文。')
    if not reply and english_negative.search(source) and not re.search(r'不|勿|別|禁止|無須|毋須',target):
        # Perfect-tense experience (have/has/had never) can naturally be
        # 尚未/未曾/從未/沒有...過. Never/Do not commands must retain the
        # original prohibition check; arbitrary 未 in 未來 is not negation.
        negatives=list(english_negative.finditer(source))
        experiences=list(re.finditer(r'\b(?:have|has|had)\s+never\b',source,re.I))
        experience_only=bool(experiences) and all(m.group().lower()=='never' for m in negatives) and len(experiences)==len(negatives)
        experience_target=re.search(r'尚未|未曾|從未|從來沒|沒(?:有)?[^，。！？;\n]{1,40}過',target)
        if not (experience_only and experience_target):
            raise ValueError('譯文可能遺漏否定，已保留原文。')
    tokens = lambda text: Counter(re.findall(r'\[GL\d+\]',text))
    if tokens(source) != tokens(target):
        raise ValueError('譯文含未還原的詞庫標記。')
    if not reply and re.search(r'[A-Za-z]{2,}',source_normal) and not re.search(r'[\u3400-\u9fff]',target):
        from .chat import only_shorthand
        # Numeric, negation and term checks above still apply. An arbitrary
        # echoed English sentence cannot bypass this check in chat mode.
        if not (chat and only_shorthand(source_normal) and only_shorthand(target_normal)
                and source_normal.strip().casefold()==target_normal.strip().casefold()):
            raise ValueError('沒有產生中文譯文，已保留原文。')
    if reply and re.search(r'[\u3400-\u9fff]',source) and not re.search(r'[A-Za-z]{2,}',target):
        raise ValueError('沒有產生英文回覆，已保留原文。')
