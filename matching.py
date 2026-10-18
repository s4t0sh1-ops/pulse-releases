"""Deterministic catalogue ranking; recording identity is stricter than search."""
import re, unicodedata
from difflib import SequenceMatcher

_RU='абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
_LAT=('a','b','v','g','d','e','e','zh','z','i','y','k','l','m','n','o','p','r','s','t','u','f','h','ts','ch','sh','sch','','y','','e','yu','ya')
_TRANS=dict(zip(_RU,_LAT))
_KEYS=dict(zip('qwertyuiop[]asdfghjkl;\'zxcvbnm,.','йцукенгшщзхъфывапролджэячсмитьбю'))
_VERSIONS={'remix':r'\bremix\b|ремикс','slowed':r'\bslow(?:ed)?\b|замедлен',
           'sped':r'\bsped\b|\bspeed\s*up\b|ускорен','live':r'\blive\b|концерт',
           'instrumental':r'\binstrumental\b|инструментал|\bkaraoke\b',
           'cover':r'\bcover\b|кавер','acoustic':r'\bacoustic\b|акустик'}

def normalize(value):
    value=unicodedata.normalize('NFKD',str(value or '')).casefold().replace('ё','е')
    value=''.join(_TRANS.get(c,c) for c in value if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+',value))

def compact(value):return normalize(value).replace(' ','')

def variants(query):
    """At most one additional request, only for a clearly wrong keyboard layout."""
    query=query.strip();result=[query]
    if re.search(r'[a-z]',query,re.I) and not re.search(r'[а-я]',query,re.I):
        fixed=''.join(_KEYS.get(c,c) for c in query.casefold())
        # English artist names must not trigger a second unrelated search.
        if re.search(r'[\[\];\']',query) or (len(query)>4 and not re.search(r'[aeiouy]',query,re.I)):
            result.append(fixed)
    return result

def text_score(query,text):
    q=normalize(query);t=normalize(text)
    if not q or not t:return 0.
    if q==t:return 100.
    if q.replace(' ','')==t.replace(' ',''):return 98.
    qt=q.split();tt=t.split()
    if set(qt)<=set(tt):return 86.+10*len(qt)/len(tt)
    if t.startswith(q+' '):return 88.
    if len(q)>=4 and q in t:return 73.
    ratio=SequenceMatcher(None,q,t).ratio()
    # Short names require exact matches; fuzziness otherwise has a firm floor.
    return 68*ratio if len(q)>=5 and ratio>=.76 else 0.

def search_score(query,row):
    artist=row.get('artist','');title=row.get('title','')
    score=max(text_score(query,artist),text_score(query,title),
              .97*text_score(query,artist+' '+title),.97*text_score(query,title+' '+artist))
    for alias in variants(query)[1:]:score=max(score,.94*max(text_score(alias,artist),text_score(alias,title),text_score(alias,artist+' '+title)))
    return round(score,4)

def version_tags(row):
    text=str(row.get('title','')).casefold()
    return frozenset(k for k,p in _VERSIONS.items() if re.search(p,text))

def recording_key(row):
    title=re.sub(r'(?i)\b(?:official|audio|video|lyrics|hd|hq)\b',' ',row.get('title',''))
    return compact(row.get('artist',''))+'|'+compact(title)+'|'+'-'.join(sorted(version_tags(row)))

def same_version(a,b):
    return version_tags(a)==version_tags(b)
