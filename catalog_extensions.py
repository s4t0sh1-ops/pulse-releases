"""Album metadata and local taste ranking. Never invent albums from track artwork."""
from collections import Counter
import random
import requests
from matching import compact

def rank_for_you(rows,favorites,history):
    artists=Counter();genres=Counter();heard={r['id'] for r in history}
    for weight,items in ((1,history),(5,favorites)):
        for r in items:
            artists[compact(r.get('artist',''))]+=weight
            if r.get('genre'):genres[compact(r['genre'])]+=weight
    rows=list({r['id']:r for r in rows}.values());random.SystemRandom().shuffle(rows)
    rows.sort(key=lambda r:artists[compact(r.get('artist',''))]*3+genres[compact(r.get('genre',''))]-(7 if r['id'] in heard else 0),reverse=True)
    return rows

def get_yandex(path):
    r=requests.get('https://api.music.yandex.net'+path,timeout=(5,10));r.raise_for_status();return r.json()['result']

def albums(player,artist):
    source=artist.get('source','yandex');all={}
    if source=='soundcloud':
        _,entities=player.soundcloud.page((artist.get('url') or artist['id']).rstrip('/')+'/albums')
        for r in player.soundcloud.records(entities,'playlists').values():
            if not (r.get('is_album') or r.get('playlist_type')=='album'):continue
            a={'id':str(r['id']),'title':r.get('title','Альбом'),'cover':r.get('artwork_url'),'url':r.get('permalink_url'),'year':str(r.get('release_year') or ''),'source':source};all[a['id']]=a
    elif source=='audius':
        offset=0
        while True:
            rows=player.audius.get('/users/'+str(artist['id'])+'/albums',limit=100,offset=offset);before=len(all)
            for r in rows:
                a={'id':str(r['id']),'title':r.get('playlist_name','Альбом'),'cover':(r.get('artwork') or {}).get('480x480'),'year':str(r.get('release_date') or '')[:4],'source':source};all[a['id']]=a
            if len(rows)<100 or len(all)==before:break
            offset+=len(rows)
    else:
        page=0
        while True:
            result=get_yandex('/artists/'+str(artist['id'])+'/direct-albums?page='+str(page)+'&page-size=100&sort-by=year');rows=result.get('albums',[]);before=len(all)
            for r in rows:
                cover=r.get('coverUri','');a={'id':str(r['id']),'title':r.get('title','Альбом'),'cover':'https://'+cover.replace('%%','400x400') if cover else None,'year':str(r.get('year') or ''),'source':'yandex'};all[a['id']]=a
            total=(result.get('pager') or {}).get('total',0)
            if len(rows)<100 or len(all)==before or (total and len(all)>=total):break
            page+=1
    return list(all.values())

def album_tracks(player,album):
    source=album['source']
    if source=='soundcloud':
        _,entities=player.soundcloud.page(album['url']);return player.soundcloud.rows(entities)
    if source=='audius':return player.audius.rows(player.audius.get('/playlists/'+album['id']+'/tracks'))
    from yandex_music import Track
    result=get_yandex('/albums/'+album['id']+'/with-tracks')
    return [player.track_data(Track.de_json(r,player.client or player.catalog)) for volume in result.get('volumes',[]) for r in volume]
