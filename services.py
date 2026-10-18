import hashlib
import threading
import time
import random
from pathlib import Path
import requests


class SoundCloudUnavailable(Exception):pass
class TrackUnavailable(Exception):pass


class SilentLog:
    def debug(self,*args):pass
    def info(self,*args):pass
    def warning(self,*args):pass
    def error(self,*args):pass


class SoundCloud:
    """Read the public mobile catalogue; play through SoundCloud's official widget."""
    def __init__(self,folder):self.folder=folder;self.pages={};self.page_lock=threading.Lock()

    def page(self,path,params=None):
        import re,json
        from urllib.parse import urlparse
        if path.startswith('https://'):
            parsed=urlparse(path)
            if parsed.hostname not in ('soundcloud.com','m.soundcloud.com','www.soundcloud.com'):raise SoundCloudUnavailable()
            path=parsed.path
        if not path.startswith('/') or path.startswith('//'):raise SoundCloudUnavailable()
        cache_key=(path,tuple(sorted((params or {}).items())))
        with self.page_lock:cached=self.pages.get(cache_key)
        if cached and time.monotonic()-cached[0]<30:return cached[1]
        try:
            response=requests.get('https://m.soundcloud.com'+path,params=params,timeout=(4,7),headers={'User-Agent':'Mozilla/5.0'})
            response.raise_for_status()
            match=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',response.text,re.S)
            if not match:raise SoundCloudUnavailable()
            page=json.loads(match.group(1))['props']['pageProps'];entities=page.get('initialStoreState',{}).get('entities',{})
            result=(page,entities)
            with self.page_lock:self.pages[cache_key]=(time.monotonic(),result)
            return result
        except Exception as exc:raise SoundCloudUnavailable() from exc

    @staticmethod
    def records(entities,kind):
        return {urn:entry.get('data',entry) for urn,entry in entities.get(kind,{}).items() if isinstance(entry,dict) and isinstance(entry.get('data',entry),dict)}

    def rows(self,entities,urns=None):
        users=self.records(entities,'users');tracks=self.records(entities,'tracks');rows=[]
        for urn in (urns if urns is not None else tracks):
            track=tracks.get(urn,{})
            if not track.get('streamable') or track.get('policy') not in ('ALLOW','MONETIZE') or not track.get('public',True):continue
            if track.get('full_duration',0)>track.get('duration',0)+5000:continue
            choices=(track.get('media') or {}).get('transcodings',[])
            if choices and not any(not t.get('snipped') for t in choices):continue
            user=track.get('user') or {};user=users.get(user,{}) if isinstance(user,str) else user
            name=user.get('username','SoundCloud');url=track.get('permalink_url')
            if not url:continue
            author={'id':str(user.get('id','')),'name':name,'source':'soundcloud','url':user.get('permalink_url'),'cover':user.get('avatar_url')}
            rows.append({'id':'sc:'+str(track['id']),'remote_id':str(track['id']),'source':'soundcloud','title':track.get('title','Трек SoundCloud'),
                'artist':name,'duration':track.get('full_duration') or track.get('duration',0),'url':url,
                'artist_id':author['id'],'artist_url':author['url'],'artist_name':name,'artists':[author],
                'cover':track.get('artwork_url') or author['cover'],'genre':track.get('genre',''),
                'popularity':track.get('playback_count',0),'public_access':True})
        return rows

    def search(self,text):
        _,entities=self.page('/search',{'q':text});rows=self.rows(entities)
        artists={row['artist_url']:row['artists'][0] for row in rows if row.get('artist_url')}
        for artist in artists.values():artist['id']=artist['url']
        return rows,list(artists.values())[:6]

    def stream(self,row):
        from urllib.parse import urlencode
        page,entities=self.page(row['url']);urn=page.get('trackUrn');rows=self.rows(entities,[urn])
        if not rows:raise TrackUnavailable()
        return 'https://w.soundcloud.com/player/?'+urlencode({'url':rows[0]['url'],'auto_play':'false','visual':'false'})

    def artist(self,artist):
        _,entities=self.page(artist.get('url') or artist['id']);return self.rows(entities)

    def related(self,row):
        page,entities=self.page(row['url']);urn=page.get('trackUrn')
        collection=self.records(entities,'relatedTracksCollections').get(urn,{})
        rows=[r for r in self.rows(entities,collection.get('collection',[])) if r['id']!=row['id']]
        random.SystemRandom().shuffle(rows);previous=getattr(self,'previous_wave',set());rows.sort(key=lambda r:r['id'] in previous)
        return rows


class AudioCache:
    def __init__(self,folder):
        self.folder=Path(folder)/'audio-cache'
        self.lock=threading.Lock();self.locks={}

    def path(self,row):return self.folder/(hashlib.sha256(row['id'].encode()).hexdigest()+'.mp3')

    def invalidate(self,row):
        try:self.path(row).unlink(missing_ok=True)
        except OSError:pass

    def public(self,row,url,on_progress=None):
        """Use a local complete file for progressive public audio (MF ignores some proxy settings)."""
        from urllib.parse import urlparse
        parsed=urlparse(url)
        if parsed.scheme!='https' or parsed.username:raise TrackUnavailable()
        root=self.path(row)
        with self.lock:lock=self.locks.setdefault(row['id'],threading.Lock())
        with lock:
            for suffix in ('.mp3','.m4a','.ogg','.wav'):
                cached=root.with_suffix(suffix)
                if cached.exists() and cached.stat().st_size>1024:return str(cached)
            self.folder.mkdir(parents=True,exist_ok=True);started=time.monotonic()
            with requests.get(url,stream=True,timeout=(8,20)) as response:
                response.raise_for_status();mime=response.headers.get('Content-Type','').split(';')[0].lower()
                if 'mpegurl' in mime or urlparse(response.url).path.endswith('.m3u8'):return url
                suffix={ 'audio/mpeg':'.mp3','audio/mp3':'.mp3','audio/mp4':'.m4a','audio/x-m4a':'.m4a','audio/ogg':'.ogg','audio/wav':'.wav','audio/x-wav':'.wav'}.get(mime)
                if not suffix and mime not in ('application/octet-stream','binary/octet-stream',''):raise TrackUnavailable()
                target=root.with_suffix(suffix or '.mp3');part=target.with_suffix('.part');count=0;length=int(response.headers.get('Content-Length',0))
                try:
                    with part.open('wb') as output:
                        for chunk in response.iter_content(128*1024):
                            output.write(chunk);count+=len(chunk)
                            if count>100*1024*1024 or time.monotonic()-started>90:raise TrackUnavailable()
                            if on_progress and length:on_progress(min(99,int(count*100/length)))
                    if count<1024 or (length and count!=length):raise TrackUnavailable()
                    part.replace(target)
                except Exception:part.unlink(missing_ok=True);raise
                return str(target)

    def yandex(self,client,row,on_progress=None):
        target=self.path(row)
        with self.lock:lock=self.locks.setdefault(row['id'],threading.Lock())
        with lock:
            if target.exists() and target.stat().st_size>1024:return str(target)
            tracks=client.tracks([row['id']])
            if not tracks or not tracks[0].available:raise TrackUnavailable()
            choices=[c for c in tracks[0].get_download_info() if c.codec=='mp3' and not getattr(c,'preview',False)]
            choices.sort(key=lambda c:c.bitrate_in_kbps or 0,reverse=True)
            if not choices:raise TrackUnavailable()
            url=choices[0].get_direct_link()
            if url.startswith('file:'):return url
            self.folder.mkdir(parents=True,exist_ok=True)
            part=target.with_suffix('.part')
            try:
                with requests.get(url,stream=True,timeout=(8,20)) as response:
                    response.raise_for_status()
                    length=int(response.headers.get('Content-Length',0));count=0
                    with part.open('wb') as output:
                        for chunk in response.iter_content(128*1024):
                            output.write(chunk);count+=len(chunk)
                            if on_progress and length:on_progress(min(99,int(count*100/length)))
                            if count>100*1024*1024:raise TrackUnavailable()
                    if count<1024 or (length and length!=count):raise TrackUnavailable()
                part.replace(target)
            except Exception:
                part.unlink(missing_ok=True);raise
            return str(target)

    def trim(self,protected=()):
        if not self.folder.exists():return
        paths=sorted((p for p in self.folder.iterdir() if p.suffix in ('.mp3','.m4a','.ogg','.wav')),key=lambda p:p.stat().st_mtime,reverse=True)
        total=0
        for path in paths:
            total+=path.stat().st_size
            if total>240*1024*1024 and str(path) not in protected:
                try:path.unlink()
                except OSError:pass
