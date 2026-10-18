"""Playback continuity, recording choices, wave preferences and releases."""
import json, os, random, sys
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QUrl,QEvent
from PySide6.QtWidgets import QWidget,QLabel,QVBoxLayout,QHBoxLayout,QComboBox,QCheckBox,QProgressBar
from PySide6.QtMultimedia import QMediaPlayer
from pages import InAppPage
from matching import compact,recording_key,search_score,text_score,version_tags
from discovery import PublicDiscovery,similarity
import updates

class Upgrades:
    def __init__(self):
        self.choice_generation=0;self.choice_pending=False;self.choice_tried=set();self.choice_pool=None
        self.choice_seed=None;self.restored_resume=None;self.update_busy=False;self.update_ready=None
        self.wave_preferences={'mode':'balanced','avoid_recent':True,'exclude':[],'blocked':{}}
        try:self.wave_preferences.update(json.loads((self.data_dir/'wave-preferences.json').read_text(encoding='utf8')))
        except (OSError,ValueError,TypeError):pass
        if self.wave_preferences.get('mode') not in ('balanced','discovery','familiar'):self.wave_preferences['mode']='balanced'
        if not isinstance(self.wave_preferences.get('blocked'),dict):self.wave_preferences['blocked']={}
        if not isinstance(self.wave_preferences.get('exclude'),list):self.wave_preferences['exclude']=[]
        super().__init__()
        for label in (self.now_artist,self.now_page.artist):
            label.setCursor(Qt.CursorShape.PointingHandCursor);label.installEventFilter(self)
            label.setAccessibleName('Открыть исполнителя');label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.wave_settings_button=self.button('Настроить волну',self.open_wave_settings)
        self.wave_hero.layout().itemAt(1).layout().insertWidget(3,self.wave_settings_button,0,Qt.AlignmentFlag.AlignLeft)
        self.settings_panel.layout().addWidget(self.button('Настроить мою волну',self.open_wave_settings))
        self.build_update_page();self.refresh_wave_caption()
        self.session_timer=QTimer(self);self.session_timer.setInterval(5000);self.session_timer.timeout.connect(self.save_session);self.session_timer.start()
        QTimer.singleShot(260,self.restore_session)
        if os.environ.get('PULSE_TEST_MODE')!='1' and '--smoke-test' not in sys.argv:QTimer.singleShot(12000,lambda:self.check_updates(True))

    def eventFilter(self,watched,event):
        if hasattr(self,'now_page') and self.now_page and watched in (self.now_artist,self.now_page.artist):
            if (event.type()==QEvent.Type.MouseButtonRelease and event.button()==Qt.MouseButton.LeftButton) or (event.type()==QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Space)):
                self.open_playing_artist();return True
        return super().eventFilter(watched,event)

    def open_playing_artist(self):
        if not 0<=self.current<len(self.queue):return
        row=self.queue[self.current];artists=row.get('artists') or []
        if not artists and row.get('artist_url'):artists=[{'name':row['artist'],'id':row.get('artist_id',row['artist_url']),'url':row['artist_url'],'source':row.get('source','soundcloud')}]
        if not artists:
            self.open_search();self.query.setText(row.get('artist',''));self.search();return
        artists=[dict(a,source=a.get('source',row.get('source','yandex'))) for a in artists]
        if len(artists)==1:self.open_artist(artists[0]);return
        page=InAppPage(self.content_host,'Исполнители трека');box=QVBoxLayout(page.body);box.setSpacing(12)
        for artist in artists:box.addWidget(self.button(artist['name'],lambda checked=False,a=artist:self.open_artist(a)))
        box.addStretch();self.extra_pages.append(page);page.show()

    def merge_search(self,version,source,result,failed=False):
        super().merge_search(version,source,result,failed)
        if version!=self.search_version:return
        query=self.query.text();rows=list(self.rows)
        rows.sort(key=lambda r:(-search_score(query,r),-min(int(r.get('popularity',0) or 0),10000000),r.get('source',''),str(r['id'])))
        # Keep weak matches after exact results; availability must not outrank identity.
        self.render(rows)
        cards=[];seen=set()
        for _,artists in self.search_results.values():
            for a in artists:
                identity=(a.get('source','yandex'),str(a['id']))
                if identity not in seen:cards.append(a);seen.add(identity)
        cards.sort(key=lambda a:(-text_score(query,a['name']),compact(a['name']),a.get('source','')))
        self.show_artists(cards[:12])

    def save_session(self):
        if not hasattr(self,'media') or not 0<=self.current<len(self.queue):return
        position=self.restored_resume if self.restored_resume is not None else self.media.position()
        if self.loading_audio:position=max(position,int(getattr(self,'resume_position',0)))
        start=max(0,self.current-100)
        state={'schema':1,'queue':self.queue[start:start+2000],'index':self.current-start,'position':max(0,int(position)),
               'shuffle':self.shuffle_button.isChecked(),'repeat':self.repeat_mode,'wave':self.wave_mode,
               'wave_context':self.wave_context,'wave_title':getattr(self,'wave_title','Моя волна')}
        try:self.save_data('playback-session.json',state)
        except (OSError,TypeError,ValueError):pass

    def restore_session(self):
        if not self.profile or self.queue or self.current>=0:return
        try:
            path=self.data_dir/'playback-session.json'
            if path.stat().st_size>8*1024*1024:return
            state=json.loads(path.read_text(encoding='utf8'))
            if state.get('schema')!=1:return
            queue=state['queue'];index=int(state['index'])
            if not isinstance(queue,list) or not 0<=index<len(queue)<=2000:return
            if any(not isinstance(r,dict) or not all(isinstance(r.get(k),str) for k in ('id','title','artist')) or r.get('source','yandex') not in ('local','yandex','audius','soundcloud') for r in queue):return
            row=queue[index];position=max(0,min(int(state.get('position',0)),int(row.get('duration',0) or 86400000)))
        except (OSError,ValueError,TypeError,KeyError):return
        self.queue=queue;self.current=index;self.restored_resume=position;self.want_playing=False
        self.repeat_mode=int(state.get('repeat',0)) if state.get('repeat') in (0,1,2) else 0
        self.shuffle_button.setChecked(bool(state.get('shuffle')))
        context=state.get('wave_context');self.wave_mode=bool(state.get('wave'))
        self.wave_context=context if isinstance(context,dict) and context.get('source') in ('audius','soundcloud') else None
        self.wave_mode=self.wave_mode and bool(self.wave_context)
        self.wave_title=str(state.get('wave_title','Моя волна'))[:180]
        self.now.setText(row['title']);self.now_artist.setText(row['artist']);self.cover_loader.load(row.get('cover'),self.dock_art)
        self.current_favorite.setChecked(row['id'] in self.favorites);self.seek.setRange(0,int(row.get('duration',0)));self.seek.setValue(position)
        self.now_page.update_row(row);self.status.setText('Очередь восстановлена · нажми ▶, чтобы продолжить')

    def toggle(self):
        if self.restored_resume is not None and 0<=self.current<len(self.queue):
            position=self.restored_resume;self.restored_resume=None;self.play_index(self.current,resume=position);return
        super().toggle()

    def play_index(self,index,resume=0,recovery=False):
        if not 0<=index<len(self.queue):return
        self.restored_resume=None;self.choice_generation+=1;self.choice_pending=False
        row=self.queue[index]
        if not recovery:
            self.choice_seed=dict(row.get('_origin') or row);self.choice_pool=None;self.choice_tried=set()
            self.track_listened=0.;self.track_counted=False;self.recoveries=0;self.has_progress=False;self.ending_handled=False
        self.choice_tried.add((row.get('source','yandex'),row['id']))
        if row.get('source','yandex')=='yandex' and not self.client:
            self.current=index;self.resolve_generation+=1;self.play_version+=1;self.media.stop();self.media.setSource(QUrl())
            self.now.setText(row['title']);self.now_artist.setText(row['artist']);self.cover_loader.load(row.get('cover'),self.dock_art)
            self.now_page.update_row(row);self.want_playing=True;self.loading_audio=True;self.resume_position=resume
            self.try_alternative(resume);return
        super().play_index(index,resume,recovery)

    def discovery(self):
        if not hasattr(self,'public_discovery'):self.public_discovery=PublicDiscovery({'soundcloud':self.soundcloud,'audius':self.audius})
        return self.public_discovery

    def try_alternative(self,position=None):
        if self.choice_pending or not 0<=self.current<len(self.queue):return self.choice_pending
        row=dict(self.choice_seed or self.queue[self.current]);index=self.current
        if row.get('source')=='local':return False
        self.choice_generation+=1;generation=self.choice_generation;self.choice_pending=True
        self.play_version+=1;self.resolve_generation+=1
        wanted=self.want_playing;position=max(0,int(self.media.position() if position is None else position))
        self.loading_audio=True;self.media.stop();self.media.setSource(QUrl())
        self.show_playback_notice('Подбираю совпадающую полную запись…')
        def done(rows):
            if generation!=self.choice_generation:return
            wanted=self.want_playing
            self.choice_pending=False;self.choice_pool=rows
            candidates=[r for r in rows if similarity(row,r)>0 and (r.get('source','yandex'),r['id']) not in self.choice_tried]
            if not candidates:
                self.loading_audio=False;self.want_playing=False
                self.show_playback_notice('Совпадающая доступная запись не найдена. Открой «Версии трека» в меню песни.');return
            candidate=dict(candidates[0]);candidate['_origin']=row
            self.choice_tried.add((candidate.get('source'),candidate['id']));self.queue[index]=candidate
            self.loading_audio=False
            # The same recording uses the normal transport without resetting fallback attempts.
            super(Upgrades,self).play_index(index,position,True);self.want_playing=wanted
        if self.choice_pool is not None:done(self.choice_pool)
        else:
            job=self.task(lambda _:self.discovery().candidates(row),done);job.choice_job=True;job.choice_generation=generation
        def expired():
            if generation==self.choice_generation and self.choice_pending:
                self.choice_generation+=1;self.choice_pending=False;self.loading_audio=False;self.want_playing=False
                self.show_playback_notice('Источники не ответили вовремя. Повтори запуск или выбери версию трека.')
        QTimer.singleShot(16000,expired);return True

    def playback_error(self,*args):
        if self.want_playing and self.try_alternative():return
        super().playback_error(*args)

    def recover_playback(self):
        if self.want_playing and not self.loading_audio and self.try_alternative():return
        super().recover_playback()

    def audio_load_timeout(self,version):
        if version==self.play_version and self.loading_audio and self.try_alternative():return
        super().audio_load_timeout(version)

    def track_menu(self,index,pos):
        super().track_menu(index,pos)
        if not 0<=index<len(self.rows):return
        row=dict(self.rows[index]);self.active_menu.addSeparator()
        self.active_menu.addAction('Версии трека').triggered.connect(lambda:self.show_versions(row))
        self.active_menu.addAction('Не предлагать этого исполнителя в волне').triggered.connect(lambda:self.block_wave_artist(row))

    def show_versions(self,row):
        page=InAppPage(self.content_host,'Версии · '+row['title']);box=QVBoxLayout(page.body);box.setSpacing(12)
        message=QLabel('Ищу доступные записи…');message.setWordWrap(True);box.addWidget(message);box.addStretch()
        self.extra_pages.append(page);page.show()
        def done(rows):
            if not page.isVisible():return
            rows=[r for r in rows if search_score(row['title'],r)>=65][:20]
            message.setText('Автоматически выбирается та же запись. Другую обработку можно включить вручную.' if rows else 'Других доступных записей не найдено.')
            for candidate in rows:
                label=candidate['title']+' · '+candidate['artist']+' · '+candidate.get('source','')
                def choose(checked=False,r=candidate):
                    page.hide();self.wave_mode=False;self.wave_generation+=1;self.wave_context=None;self.queue=[dict(r)];self.play_index(0)
                box.insertWidget(box.count()-1,self.button(label,choose))
        job=self.task(lambda _:self.discovery().candidates(row),done);job.versions_job=True;job.versions_message=message

    def prepare_wave_rows(self,rows,context=None,queued=None):
        prefs=self.wave_preferences;seen={recording_key(r) for r in (queued or [])}
        recent={recording_key(r) for r in self.stats['history'][:50]} if prefs['avoid_recent'] else set()
        blocked=prefs.get('blocked',{});result=[]
        for row in rows:
            identity=recording_key(row)
            names=[a.get('name','') for a in row.get('artists',[])] or [row.get('artist','')]
            if identity in seen or identity in recent or any(compact(n) in blocked for n in names):continue
            if version_tags(row)&set(prefs.get('exclude',[])):continue
            seen.add(identity);result.append(row)
        random.SystemRandom().shuffle(result)
        liked={compact(r.get('artist','')) for r in self.favorites.values()}
        known=liked|{compact(r.get('artist','')) for r in self.stats['history']}
        if prefs['mode']=='discovery':result.sort(key=lambda r:compact(r.get('artist','')) in known)
        elif prefs['mode']=='familiar':result.sort(key=lambda r:compact(r.get('artist','')) not in known)
        return result

    def refresh_wave_caption(self):
        self.wave_hero.subtitle.setText({'balanced':'По твоим вкусам','discovery':'Больше открытий','familiar':'Знакомые исполнители'}[self.wave_preferences['mode']])

    def block_wave_artist(self,row):
        self.wave_preferences['blocked'][compact(row['artist'])]=row['artist'];self.save_data('wave-preferences.json',self.wave_preferences)
        self.status.setText('Исполнитель исключён из новых рекомендаций. Изменить можно в настройках волны.')

    def open_wave_settings(self):
        page=InAppPage(self.content_host,'Настрой свою волну');box=QVBoxLayout(page.body);box.setContentsMargins(30,20,30,24);box.setSpacing(18)
        box.addWidget(QLabel('Что хочется слушать?'))
        mode=QComboBox();mode.addItem('Баланс знакомого и нового','balanced');mode.addItem('Больше новых исполнителей','discovery');mode.addItem('Больше знакомых исполнителей','familiar');mode.setCurrentIndex(mode.findData(self.wave_preferences['mode']));box.addWidget(mode)
        recent=QCheckBox('Не повторять последние 50 прослушанных треков');recent.setChecked(self.wave_preferences['avoid_recent']);box.addWidget(recent)
        box.addWidget(QLabel('Какие версии исключить из рекомендаций?'));checks={}
        for key,text in [('slowed','Slowed'),('sped','Ускоренные версии'),('live','Концертные записи'),('cover','Каверы'),('remix','Ремиксы')]:
            check=QCheckBox(text);check.setChecked(key in self.wave_preferences['exclude']);checks[key]=check;box.addWidget(check)
        box.addWidget(QLabel('Исключённые исполнители'));blocked=dict(self.wave_preferences['blocked'])
        if not blocked:box.addWidget(QLabel('Пока никого. Исключить исполнителя можно в меню трека.'))
        for key,name in list(blocked.items()):
            button=self.button(name+' · вернуть в волну',lambda checked=False,k=key:None)
            def unblock(checked=False,k=key,b=button):blocked.pop(k,None);b.hide()
            button.clicked.connect(unblock);box.addWidget(button)
        def save():
            self.wave_preferences={'mode':mode.currentData(),'avoid_recent':recent.isChecked(),'exclude':[k for k,c in checks.items() if c.isChecked()],'blocked':blocked}
            self.save_data('wave-preferences.json',self.wave_preferences);self.refresh_wave_caption()
            if self.wave_mode:
                previous=self.queue[:self.current+1];future=self.prepare_wave_rows(self.queue[self.current+1:],self.wave_context,previous)
                self.queue=previous+future
                if self.view in ('wave','queue'):self.render(list(self.queue))
                if self.wave_context:self.next_wave_batch()
            page.accept()
        box.addWidget(self.button('Применить',save,primary=True));box.addStretch();self.extra_pages.append(page);page.show()

    def build_update_page(self):
        self.update_page=InAppPage(self.content_host,'Обновления Pulse');box=QVBoxLayout(self.update_page.body);box.setContentsMargins(30,24,30,24);box.setSpacing(18)
        box.addWidget(QLabel('Pulse '+updates.VERSION));self.update_text=QLabel('Проверяй новые версии здесь. Профиль и библиотека сохранятся.');self.update_text.setWordWrap(True);box.addWidget(self.update_text)
        self.update_auto=QCheckBox('Автоматически проверять обновления при запуске');self.update_auto.setChecked(self.preferences.get('check_updates',True));self.update_auto.toggled.connect(lambda value:self.preference('check_updates',value));box.addWidget(self.update_auto)
        self.update_check=self.button('Проверить обновления',lambda:self.check_updates(False));box.addWidget(self.update_check)
        self.update_progress=QProgressBar();self.update_progress.hide();box.addWidget(self.update_progress)
        self.update_action=self.button('Скачать обновление',self.download_update);self.update_action.hide();box.addWidget(self.update_action)
        self.update_install=self.button('Установить и перезапустить Pulse',self.install_update,primary=True);self.update_install.hide();box.addWidget(self.update_install);box.addStretch()
        self.settings_panel.layout().addWidget(self.button('Обновления Pulse',self.update_page.show))

    def check_updates(self,automatic=False):
        if self.update_busy or (automatic and not self.preferences.get('check_updates',True)):return
        self.update_busy=True;self.update_check.setEnabled(False);self.update_text.setText('Проверяю новую версию…')
        if not automatic:self.update_page.show()
        def done(release):
            self.update_busy=False;self.update_check.setEnabled(True);self.available_release=release
            self.update_text.setText('Доступна Pulse '+release['version']+'\n'+str(release.get('notes','')) if release else 'Установлена последняя опубликованная версия.')
            self.update_action.setVisible(bool(release))
            if release and automatic:
                self.status.setText('Доступна Pulse '+release['version']+' · открой «Обновления» в настройках')
        job=self.task(lambda _:updates.check_release(),done);job.update_job='check'

    def download_update(self):
        if self.update_busy or not getattr(self,'available_release',None):return
        self.update_busy=True;self.update_action.setEnabled(False);self.update_progress.show();self.update_progress.setValue(0)
        release=dict(self.available_release)
        def done(path):
            self.update_busy=False;self.update_ready=(path,release);self.update_progress.setValue(100);self.update_install.show();self.update_action.hide();self.update_text.setText('Обновление загружено и проверено. Можно перезапустить Pulse.');self.update_check.setEnabled(True)
        job=self.task(lambda signals:updates.download_release(release,self.data_dir/'updates',signals.progress.emit),done);job.update_job='download';job.signals.progress.connect(self.update_progress.setValue)

    def install_update(self):
        if not self.update_ready:return
        try:
            self.save_session();updates.install_release(*self.update_ready);self.close()
        except Exception:self.update_text.setText('Не удалось установить обновление. Закрой другие копии Pulse и повтори.');self.update_install.setEnabled(True)

    def job_failed(self,payload):
        _,job=payload
        if getattr(job,'choice_job',False):
            self.jobs.discard(job)
            if job.choice_generation==self.choice_generation:
                self.choice_pending=False;self.loading_audio=False;self.want_playing=False;self.show_playback_notice('Не удалось проверить другие записи. Проверь подключение и повтори.')
            return
        if getattr(job,'versions_job',False):self.jobs.discard(job);job.versions_message.setText('Источники не ответили. Попробуй позже.');return
        if getattr(job,'update_job',False):
            self.jobs.discard(job);self.update_busy=False;self.update_check.setEnabled(True);self.update_action.setEnabled(True)
            self.update_text.setText('Не удалось проверить обновление или его подлинность. Повтори позже.');return
        if hasattr(job,'play_version') and job.play_version==self.play_version:
            self.jobs.discard(job)
            if self.try_alternative():return
        super().job_failed(payload)

    def closeEvent(self,event):
        self.save_session();self.session_timer.stop();self.choice_generation+=1
        super().closeEvent(event)
