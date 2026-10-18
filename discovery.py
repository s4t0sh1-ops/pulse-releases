"""Bounded matching of public copies and source-independent radio seeds."""
import re,time,unicodedata,threading
from matching import compact,same_version
from concurrent.futures import ThreadPoolExecutor,wait

def key(text):
    return compact(text)

def similarity(seed,candidate):
    if not same_version(seed,candidate):return 0
    title=key(seed['title']);other=key(candidate['title'])
    artists=[key(a.get('name','')) for a in seed.get('artists',[]) if a.get('name')]
    artists=artists or [key(x) for x in re.split(r',| feat\.? | & ',seed['artist'],flags=re.I)]
    primary=artists[0] if artists else ''
    credited=key(candidate['artist'])+other
    # Uploaders need not be the artist. Require an artist credit in the title instead.
    if not primary or primary not in credited:return 0
    def title_core(value):
        # Credits and an uploader's artist prefix do not change the recording's title.
        value=re.sub(r'(?i)\b(?:ft|feat|featuring)\.?\s*',' ',value)
        value=re.sub(r'(?i)\b(?:official|audio|video|lyrics|hd|hq)\b',' ',value)
        normalized=key(value)
        for artist in sorted(artists,key=len,reverse=True):normalized=normalized.replace(artist,'')
        return normalized
    if title_core(seed['title'])!=title_core(candidate['title']):return 0
    if seed.get('duration') and candidate.get('duration') and abs(seed['duration']-candidate['duration'])>8000:return 0
    return 100+(20 if title==other else 0)+int(candidate.get('popularity',0)>0)

class PublicDiscovery:
    def __init__(self,providers):self.providers=providers;self.cache={};self.lock=threading.Lock()
    def candidates(self,seed):
        query=seed['artist']+' '+seed['title'];pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='public-search')
        jobs={pool.submit(provider.search,query):name for name,provider in self.providers.items()};rows=[]
        try:
            done,_=wait(jobs,timeout=13)
            for job in done:
                try:rows.extend(job.result()[0])
                except Exception:pass
        finally:pool.shutdown(wait=False,cancel_futures=True)
        return sorted(rows,key=lambda row:similarity(seed,row),reverse=True)
    def match(self,seed):
        identity=seed['id'];now=time.monotonic()
        with self.lock:cached=self.cache.get(identity)
        if cached and now-cached[0]<60:return cached[1]
        rows=self.candidates(seed);result=next((row for row in rows if similarity(seed,row)),None)
        with self.lock:self.cache[identity]=(time.monotonic(),result)
        return result
    def wave(self,seed):
        rows=self.candidates(seed)
        # Start with an actual matching recording, then that source's related catalogue.
        anchors=[r for r in rows if similarity(seed,r)]
        for anchor in anchors[:3]:
            try:
                related=self.providers[anchor['source']].related(anchor)
                if related:return related,{'source':anchor['source'],'seed':anchor,'original_seed':seed}
            except Exception:continue
        return [],None
