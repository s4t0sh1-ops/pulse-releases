import hashlib,hmac,json,os,re,secrets,sys,time,uuid
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QEvent,QPoint,QUrl
from PySide6.QtGui import QFont,QIcon
from PySide6.QtWidgets import (QWidget,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout,QLineEdit,QSizeGrip,QComboBox,QSizePolicy)
from PySide6.QtMultimedia import QMediaPlayer
from pages import InAppPage
from skin import MetalButton
from listening_ui import TitleBar,ListeningPage,ClickArtwork
from lyrics import LyricsService
from public_music import Audius

class Experience:
    def __init__(self):
        self.audius=Audius();self.lyrics_service=LyricsService(self.data_dir);self.lyrics_version=0;self.lyrics_track=None;self.public_home_loading=False
        self.search_results={};self.search_pending=set();self.search_unavailable=[];self.now_page=None;self.registration=None
        super().__init__()
        self.title_bar=TitleBar(self);self.root.layout().insertWidget(0,self.title_bar)
        self.size_grip=QSizeGrip(self.root);self.size_grip.setFixedSize(14,14);self.size_grip.raise_()
        self.rebuild_dock();self.now_page=ListeningPage(self)
        self.media.positionChanged.connect(lambda n:self.now_page.update_position(n,self.media.duration()))
        self.media.durationChanged.connect(lambda n:self.now_page.update_position(self.media.position(),n))
        self.build_registration()
        self.finish_identity_profile()
        self.show_home()

    def finish_identity_profile(self):
        form=self.profile_dialog.body.layout().itemAt(0).widget().layout()
        self.profile_email=QLabel(self.profile.get('email','Локальный профиль · почта не указана'));self.profile_email.setObjectName('muted');form.insertWidget(1,self.profile_email)
        form.insertWidget(2,self.button('Почта и пароль профиля',self.open_registration))

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.Resize and hasattr(self,'size_grip') and watched==self.root:
            self.size_grip.move(self.root.width()-15,self.root.height()-15)
        if event.type()==QEvent.Type.WindowStateChange and watched==self and hasattr(self,'backgrounds'):self.backgrounds.apply()
        return super().eventFilter(watched,event)

    def nativeEvent(self,event_type,message):
        if sys.platform=='win32' and not self.isMaximized():
            import ctypes
            from ctypes import wintypes
            msg=wintypes.MSG.from_address(int(message))
            if msg.message==0x84:
                x=ctypes.c_short(msg.lParam&0xffff).value;y=ctypes.c_short((msg.lParam>>16)&0xffff).value
                p=self.mapFromGlobal(QPoint(x,y));left=p.x()<7;right=p.x()>=self.width()-7;top=p.y()<7;bottom=p.y()>=self.height()-7
                hit=13 if top and left else 14 if top and right else 16 if bottom and left else 17 if bottom and right else 10 if left else 11 if right else 12 if top else 15 if bottom else 0
                if hit:return True,hit
        return super().nativeEvent(event_type,message)

    def rebuild_dock(self):
        dock=self.seek.parentWidget();layout=dock.layout();old=layout.takeAt(0).layout()
        old_buttons=[]
        while old.count():
            item=old.takeAt(0)
            if item.widget():old_buttons.append(item.widget())
            elif item.layout():
                nested=item.layout()
                while nested.count():nested.takeAt(0)
        old.deleteLater()
        row=QWidget();grid=QGridLayout(row);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(10)
        grid.setColumnStretch(0,1);grid.setColumnStretch(1,0);grid.setColumnStretch(2,1)
        left=QWidget();left.setMinimumWidth(0);left.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        info=QHBoxLayout(left);info.setContentsMargins(0,0,0,0);info.setSpacing(11)
        old_art=self.dock_art;self.dock_art=ClickArtwork(46);self.dock_art.pixmap=old_art.pixmap;self.dock_art.clicked.connect(self.open_now);self.dock_art.setToolTip('Открыть трек');old_art.hide();old_art.deleteLater()
        info.addWidget(self.dock_art);words=QVBoxLayout();words.setSpacing(3);words.addWidget(self.now);words.addWidget(self.now_artist);info.addLayout(words,1)
        info.addWidget(self.current_favorite);grid.addWidget(left,0,0)
        center=QWidget();buttons=QHBoxLayout(center);buttons.setContentsMargins(0,0,0,0);buttons.setSpacing(9)
        center_buttons=[]
        for glyph,tip,fn in [('queue','Очередь',self.show_queue),('previous','Предыдущий',lambda:self.step(-1))]:center_buttons.append(self.icon_button(glyph,tip,fn))
        center_buttons.append(self.play_button);self.play_button.setFixedSize(48,48)
        center_buttons.append(self.icon_button('next','Следующий',lambda:self.step(1)));center_buttons.append(self.shuffle_button)
        for b in center_buttons:buttons.addWidget(b)
        self.transport=center;grid.addWidget(center,0,1,Qt.AlignmentFlag.AlignHCenter)
        right=QWidget();right.setMinimumWidth(0);right.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        controls=QHBoxLayout(right);controls.setContentsMargins(0,0,0,0);controls.setSpacing(9);controls.addStretch()
        self.lyrics_button=self.icon_button('lyrics','Текст песни',lambda:self.open_now(True));controls.addWidget(self.lyrics_button)
        controls.addWidget(self.mute_button);controls.addWidget(self.volume);grid.addWidget(right,0,2)
        used=[self.now,self.now_artist,self.current_favorite,self.play_button,self.shuffle_button,self.mute_button,self.volume,old_art]
        for widget in old_buttons:
            if widget not in used:widget.hide();widget.deleteLater()
        layout.insertWidget(0,row)
        self.now.setStyleSheet('font-size:13px;font-weight:700;');self.now_artist.setStyleSheet('font-family:Segoe UI;font-size:13px;font-weight:500;color:#c3c6d1;')

    def first_run(self):
        if '--smoke-test' in sys.argv or os.environ.get('PULSE_TEST_MODE')=='1':return
        if not self.profile:self.open_registration()
        else:self.maybe_tour()

    def build_registration(self):
        self.registration=self.registration_page()
        outer=QVBoxLayout(self.registration.body);outer.setContentsMargins(24,20,24,24);outer.addStretch()
        card=QWidget();card.setMaximumWidth(460);card.setMinimumWidth(360);box=QVBoxLayout(card);box.setSpacing(16)
        title=QLabel('Музыка начинается\nс тебя.');title.setStyleSheet('font-size:32px;font-weight:800;letter-spacing:-1px');box.addWidget(title)
        hint=QLabel('Выбери вход через сервис или создай локальный профиль. Библиотека и настройки сохраняются на этом компьютере.');hint.setWordWrap(True);hint.setObjectName('muted');box.addWidget(hint)
        self.register_name=QLineEdit();self.register_name.setPlaceholderText('Твоё имя');self.register_name.setMaxLength(40)
        self.register_email=QLineEdit();self.register_email.setPlaceholderText('Электронная почта');self.register_email.setMaxLength(254)
        self.register_password=QLineEdit();self.register_password.setPlaceholderText('Пароль · минимум 6 символов');self.register_password.setEchoMode(QLineEdit.EchoMode.Password);self.register_password.setMaxLength(128)
        for caption,field in [('Имя',self.register_name),('Почта',self.register_email),('Пароль',self.register_password)]:
            label=QLabel(caption);label.setStyleSheet('font-size:12px;color:#a8afc1');box.addWidget(label);box.addWidget(field)
        self.register_error=QLabel();self.register_error.setWordWrap(True);self.register_error.setStyleSheet('color:#f4a8b5');box.addWidget(self.register_error)
        self.register_button=self.button('Создать профиль',self.register_local,primary=True);box.addWidget(self.register_button)
        self.register_password.returnPressed.connect(self.register_local)
        outer.addWidget(card,0,Qt.AlignmentFlag.AlignHCenter);outer.addStretch()
    def open_registration(self):
        self.register_name.setText(self.profile.get('name',''));self.register_email.setText(self.profile.get('email',''));self.register_password.clear();self.register_error.clear();self.registration.show()
    def register_local(self):
        name=self.register_name.text().strip();email=self.register_email.text().strip();password=self.register_password.text()
        if len(name)<2:self.register_error.setText('Введи имя: минимум 2 символа.');return
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):self.register_error.setText('Проверь адрес почты. Подтверждение письмом не требуется.');return
        if len(password)<6:self.register_error.setText('Для пароля нужно минимум 6 символов.');return
        salt=secrets.token_bytes(16);digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,200000)
        self.profile.update(id=self.profile.get('id',str(uuid.uuid4())),name=name,email=email,local_auth={'salt':salt.hex(),'hash':digest.hex(),'iterations':200000,'algorithm':'pbkdf2-sha256'})
        self.save_data('profile.json',self.profile);self.register_password.clear();self.name_edit.setText(name);self.profile_email.setText(email)
        self.profile_nav.setToolTip(name+' · профиль');self.registration.accept();self.maybe_tour()

    def search(self):
        query=self.query.text().strip()
        if not query:return
        self.hide_pages();self.search_version+=1;version=self.search_version;self.search_results={};self.search_unavailable=[]
        sources=['soundcloud','audius','yandex'];self.search_pending=set(sources)
        self.suggestions.hide();self.view='search';self.status.setText('Ищу музыку во всей медиатеке…')
        local=[r for r in self.local_library.values() if self.artist_key(query) in self.artist_key(r['title']+' '+r['artist'])]
        self.search_results['local']=(local,[]);self.render([]);self.client_for_search=self.client or self.catalog
        for source in sources:
            def work(_,s=source):
                if s!='yandex':
                    from matching import variants
                    rows=[];artists=[]
                    for variant in variants(query):
                        batch,cards=getattr(self,s).search(variant);rows+=batch;artists+=cards
                    return rows,artists
                client=self.client_for_search;result=client.search(query,type_='all',timeout=8)
                artists=[self.artist_data(a) for a in (result.artists.results if getattr(result,'artists',None) else [])][:6]
                rows=[self.track_data(t) for t in (result.tracks.results if result.tracks else [])]
                key=self.artist_key(query);matches=[a for a in artists if len(key)>=3 and self.artist_key(a['name'])==key]
                if matches:
                    catalog=[]
                    for page in range(2):
                        data=client.artists_tracks(matches[0]['id'],page=page,page_size=100);batch=[self.track_data(t) for t in data.tracks];catalog+=batch
                        if not batch or len(catalog)>=getattr(getattr(data,'pager',None),'total',len(catalog)):break
                    if catalog:rows=catalog+rows
                return rows,artists
            job=self.task(work,lambda result,s=source:self.merge_search(version,s,result));job.unified_version=version;job.unified_source=source
    def merge_search(self,version,source,result,failed=False):
        if version!=self.search_version:return
        self.search_pending.discard(source);self.search_results[source]=result
        if failed:self.search_unavailable.append(source)
        rows=[];artists=[];seen=set();artist_seen=set();key=self.artist_key(self.query.text())
        for batch,cards in self.search_results.values():
            for row in batch:
                if row['id'] not in seen:rows.append(row);seen.add(row['id'])
            for artist in cards:
                k=(artist.get('source','yandex'),str(artist['id']))
                if k not in artist_seen:artists.append(artist);artist_seen.add(k)
        def score(row):
            artist=self.artist_key(row['artist']);title=self.artist_key(row['title'])
            return (4 if artist==key else 3 if artist.startswith(key) else 0)+(3 if title==key else 2 if title.startswith(key) else 0)
        rows.sort(key=lambda r:(-score(r),-min(10000000,r.get('popularity',0))))
        self.view='search';self.render(rows);self.show_artists(artists)
        self.status.setText(f'Найдено {len(rows)} треков'+(' · поиск продолжается…' if self.search_pending else ' · часть источников не ответила' if self.search_unavailable else ''))
    def job_failed(self,payload):
        name,job=payload
        if hasattr(job,'unified_version'):
            self.jobs.discard(job);self.merge_search(job.unified_version,job.unified_source,([],[]),True);return
        if getattr(job,'lyrics_job',False):
            self.jobs.discard(job)
            if job.lyrics_version==self.lyrics_version:self.now_page.canvas.set_data({'missing':True});self.now_page.caption.setText('Источник текста временно недоступен')
            return
        if getattr(job,'public_home',False):self.jobs.discard(job);self.public_home_loading=False;return
        super().job_failed(payload)

    def show_home(self):
        super().show_home()
        if hasattr(self,'home_panel') and not self.client and not self.home_rows and not self.public_home_loading:
            self.public_home_loading=True
            def done(rows):
                self.public_home_loading=False
                if not self.client:self.home_rows=rows[:20]
                if self.view=='home' and not self.client:self.render(self.home_rows);self.status.clear()
            job=self.task(lambda _:self.audius.trending(limit=20),done);job.public_home=True
    def start_wave(self,seed=None):
        if seed is None and not self.client:
            candidates=[r for r in self.stats['history']+list(self.favorites.values()) if r.get('source') in ('audius','soundcloud')]
            if candidates:return super().start_wave(candidates[0])
            if self.home_rows:return super().start_wave(self.home_rows[0])
            self.status.setText('Найди трек, чтобы начать свою волну.');self.open_search();return
        super().start_wave(seed)
    def activate_track(self,index):
        super().activate_track(index)
    def open_now(self,lyrics=False):
        if not 0<=self.current<len(self.queue):self.status.setText('Сначала включи трек');return
        self.now_page.update_row(self.queue[self.current]);self.now_page.show()
        if lyrics and not self.now_page.lyrics_host.isVisible():self.now_page.show_lyrics()
    def play_index(self,index,resume=0,recovery=False):
        if not recovery:self.lyrics_version+=1;self.lyrics_track=None
        super().play_index(index,resume,recovery)
        if self.now_page and 0<=index<len(self.queue):
            self.now_page.update_row(self.queue[index]);self.now_page.canvas.set_data({})
            if self.now_page.isVisible() and self.now_page.lyrics_host.isVisible():self.load_lyrics()
    def load_lyrics(self):
        if not 0<=self.current<len(self.queue):return
        row=dict(self.queue[self.current]);key=row.get('source','')+row['id']
        if self.lyrics_track==key:return
        self.lyrics_track=key;self.lyrics_version+=1;version=self.lyrics_version;client=self.client
        self.now_page.canvas.set_data({});self.now_page.caption.setText('Ищу текст и точные тайминги…')
        def done(data):
            if version!=self.lyrics_version:return
            self.now_page.canvas.set_data(data)
            mode='Подсветка слов' if any(r.get('words') for r in data.get('lines',[])) else 'Построчная синхронизация' if data.get('lines') else 'Текст без таймингов' if data.get('plain') else 'Текст недоступен'
            self.now_page.caption.setText(mode+(' · '+data['source'] if data.get('source') else ''))
        job=self.task(lambda _:self.lyrics_service.fetch(row,client),done);job.lyrics_job=True;job.lyrics_version=version
    def state_changed(self,state):
        super().state_changed(state)
        if self.now_page:self.now_page.play.setGlyph('pause' if state==QMediaPlayer.PlaybackState.PlayingState else 'play')
    def favorite_current(self):
        super().favorite_current()
        if self.now_page:self.now_page.like.setChecked(self.current_favorite.isChecked())
