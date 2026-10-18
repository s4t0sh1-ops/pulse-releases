"""Timed lyrics without invented word timings. Network work runs off the UI thread."""
import hashlib,json,re,time,threading,unicodedata
from pathlib import Path
import requests

def stamp(minutes,seconds):return round((int(minutes)*60+float(seconds))*1000)

def parse_lrc(text):
    rows=[];offset=0
    match=re.search(r'\[offset:([+-]?\d+)\]',text or '',re.I)
    if match:offset=int(match[1])
    for line in (text or '').splitlines():
        tags=list(re.finditer(r'\[(\d+):(\d+(?:\.\d+)?)\]',line))
        if not tags:continue
        content=line[tags[-1].end():].strip();words=[]
        parts=list(re.finditer(r'<(\d+):(\d+(?:\.\d+)?)>([^<]*)',content))
        if parts:
            words=[{'time':max(0,stamp(m[1],m[2])+offset),'text':m[3]} for m in parts if m[3]]
            content=''.join(w['text'] for w in words)
        for tag in tags:rows.append({'time':max(0,stamp(tag[1],tag[2])+offset),'text':content,'words':words})
    return sorted(rows,key=lambda r:r['time'])

def parse_lyricsfile(text):
    if not text or len(text)>512000:return []
    import yaml
    # The draft excludes aliases, custom tags and duplicate mapping keys.
    if any(isinstance(t,(yaml.tokens.AliasToken,yaml.tokens.AnchorToken,yaml.tokens.TagToken)) for t in yaml.scan(text)):return []
    class UniqueLoader(yaml.SafeLoader):pass
    def mapping(loader,node,deep=False):
        result={}
        for key,value in node.value:
            k=loader.construct_object(key,deep=deep)
            if k in result:raise ValueError('duplicate key')
            result[k]=loader.construct_object(value,deep=deep)
        return result
    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)
    obj=yaml.load(text,Loader=UniqueLoader)
    if not isinstance(obj,dict) or str(obj.get('version'))!='1.0':return []
    rows=[]
    for row in (obj.get('lines') or [])[:1500]:
        if not isinstance(row,dict) or not isinstance(row.get('start_ms'),int):continue
        words=[{'time':max(0,w['start_ms']),'end':w.get('end_ms'),'text':str(w.get('text',''))} for w in row.get('words',[]) if isinstance(w,dict) and isinstance(w.get('start_ms'),int)]
        rows.append({'time':max(0,row['start_ms']),'end':row.get('end_ms'),'text':str(row.get('text','')),'words':sorted(words,key=lambda w:w['time'])})
    return sorted(rows,key=lambda r:r['time'])

class LyricsService:
    def __init__(self,folder):
        self.folder=Path(folder)/'lyrics-cache';self.lock=threading.Lock();self.next_request=0.
    def fetch(self,row,client=None):
        key=hashlib.sha256((row.get('source','')+row['id']).encode()).hexdigest()
        path=self.folder/(key+'.json')
        try:
            if time.time()-path.stat().st_mtime<86400*14:return json.loads(path.read_text(encoding='utf8'))
        except (OSError,ValueError):pass
        result=None;line_fallback=None
        if row.get('source')=='local':
            base=Path(row['path'])
            for suffix in ('.lyricsfile.yaml','.lrc','.txt'):
                candidate=base.with_suffix(suffix)
                if candidate.exists() and candidate.stat().st_size<512000:
                    text=candidate.read_text(encoding='utf-8-sig');lines=parse_lyricsfile(text) if suffix.endswith('yaml') else parse_lrc(text)
                    result={'lines':lines,'plain':text if not lines else '', 'source':'Файл рядом с треком'};break
        if not result and client and row.get('source','yandex')=='yandex':
            for fmt in ('LRC','TEXT'):
                try:
                    metadata=client.tracks_lyrics(row['id'],format_=fmt,timeout=6)
                    if metadata:
                        text=metadata.fetch_lyrics();lines=parse_lrc(text)
                        if text:line_fallback={'lines':lines,'plain':text if not lines else '', 'source':'Яндекс Музыка'};break
                except Exception:pass
        # LRCLIB may contain real word timings even when the platform only has LRC.
        if not result:
            try:
                with self.lock:
                    delay=self.next_request-time.monotonic()
                    if delay>.5:raise requests.RequestException('cooldown')
                    if delay>0:time.sleep(delay)
                    response=requests.get('https://lrclib.net/api/get',params={'track_name':row['title'],'artist_name':row['artist'],'duration':max(1,round(row.get('duration',0)/1000))},
                        headers={'User-Agent':'Pulse/0.7 (local Windows music player; https://lrclib.net)'},timeout=(4,6))
                    self.next_request=time.monotonic()+.3
                    if response.status_code in (429,503):
                        try:self.next_request=time.monotonic()+min(3600,max(1,float(response.headers.get('Retry-After',30))))
                        except ValueError:self.next_request=time.monotonic()+30
                    if response.ok and len(response.content)<1000000:
                        data=response.json();lines=[]
                        try:lines=parse_lyricsfile(data.get('lyricsfile'))
                        except Exception:pass
                        if not lines:lines=parse_lrc(data.get('syncedLyrics'))
                        if lines or data.get('plainLyrics') or data.get('instrumental'):
                            result={'lines':lines,'plain':data.get('plainLyrics') if not lines else '', 'source':'LRCLIB','instrumental':bool(data.get('instrumental'))}
            except (requests.RequestException,ValueError,TypeError):pass
        if line_fallback and line_fallback.get('lines') and result and not result.get('lines'):result=line_fallback
        result=result or line_fallback or {'lines':[],'plain':'','source':'','missing':True}
        if not result.get('missing'):
            self.folder.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')
        return result
