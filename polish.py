"""Glass surfaces, compact profile and visible playback diagnostics."""
import json,sys,time
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout,QLineEdit,QCheckBox,QSlider
from PySide6.QtMultimedia import QMediaPlayer
from pages import InAppPage
from library_ui import Artwork
import glass

class Polish:
    def __init__(self):
        self.preferences={'glass':58,'auto_next':True,'remember_volume':True,'volume':65}
        try:self.preferences.update(json.loads((self.data_dir/'preferences.json').read_text(encoding='utf8')))
        except (OSError,ValueError,TypeError):pass
        self.preferences['glass']=max(25,min(85,int(self.preferences['glass'])));glass.opacity=self.preferences['glass']/100
        super().__init__()
        if not self.preferences.get('glass_v09'):
            self.backgrounds.change('blur',max(2.,self.backgrounds.data['blur']));self.preference('glass_v09',True)
        dock=self.seek.parentWidget();self.playback_notice=QWidget();self.playback_notice.setObjectName('playbackNotice')
        row=QHBoxLayout(self.playback_notice);row.setContentsMargins(12,5,7,5);row.setSpacing(12)
        self.playback_message=QLabel();self.playback_message.setWordWrap(True);row.addWidget(self.playback_message,1)
        self.playback_connect=self.button('Подключить Яндекс',self.connect_yandex);row.addWidget(self.playback_connect)
        close=self.icon_button('close','Скрыть сообщение',lambda:self.playback_notice.hide());row.addWidget(close)
        dock.layout().insertWidget(0,self.playback_notice);self.playback_notice.hide()
        rail=self.profile_nav.parentWidget();self.support_nav=self.icon_button('support','Поддержка Pulse',self.open_support)
        rail.layout().insertWidget(rail.layout().count()-2,self.support_nav)
        self.volume.valueChanged.connect(self.remember_volume)
        if self.preferences['remember_volume']:self.volume.setValue(int(self.preferences.get('volume',65)))
        playback=QWidget();controls=QVBoxLayout(playback);controls.setContentsMargins(0,0,0,0);controls.setSpacing(8);controls.addWidget(QLabel('Воспроизведение'))
        self.auto_next.setText('Продолжать очередь после трека');self.remember_check.setText('Запоминать громкость');controls.addWidget(self.auto_next);controls.addWidget(self.remember_check);self.settings_panel.layout().addWidget(playback)
        self.apply_glass();self.refresh_profile()

    def build_profile(self):
        self.profile_dialog=InAppPage(self.content_host,'Профиль')
        outer=QVBoxLayout(self.profile_dialog.body);outer.setContentsMargins(22,16,22,20);outer.setSpacing(18)
        form=QWidget();form.setMaximumWidth(1120);form.setMinimumWidth(680);box=QVBoxLayout(form);box.setContentsMargins(0,0,0,0);box.setSpacing(16)
        outer.addWidget(form);outer.addStretch()
        header=QHBoxLayout();header.setSpacing(18);self.profile_avatar=Artwork(76);header.addWidget(self.profile_avatar)
        head=QVBoxLayout();head.setSpacing(4);self.profile_heading=QLabel(self.profile.get('name','Слушатель'));self.profile_heading.setStyleSheet('font-size:28px;font-weight:800;letter-spacing:-.7px;');head.addWidget(self.profile_heading)
        self.profile_email=QLabel();self.profile_email.setObjectName('muted');head.addWidget(self.profile_email)
        self.profile_identity=QLabel();self.profile_identity.setStyleSheet('font-size:10px;color:#a7a1b5;');head.addWidget(self.profile_identity);header.addLayout(head,1)
        header.addWidget(self.button('Изменить фото',self.choose_avatar));box.addLayout(header)
        metrics=QHBoxLayout();metrics.setSpacing(10);self.profile_metrics=[]
        for title in ('Слушал','Прослушано','Разных треков'):
            label=QLabel(title);label.setMinimumHeight(70);label.setObjectName('profileMetric');metrics.addWidget(label,1);self.profile_metrics.append(label)
        self.favorites_metric=QLabel();self.favorites_metric.setObjectName('profileMetric');metrics.addWidget(self.favorites_metric,1);box.addLayout(metrics)
        grid=QGridLayout();grid.setSpacing(14);grid.setColumnStretch(0,1);grid.setColumnStretch(1,1);box.addLayout(grid)
        def section(title,subtitle):
            host=QWidget();host.setObjectName('profileSection');layout=QVBoxLayout(host);layout.setContentsMargins(18,16,18,17);layout.setSpacing(11)
            heading=QLabel(title);heading.setStyleSheet('font-size:16px;font-weight:750;');layout.addWidget(heading)
            if subtitle:
                hint=QLabel(subtitle);hint.setWordWrap(True);hint.setObjectName('muted');layout.addWidget(hint)
            return host,layout
        personal,details=section('Личные данные','Видны только на этом компьютере')
        details.addWidget(QLabel('Имя'));self.name_edit=QLineEdit(self.profile.get('name',''));self.name_edit.setMaxLength(40);details.addWidget(self.name_edit)
        details.addWidget(QLabel('О себе'));self.bio_edit=QLineEdit(self.profile.get('bio',''));self.bio_edit.setPlaceholderText('Пара слов о твоей музыке');self.bio_edit.setMaxLength(120);details.addWidget(self.bio_edit)
        self.profile_saved=QLabel();self.profile_saved.setObjectName('muted');details.addWidget(self.profile_saved)
        actions=QHBoxLayout();actions.addWidget(self.button('Сохранить',self.save_profile,primary=True));details.addLayout(actions);grid.addWidget(personal,0,0)
        sources,source=section('Источники музыки','')
        self.account=QLabel('Яндекс Музыка · не подключена');self.account.setWordWrap(True);source.addWidget(self.account)
        self.login=self.button('Подключить Яндекс',self.connect_yandex,primary=True);source.addWidget(self.login)
        self.logout=self.button('Отключить Яндекс',self.sign_out);self.logout.hide();source.addWidget(self.logout)
        self.import_yandex=self.button('Импортировать треки',self.import_yandex_likes);source.insertWidget(3,self.import_yandex)
        self.import_result=QLabel();self.import_result.setWordWrap(True);self.import_result.setObjectName('muted');source.addWidget(self.import_result)
        for text in ('Audius · открытые треки без аккаунта','SoundCloud · публичные записи и ремиксы'):
            label=QLabel(text);label.setWordWrap(True);label.setObjectName('muted');source.addWidget(label)
        grid.addWidget(sources,0,1)
        # Keep persisted playback defaults; these controls no longer occupy the profile.
        hidden=QWidget(self.profile_dialog.body);hidden.hide()
        self.auto_next=QCheckBox(hidden);self.auto_next.setChecked(self.preferences['auto_next']);self.auto_next.toggled.connect(lambda value:self.preference('auto_next',value))
        self.remember_check=QCheckBox(hidden);self.remember_check.setChecked(self.preferences['remember_volume']);self.remember_check.toggled.connect(lambda value:self.preference('remember_volume',value))
        self.top_artist=QLabel(hidden)
        activity,activity_box=section('Часто прослушиваемые песни','')
        self.artist_stats=QLabel();self.artist_stats.setWordWrap(True);activity_box.addWidget(self.artist_stats)
        self.frequent_box=QVBoxLayout();self.frequent_box.setSpacing(8);activity_box.addLayout(self.frequent_box);grid.addWidget(activity,1,0,1,2)
        self.frequent_signature=None
        self.profile_dialog.finished.connect(lambda _:self.maybe_tour())

    def finish_identity_profile(self):
        self.profile_email.setText(self.profile.get('email') or ('Telegram · вход подтверждён' if self.profile.get('provider')=='telegram' else 'Локальный профиль'))

    def refresh_profile(self):
        super().refresh_profile()
        if not hasattr(self,'profile_heading'):return
        self.profile_heading.setText(self.profile.get('name','Слушатель'))
        provider={'telegram':'Telegram','google':'Google'}.get(self.profile.get('provider'),'На этом компьютере')
        self.profile_identity.setText(provider+'  ·  PULSE '+str(self.profile.get('id',''))[:8].upper())
        self.favorites_metric.setText(str(len(self.favorites))+'\nЛюбимых треков')
        counts=self.stats.get('track_plays',{})
        history=self.stats.get('history',[])
        rows=sorted((row for row in history if counts.get(row['id'],0)>0),key=lambda row:-counts[row['id']])[:5]
        signature=[(row['id'],counts.get(row['id'],0)) for row in rows]
        if signature!=self.frequent_signature:
            self.frequent_signature=signature
            while self.frequent_box.count():
                item=self.frequent_box.takeAt(0)
                if item.widget():item.widget().deleteLater()
            for row in rows:
                plays=counts.get(row['id'],0);caption=row['title']+'  ·  '+row['artist']+(f'  ·  {plays} прослуш.' if plays else '')
                self.frequent_box.addWidget(self.button(caption,lambda checked=False,r=dict(row):self.play_profile_track(r)))
        self.artist_stats.setVisible(not bool(rows));self.artist_stats.setText('Здесь появятся песни, которые ты слушаешь чаще всего.')
        self.finish_identity_profile()

    def play_profile_track(self,row):
        self.wave_mode=False;self.wave_generation+=1;self.queue=[row];self.play_index(0)

    def import_yandex_likes(self):
        if not self.client:
            self.import_result.setText('Сначала подключи свой аккаунт Яндекса.');return
        if getattr(self,'likes_importing',False):return
        client=self.client;self.likes_importing=True;self.import_yandex.setEnabled(False);self.import_result.setText('Импортирую все любимые треки…')
        def work(signals):
            liked=client.users_likes_tracks(timeout=10);ids=[t.id for t in liked.tracks] if liked else [];rows=[]
            for offset in range(0,len(ids),100):
                if self.client is not client:raise RuntimeError('Account changed')
                rows.extend(self.track_data(track) for track in client.tracks(ids[offset:offset+100],timeout=10))
                signals.progress.emit(min(100,int((offset+100)*100/max(1,len(ids)))))
            return rows
        def done(rows):
            self.likes_importing=False;self.import_yandex.setEnabled(True)
            if self.client is not client:self.import_result.setText('Аккаунт сменился. Повтори импорт.');return
            before=len(self.favorites)
            for row in rows:self.favorites[row['id']]=row
            self.save_data('favorites.json',self.favorites);self.refresh_profile()
            self.import_result.setText(f'Готово: добавлено {len(self.favorites)-before}, всего из Яндекса {len(rows)}. Повторных записей нет.')
        job=self.task(work,done);job.likes_import=True

    def save_profile(self):
        name=self.name_edit.text().strip()
        if not name:self.profile_saved.setText('Введи имя');self.name_edit.setFocus();return
        self.profile.update(name=name,bio=self.bio_edit.text().strip());self.save_data('profile.json',self.profile)
        self.profile_nav.setToolTip(name+' · профиль');self.refresh_profile();self.profile_saved.setText('Изменения сохранены')

    def build_settings(self):
        super().build_settings();layout=self.settings_panel.layout()
        group=QWidget();form=QVBoxLayout(group);form.setContentsMargins(0,0,0,0);form.setSpacing(10)
        line=QHBoxLayout();line.addWidget(QLabel('Дымчатые панели'));line.addStretch();self.glass_value=QLabel();line.addWidget(self.glass_value);form.addLayout(line)
        self.glass_slider=QSlider(Qt.Orientation.Horizontal);self.glass_slider.setRange(25,85);self.glass_slider.setValue(self.preferences['glass']);form.addWidget(self.glass_slider)
        hint=QLabel('Слева — больше фона, справа — плотнее стекло');hint.setObjectName('muted');form.addWidget(hint);layout.insertWidget(1,group)
        self.glass_slider.valueChanged.connect(self.set_glass);self.glass_value.setText(str(self.preferences['glass'])+'%')

    def set_glass(self,value):
        self.preference('glass',value);glass.opacity=value/100;self.glass_value.setText(str(value)+'%');self.apply_glass()

    def apply_glass(self):
        alpha=int(self.preferences['glass']*2.55)
        css=f'''QWidget#rail,QWidget#searchBox,QWidget#hero,QWidget#dock{{background:rgba(19,19,24,{alpha});border:1px solid rgba(255,255,255,26);border-radius:18px;}}
QWidget#profileSection{{background:rgba(23,22,29,95);border:1px solid rgba(255,255,255,22);border-radius:17px;}}
QLabel#profileMetric{{background:rgba(31,29,38,135);border:1px solid rgba(255,255,255,20);border-radius:15px;padding:12px;font-size:15px;color:#e4deec;}}
QWidget#playbackNotice{{background:rgba(58,43,53,225);border:1px solid rgba(236,186,204,55);border-radius:12px;}}'''
        from skin import STYLE
        from library_ui import LIBRARY_STYLE
        self.setStyleSheet(STYLE+LIBRARY_STYLE+css)
        for page in self.content_host.findChildren(InAppPage):page.setStyleSheet(f'QWidget#inAppPage{{background:rgba(18,18,23,{min(220,alpha+22)});border:1px solid rgba(255,255,255,28);border-radius:20px;}}')
        self.root.update();self.wave_hero.update();self.tracks.viewport().update()
        for i in range(self.tracks.count()):
            widget=self.tracks.itemWidget(self.tracks.item(i))
            if widget:widget.update()

    def preference(self,key,value):
        self.preferences[key]=value;self.save_data('preferences.json',self.preferences)

    def remember_volume(self,value):
        if self.preferences['remember_volume']:self.preference('volume',value)

    def advance_finished(self):
        if not self.preferences['auto_next'] and self.media.mediaStatus()==QMediaPlayer.MediaStatus.EndOfMedia:
            self.want_playing=False;self.ending_handled=True;self.count_track(force=True);return
        super().advance_finished()

    def open_support(self):
        url=self.identity_config.get('telegram',{}).get('support_url','https://t.me/PulseMusicHelpBot?start=support')
        QDesktopServices.openUrl(QUrl(url))

    def show_home(self):
        super().show_home()
        if hasattr(self,'wave_hero') and self.wave_seeds:
            self.cover_loader.load(self.wave_seeds[0].get('cover'),self.wave_hero.art)

    def render(self,rows):
        super().render(rows)
        if hasattr(self,'content_host'):
            for page in self.content_host.findChildren(InAppPage,options=Qt.FindChildOption.FindDirectChildrenOnly):
                if page.isVisible():page.suppress_siblings()

    def show_playback_notice(self,text,connect=False):
        if not hasattr(self,'playback_notice'):return
        self.playback_message.setText(text);self.playback_connect.setVisible(connect);self.playback_notice.show()

    def play_index(self,index,resume=0,recovery=False):
        if not recovery and hasattr(self,'playback_notice'):self.playback_notice.hide()
        super().play_index(index,resume,recovery)
        version=self.play_version;QTimer.singleShot(35000,lambda:self.audio_load_timeout(version))
        if self.loading_audio and 0<=index<len(self.queue) and self.queue[index].get('source') in ('audius','soundcloud'):self.show_playback_notice('Подготавливаю полную запись…')

    def audio_load_timeout(self,version):
        if version!=self.play_version or not self.loading_audio:return
        self.play_version+=1;self.resolve_generation+=1;self.loading_audio=False;self.want_playing=False
        self.show_playback_notice('Источник слишком долго готовит запись. Попробуй другую версию трека или повтори запуск.')

    def state_changed(self,state):
        super().state_changed(state)
        if state==QMediaPlayer.PlaybackState.PlayingState and hasattr(self,'playback_notice'):self.playback_notice.hide()

    def playback_error(self,*args):
        if getattr(self.media,'mode','native')=='soundcloud':
            self.want_playing=False;self.loading_audio=False
            self.show_playback_notice('SoundCloud не смог запустить запись. Проверь доступ к сервису или попробуй другую версию трека.');return
        super().playback_error(*args)

    def job_failed(self,payload):
        name,job=payload
        if getattr(job,'likes_import',False):
            self.jobs.discard(job);self.likes_importing=False;self.import_yandex.setEnabled(True);self.import_result.setText('Импорт не завершён. Проверь подключение и повтори — любимые сохранены.');return
        if hasattr(job,'play_version') and job.play_version==self.play_version:
            source=self.queue[self.current].get('source') if 0<=self.current<len(self.queue) else ''
            self.show_playback_notice('Источник не отдал полную запись. Попробуй другой трек или проверь подключение.' if name=='TrackUnavailable' else 'Не удалось загрузить запись. Проверь доступ к музыкальному сервису.',source=='yandex' and not self.client)
        super().job_failed(payload)
