"""Metadata import from public SoundCloud collections or local URL lists."""
import csv,io,json,re
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import requests

class ImportInputError(ValueError):pass

def soundcloud_path(value):
    parsed=urlparse(value.strip())
    if parsed.scheme!='https' or parsed.hostname not in ('soundcloud.com','www.soundcloud.com','m.soundcloud.com') or parsed.username or parsed.password or parsed.port not in (None,443):raise ImportInputError('Нужна полная ссылка https://soundcloud.com/…')
    parts=[p for p in parsed.path.split('/') if p]
    if not parts or parts[0] in ('you','search','discover','stream','signin','settings') or len(parts)>3:raise ImportInputError('Укажи ссылку на профиль, лайки, плейлист или трек SoundCloud.')
    if any(key not in ('si','in') and not key.startswith('utm_') for key in parse_qs(parsed.query)):raise ImportInputError('Закрытые ссылки с токеном не импортируются. Вставь публичную ссылку SoundCloud.')
    return '/'+('/'.join(parts))

def urls_from_text(text):
    value=text.strip()
    if re.fullmatch(r'@?[A-Za-z0-9_-]{2,100}',value):text='https://soundcloud.com/'+value.lstrip('@')
    found=re.findall(r'https://(?:www\.|m\.)?soundcloud\.com/[^\s<>"\x27,;\\]+',text)
    result=[];seen=set()
    for url in found:
        url=url.rstrip(').]}')
        try:path=soundcloud_path(url)
        except (ImportInputError,ValueError):continue
        canonical='https://soundcloud.com'+path
        if canonical not in seen:result.append(canonical);seen.add(canonical)
    return result

def urls_from_file(path):
    path=Path(path)
    if path.stat().st_size>25*1024*1024:raise ImportInputError('Файл слишком большой. Используй список ссылок до 25 МБ.')
    text=path.read_text(encoding='utf-8-sig')
    if path.suffix.casefold()=='.json':
        data=json.loads(text);text=json.dumps(data,ensure_ascii=False).replace('\\/','/')
    result=urls_from_text(text)
    if not result:raise ImportInputError('В файле нет полных ссылок SoundCloud. Поддерживаются CSV, JSON и TXT со ссылками на треки.')
    if len(result)>10000:raise ImportInputError('Раздели список на файлы до 10 000 ссылок.')
    return result

class SoundCloudImport:
    def __init__(self,provider):self.provider=provider

    def collect(self,urls,progress=lambda _:None,cancelled=lambda:False):
        result=[];seen=set();partial=False;skipped=0
        for index,url in enumerate(urls):
            if cancelled():break
            try:
                rows,incomplete=self.collection(url,cancelled)
                partial=partial or incomplete
                for row in rows:
                    if row['id'] not in seen:result.append(row);seen.add(row['id'])
            except Exception:skipped+=1
            progress(int((index+1)*100/len(urls)))
        return {'rows':result,'partial':partial,'skipped':skipped,'cancelled':cancelled()}

    def collection(self,url,cancelled):
        path=soundcloud_path(url);parts=path.strip('/').split('/')
        if len(parts)==1:path+='/likes'
        page,entities=self.provider.page(path)
        if len(parts)==1 or parts[-1]=='likes':
            collection=self.provider.records(entities,'likesCollections').get(page.get('userUrn'),{})
            refs=[item.get('track') for item in collection.get('collection',[]) if isinstance(item,dict) and item.get('track')]
            rows=self.provider.rows(entities,refs);next_url=collection.get('next_href');visited=set()
            while next_url and not cancelled():
                if next_url in visited or len(visited)>=1000:return rows,True
                visited.add(next_url);parsed=urlparse(next_url)
                if parsed.scheme!='https' or parsed.hostname not in ('api-mobi.soundcloud.com','api.soundcloud.com','api-v2.soundcloud.com') or parsed.username or parsed.password:return rows,True
                # Follow only the pagination advertised by the public page. An
                # authentication requirement ends the import; no token extraction.
                response=requests.get(next_url,timeout=(4,8),headers={'User-Agent':'Mozilla/5.0'},allow_redirects=False)
                if response.status_code!=200:return rows,True
                if len(response.content)>5*1024*1024:return rows,True
                data=response.json();tracks={};users={}
                for entry in data.get('collection',[]):
                    track=entry.get('track') if isinstance(entry,dict) else None
                    if isinstance(track,dict):tracks['soundcloud:tracks:'+str(track['id'])]=track
                rows+=self.provider.rows({'tracks':tracks,'users':users});next_url=data.get('next_href')
            return rows,False
        if page.get('trackUrn'):return self.provider.rows(entities,[page['trackUrn']]),False
        playlists=self.provider.records(entities,'playlists');playlist=playlists.get(page.get('playlistUrn')) or next(iter(playlists.values()),{})
        refs=[item if isinstance(item,str) else 'soundcloud:tracks:'+str(item.get('id','')) for item in playlist.get('tracks',[])]
        rows=self.provider.rows(entities,refs)
        return rows,bool(playlist.get('track_count',len(refs))>len(rows))
