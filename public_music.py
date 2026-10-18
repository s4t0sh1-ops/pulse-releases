"""Public Audius catalog; gated tracks are never exposed as playable."""
import requests
import random
from services import TrackUnavailable

class Audius:
    base='https://api.audius.co/v1'
    def get(self,path,**params):
        response=requests.get(self.base+path,params=dict(params,app_name='Pulse'),timeout=(4,7))
        response.raise_for_status();return response.json().get('data',[])
    @staticmethod
    def row(track):
        user=track.get('user') or {};art=track.get('artwork') or {}
        return {'id':'audius:'+str(track['id']),'remote_id':str(track['id']),'source':'audius','title':track.get('title','Без названия'),
            'artist':user.get('name') or user.get('handle','Audius'),'duration':int(track.get('duration',0)*1000),
            'genre':track.get('genre',''),'cover':art.get('480x480') or art.get('150x150'),'artist_id':user.get('id'),
            'artists':[{'id':user.get('id'),'name':user.get('name','Audius'),'source':'audius','cover':(user.get('profile_picture') or {}).get('150x150')}],
            'popularity':track.get('play_count',0),'public_access':True}
    def rows(self,rows):
        return [self.row(t) for t in rows if t.get('is_streamable') and (t.get('access') or {}).get('stream',True) and not t.get('stream_conditions') and not t.get('is_delete')]
    def search(self,query):
        rows=self.rows(self.get('/tracks/search',query=query,limit=40))
        artists={str(a['id']):a for r in rows for a in r['artists']};return rows,list(artists.values())[:6]
    def trending(self,genre=None,limit=50):return self.rows(self.get('/tracks/trending',limit=limit,**({'genre':genre} if genre else {})))
    def related(self,row):
        rows=self.trending(row.get('genre') or None,100)
        if not rows:rows=self.trending(limit=100)
        rows=[r for r in rows if r['id']!=row['id']]
        random.SystemRandom().shuffle(rows);previous=getattr(self,'previous_wave',set())
        rows.sort(key=lambda r:r['id'] in previous);return rows
    def artist(self,artist):
        rows=[];seen=set();offset=0
        while True:
            data=self.get('/users/'+str(artist['id'])+'/tracks',limit=100,offset=offset)
            batch=self.rows(data);fresh=[r for r in batch if r['id'] not in seen]
            rows+=fresh;seen.update(r['id'] for r in fresh);offset+=len(data)
            if len(data)<100 or (batch and not fresh):return rows
    def stream(self,row):
        # Recheck the current stream permission; access can change after search.
        track=self.get('/tracks/'+row['remote_id'])
        if not isinstance(track,dict) or not self.rows([track]):raise TrackUnavailable()
        return self.base+'/tracks/'+row['remote_id']+'/stream?app_name=Pulse'
