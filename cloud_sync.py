"""Authenticated favourite sync. Local outbox and server cursor survive restarts."""
import base64, ctypes, hashlib, json, time, uuid
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from pathlib import Path
import requests
from urllib.parse import urlsplit
from PySide6.QtCore import QTimer

BASE='https://pulse-help.ddemonovic65.workers.dev'

def seal(raw, decrypt=False):
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buf=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    fn=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ctypes.WinError()
    try:return ctypes.string_at(target.data,target.size)
    finally:ctypes.windll.kernel32.LocalFree(target.data)

def save_session(folder, account, token):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    path=folder/('cloud-'+hashlib.sha256(str(account).encode()).hexdigest()+'.bin')
    tmp=path.with_suffix('.tmp');tmp.write_bytes(seal(token.encode()));tmp.replace(path)

def shareable(row):return row.get('source','yandex') in ('yandex','soundcloud','audius') and str(row.get('id',''))

class SyncState:
    def __init__(self,state=None):
        self.data=state or {};self.data.setdefault('known',{});self.data.setdefault('pending',{})
    def reconcile(self,rows):
        rows=[r for r in rows if shareable(r)]
        if {str(r['id']) for r in rows}==set(self.data['known']):return False
        current={str(r['id']):dict(r,id=str(r['id']),source=r.get('source','yandex')) for r in rows if shareable(r)}
        known=self.data['known'];pending=self.data['pending']
        for key,row in current.items():
            if key not in known:pending[key]={'op':str(uuid.uuid4()),'liked':True,'track':row}
        for key,row in known.items():
            if key not in current:pending[key]={'op':str(uuid.uuid4()),'liked':False,'track':row}
        self.data['known']=current
        return True
    def request(self):
        def clean(op):
            t=op['track'];row={k:t.get(k,'') for k in ('id','source','title','artist','artist_id','genre')};row['duration']=t.get('duration',0)
            for k in ('url','artist_url','cover'):
                value=t.get(k) or '';u=urlsplit(value)
                row[k]=value if u.scheme=='https' and not u.username and not u.password and not u.query and not u.fragment else ''
            return dict(op,track=row)
        return {'cursor':self.data.get('cursor',0),'ops':[clean(o) for o in list(self.data['pending'].values())[:100]]}
    def apply(self,response,rows):
        self.reconcile(rows);ack=set(response['ack']);pending=self.data['pending']
        for k in list(pending):
            if pending[k]['op'] in ack:del pending[k]
        result={str(r['id']):r for r in rows}
        for e in response['events']:
            row=e['track'];key=str(row['id'])
            if not shareable(row) or key in pending:continue
            row=dict(row,remote_id=key.split(':',1)[-1])
            if row['source']=='yandex':row['remote_id']=key.split(':')[0]
            if e['liked']:
                if key not in result:result={key:row,**result}
                else:result[key]=row
            else:result.pop(key,None)
        self.data['known']={k:r for k,r in result.items() if shareable(r)};self.data['cursor']=response['cursor']
        return result

def exchange(token,payload):
    r=requests.post(BASE+'/sync',json=payload,headers={'Authorization':'Bearer '+token},timeout=(8,15),allow_redirects=False)
    if r.status_code==401:raise PermissionError('sign_in')
    r.raise_for_status()
    if len(r.content)>2*1024*1024:raise ValueError('size')
    return r.json()

class CloudSync:
    def __init__(self):
        super().__init__();self.cloud_account=None;self.cloud_state=None;self.cloud_future=None;self.cloud_next=0;self.cloud_status=''
        self.cloud_pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='PulseSync')
        self.cloud_local=self._cloud_load('cloud-local.json',{})
        self.cloud_timer=QTimer(self);self.cloud_timer.timeout.connect(self.cloud_tick);self.cloud_timer.start(1500)
        QTimer.singleShot(0,self.cloud_tick)

    def _cloud_load(self,name,default):
        try:return json.loads((self.data_dir/name).read_text(encoding='utf8'))
        except (ValueError,OSError):return default

    def cloud_tick(self):
        if getattr(self,'closing',False):return
        try:self._cloud_tick()
        except Exception:self.cloud_status='Лайки сохранены на компьютере. Повторим синхронизацию.';self.cloud_next=time.monotonic()+15

    def _cloud_tick(self):
        p=self.profile;owner=(p.get('provider','local')+':'+str(p.get('provider_id') or p.get('id'))) if p.get('id') else ''
        # Keep each local account's favourites separate; first migration adopts the existing library.
        previous=self.cloud_local.get('owner');local_changed=previous!=owner
        if previous!=owner:
            if previous is not None:
                self.cloud_local.setdefault('accounts',{})[previous]=dict(self.favorites)
                self.favorites=dict(self.cloud_local.get('accounts',{}).get(owner,{}))
                self.save_data('favorites.json',self.favorites)
            self.cloud_local['owner']=owner
        if self.cloud_local.setdefault('accounts',{}).get(owner)!=self.favorites:
            self.cloud_local['accounts'][owner]=dict(self.favorites);local_changed=True
        if local_changed:self.save_data('cloud-local.json',self.cloud_local)
        account=str(p.get('provider_id','')) if p.get('provider')=='telegram' else ''
        if account!=self.cloud_account:
            self.cloud_account=account;self.cloud_next=0
            self.cloud_name='cloud-state-'+hashlib.sha256(account.encode()).hexdigest()+'.json'
            self.cloud_state=SyncState(self._cloud_load(self.cloud_name,{})) if account else None
        if not account:return
        state=self.cloud_state
        if state.reconcile(self.favorites.values()):self.save_data(self.cloud_name,state.data)
        if self.cloud_future:
            if not self.cloud_future.done():return
            future=self.cloud_future;self.cloud_future=None
            if self.cloud_job_owner!=account:return
            try:reply=future.result()
            except PermissionError:self.cloud_status='Войди через Telegram ещё раз для синхронизации';self.cloud_next=time.monotonic()+30;return
            except Exception:self.cloud_status='Нет связи. Лайки сохранены на компьютере';self.cloud_next=time.monotonic()+15;return
            rows=state.apply(reply,self.favorites.values());changed=rows!=self.favorites
            self.favorites=rows;self.save_data('favorites.json',rows);self.save_data(self.cloud_name,state.data)
            self.cloud_status='Лайки синхронизированы';self.cloud_next=time.monotonic()+(0 if reply.get('more') or state.data['pending'] else 10)
            if changed:
                if self.view=='favorites':self.show_favorites()
                if 0<=self.current<len(self.queue):self.current_favorite.setChecked(self.queue[self.current]['id'] in rows)
                self.refresh_profile()
        if time.monotonic()<self.cloud_next:return
        path=self.data_dir/('cloud-'+hashlib.sha256(account.encode()).hexdigest()+'.bin')
        try:token=seal(path.read_bytes(),True).decode()
        except (OSError,ValueError):self.cloud_status='Войди через Telegram ещё раз для синхронизации';return
        payload=json.loads(json.dumps(state.request()));self.cloud_job_owner=account
        self.cloud_future=self.cloud_pool.submit(exchange,token,payload)

    def build_profile(self):
        super().build_profile()
        from PySide6.QtWidgets import QLabel
        self.cloud_caption=QLabel('Синхронизация лайков доступна через Telegram')
        self.cloud_caption.setWordWrap(True);self.profile_dialog.body.layout().addWidget(self.cloud_caption)
        self.profile_dialog.body.layout().addWidget(self.button('Обновить Telegram-вход для синхронизации',lambda:self.begin_identity('telegram')))

    def open_profile(self):
        super().open_profile();self.cloud_caption.setText(self.cloud_status or 'Лайки синхронизируются между телефоном и ПК после входа в один Telegram-аккаунт.')

    def logout_profile(self):
        self.cloud_tick();super().logout_profile();self.cloud_tick()

    def profile_for_identity(self,identity):
        self.cloud_tick();return super().profile_for_identity(identity)

    def closeEvent(self,event):
        self.cloud_tick();self.cloud_timer.stop();self.cloud_pool.shutdown(wait=False,cancel_futures=True)
        super().closeEvent(event)
