"""Mandatory local onboarding and public metadata discovery."""
import os,sys,random,json,uuid
from pathlib import Path
from PySide6.QtCore import Qt,QEvent,QTimer,QRectF
from PySide6.QtGui import QPainterPath,QRegion,QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget,QLabel,QApplication
from yandex_music import Client
from pages import InAppPage
from library_ui import TourOverlay

class RequiredProfile(InAppPage):
    def __init__(self,parent,player):
        self.player=player
        super().__init__(parent,'Добро пожаловать в Pulse')
    def show(self):
        locked=not bool(self.player.profile)
        self.back_button.setVisible(not locked);self.close_button.setVisible(not locked)
        super().show();QTimer.singleShot(0,lambda:self.place())
    def place(self):
        self.setGeometry(8,50,max(1,self.parentWidget().width()-16),max(1,self.parentWidget().height()-58))
    def reject(self):
        if self.player.profile:super().reject()
    def closeEvent(self,event):
        if not self.player.profile:event.ignore()
        else:super().closeEvent(event)

class Refinement:
    def __init__(self):
        self.catalog=Client();self.resolve_generation=0;self.wave_history={}
        self.identity_flow=None;self.identity_generation=0;self.identity_config={}
        try:self.identity_config=json.loads((Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'identity-config.json').read_text(encoding='utf8'))
        except (OSError,ValueError):pass
        super().__init__()
        try:
            self.wave_history=json.loads((self.data_dir/'wave-history.json').read_text(encoding='utf8'))
        except (OSError,ValueError):pass
        self.setWindowTitle('Pulse 0.15')
        self.root.installEventFilter(self);self.installEventFilter(self)
        QTimer.singleShot(0,lambda:self.round_window())

    def registration_page(self):
        return RequiredProfile(self.root,self)

    def build_registration(self):
        super().build_registration()
        layout=self.register_button.parentWidget().layout()
        self.identity_buttons=[]
        for provider,caption in [('google','Войти через Google'),('telegram','Войти через Telegram')]:
            button=self.button(caption,lambda checked=False,p=provider:self.begin_identity(p))
            layout.addWidget(button);self.identity_buttons.append(button)
        self.identity_cancel=self.button('Отменить вход',self.cancel_identity);layout.addWidget(self.identity_cancel);self.identity_cancel.hide()

    def cancel_identity(self):
        self.identity_generation+=1
        if self.identity_flow:self.identity_flow.cancelled=True
        self.identity_flow=None
        for button in self.identity_buttons:button.setEnabled(True)
        self.register_button.setEnabled(True);self.identity_cancel.hide();self.register_error.clear()

    def begin_identity(self,provider):
        from identity import GoogleSignIn,TelegramSignIn
        self.cancel_identity();generation=self.identity_generation;config=self.identity_config.get(provider)
        if not config:self.register_error.setText('Этот способ входа пока не настроен.');return
        try:flow=GoogleSignIn(config) if provider=='google' else TelegramSignIn(config)
        except Exception:self.register_error.setText('Не удалось начать вход. Попробуй ещё раз.');return
        self.identity_flow=flow;self.register_button.setEnabled(False)
        for button in self.identity_buttons:button.setEnabled(False)
        self.identity_cancel.show();self.register_error.setText('Подтверди вход в открывшемся сервисе.')
        def done(identity):
            if generation!=self.identity_generation or getattr(self,'closing',False):return
            self.cancel_identity()
            if hasattr(self,'profile_for_identity'):self.profile=self.profile_for_identity(identity)
            else:self.profile.update(id=self.profile.get('id',str(uuid.uuid4())),name=identity['name'],email=identity.get('email',''),provider=identity['provider'],provider_id=identity['provider_id'])
            self.save_data('profile.json',self.profile);self.name_edit.setText(self.profile['name']);self.profile_email.setText(self.profile.get('email') or 'Telegram · профиль подтверждён')
            if hasattr(self,'bio_edit'):self.bio_edit.setText(self.profile.get('bio',''))
            self.profile_nav.setToolTip(self.profile['name']+' · профиль');self.registration.accept();self.set_registration_gate(False);self.maybe_tour()
        def launch(url):
            if generation!=self.identity_generation:return
            if provider=='telegram':self.register_error.setText('В боте подтверди запрос '+flow.challenge['id'][:8].upper()+'.')
            if not QDesktopServices.openUrl(QUrl(url)):
                self.cancel_identity();self.register_error.setText('Не удалось открыть страницу входа.');return
            job=self.task(lambda _:flow.wait(),done);job.identity_job=True;job.identity_generation=generation
        if provider=='google':launch(flow.url)
        else:
            job=self.task(lambda _:flow.begin(),launch);job.identity_job=True;job.identity_generation=generation

    def open_registration(self):
        super().open_registration()
        self.set_registration_gate(not bool(self.profile))

    def set_registration_gate(self,locked):
        for widget in (self.content_host,self.favorites_nav.parentWidget(),self.seek.parentWidget()):widget.setEnabled(not locked)
        self.registration.setEnabled(True);self.registration.raise_()

    def register_local(self):
        super().register_local()
        if self.profile:self.set_registration_gate(False)

    def maybe_tour(self):
        if getattr(self,'closing',False) or not self.profile:return
        if not (self.data_dir/'onboarding-v08.json').exists() and not self.auth_dialog:self.start_tour()

    def start_tour(self):
        if not self.profile:return
        if self.tour:self.tour.deleteLater()
        steps=[
            (self.search_nav,'Найди музыку','Один поиск по всем доступным источникам. Карточка исполнителя открывает его каталог.',self.open_search),
            (self.favorites_nav,'Сохраняй любимое','Сердечко у трека добавляет его в любимые. Любимые сохраняются на этом компьютере.',self.show_favorites),
            (self.play_button,'Управляй музыкой','Здесь пауза и переключение треков. Нажми на обложку, чтобы открыть трек и текст. ПКМ по треку запускает волну.',None),
            (self.settings_nav,'Выбери свой фон','Здесь фон, цвет и движение. Тонкая настройка раскрывает дополнительные параметры; экономный режим снижает нагрузку.',self.toggle_settings),
            (self.import_nav,'Свои треки','Кнопка плюс добавляет аудиофайлы с компьютера. Они доступны без музыкального аккаунта и интернета.',None),
            (self.support_nav,'Поддержка','Здесь бот поддержки. Выбери проблему, опиши её и приложи фото или видео. Ответ придёт в тот же чат.',None),
            (self.profile_nav,'Твой профиль','Здесь имя, фото, описание и статистика. Ниже — источники музыки и часто прослушиваемые песни.',self.open_profile),
            (self.import_yandex,'Больше с Яндексом','Подключи свой аккаунт Яндекс Музыки для полного доступного тебе каталога и персональных рекомендаций. Кнопка «Импортировать треки» добавляет все твои лайки в любимые Pulse без дубликатов.',None)]
        def done():
            self.save_data('onboarding-v08.json',{'completed':True});self.tour=None;self.hide_pages();self.show_home()
        self.tour=TourOverlay(self.root,steps,done)

    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Type.Resize,QEvent.Type.WindowStateChange):
            if watched==self:QTimer.singleShot(0,lambda:self.round_window())
            if watched==getattr(self,'root',None) and getattr(self,'registration',None):QTimer.singleShot(0,lambda:self.registration.place())
        return super().eventFilter(watched,event)

    def round_window(self):
        if self.isMaximized():self.clearMask();return
        path=QPainterPath();path.addRoundedRect(QRectF(self.rect()),10,10)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def show_home(self):
        super().show_home()
        if hasattr(self,'status'):self.status.clear()

    def merge_search(self,version,source,result,failed=False):
        super().merge_search(version,source,result,failed)
        if version!=self.search_version:return
        key=self.artist_key(self.query.text());cards=[];seen=set()
        for _,artists in self.search_results.values():
            for a in artists:
                aid=(a.get('source','yandex'),str(a['id']))
                if aid not in seen:seen.add(aid);cards.append(a)
        def rank(a):
            name=self.artist_key(a['name'])
            return (0 if name==key else 1 if name.startswith(key) else 2 if key in name else 3,len(name))
        cards.sort(key=rank);self.show_artists(cards)

    def open_artist(self,artist):
        self.hide_pages();self.artist_info=artist;self.search_version+=1;version=self.search_version
        self.view='artist';self.render([]);self.heading.setText(artist['name'])
        self.library_hero.setStyleSheet('QWidget#hero{background:rgba(25,23,32,140);border:1px solid rgba(255,255,255,30);border-radius:22px;}')
        self.library_hero.setFixedHeight(232);self.hero_art.setFixedSize(176,176);self.empty.hide()
        self.heading.setStyleSheet('font-size:38px;font-weight:800;letter-spacing:-1px;')
        self.hero_art.hero=False;self.hero_art.pixmap=None;self.cover_loader.load(artist.get('cover'),self.hero_art);self.hero_art.update()
        self.count_label.setText('ИСПОЛНИТЕЛЬ');self.status.setText('Загружаю каталог…')
        client=self.client or self.catalog;source=artist.get('source','yandex')
        def work(_):
            if source in ('soundcloud','audius'):return getattr(self,source).artist(artist)
            rows=[];seen=set();page=0
            while version==self.search_version and not getattr(self,'closing',False):
                data=client.artists_tracks(artist['id'],page=page,page_size=100,timeout=8)
                batch=[self.track_data(t) for t in data.tracks];fresh=[r for r in batch if r['id'] not in seen]
                rows+=fresh;seen.update(r['id'] for r in fresh);page+=1
                total=getattr(getattr(data,'pager',None),'total',0)
                if not fresh or (total and len(rows)>=total) or (not total and len(batch)<100):break
            return rows
        def done(rows):
            if version!=self.search_version:return
            self.render(rows);self.heading.setText(artist['name']);self.count_label.setText(f'ИСПОЛНИТЕЛЬ · {len(rows)} треков')
            self.cover_loader.load(artist.get('cover'),self.hero_art);self.status.clear();self.more_artist.hide()
        job=self.task(work,done);job.artist_catalog=True;job.catalog_version=version

    def render(self,rows):
        if hasattr(self,'library_hero') and self.view!='artist':
            self.library_hero.setStyleSheet('');self.library_hero.setFixedHeight(184);self.hero_art.setFixedSize(138,138);self.heading.setStyleSheet('font-size:32px;font-weight:700;')
        super().render(rows)

    def play_index(self,index,resume=0,recovery=False):
        if 0<=index<len(self.queue) and self.queue[index].get('source','yandex')=='yandex' and not self.client:
            row=dict(self.queue[index]);self.resolve_generation+=1;generation=self.resolve_generation
            self.play_version+=1;self.current=index;self.media.stop();self.loading_audio=True;self.want_playing=True
            self.now.setText(row['title']);self.now_artist.setText(row['artist']);self.dock_art.pixmap=None;self.dock_art.update();self.cover_loader.load(row.get('cover'),self.dock_art)
            if self.now_page:self.now_page.update_row(row)
            self.status.setText('Ищу полную запись в открытых источниках…');self.show_playback_notice('Ищу полную запись в открытых источниках…')
            def work(_):
                from discovery import PublicDiscovery
                if not hasattr(self,'public_discovery'):self.public_discovery=PublicDiscovery({'soundcloud':self.soundcloud,'audius':self.audius})
                return self.public_discovery.match(row)
            def done(candidate):
                if generation!=self.resolve_generation:return
                self.loading_audio=False
                if candidate and index<len(self.queue) and self.queue[index]['id']==row['id']:
                    wanted=self.want_playing;self.queue[index]=candidate;self.play_index(index,resume,recovery);self.want_playing=wanted
                else:
                    self.want_playing=False
                    message='Совпадающая полная запись в открытых источниках не найдена. Попробуй другую версию трека в поиске.'
                    self.status.setText(message);self.show_playback_notice(message)
            self.task(work,done);QTimer.singleShot(15000,lambda:self.resolve_timeout(generation));return
        self.resolve_generation+=1
        super().play_index(index,resume,recovery)

    def resolve_timeout(self,generation):
        if generation!=self.resolve_generation or not self.loading_audio:return
        self.resolve_generation+=1;self.loading_audio=False;self.want_playing=False
        self.show_playback_notice('Открытые источники не ответили вовремя. Проверь доступ к SoundCloud и повтори запуск.')

    def remember_wave(self,row):
        super().remember_wave(row)
        self.wave_history[row['id']]=[r['id'] for r in self.queue[:80]]
        self.wave_history=dict(list(self.wave_history.items())[-30:]);self.save_data('wave-history.json',self.wave_history)

    def start_wave(self,seed=None):
        if seed:
            from features import Features
            Features.remember_wave(self,seed)
        if seed and seed.get('source','yandex') in ('yandex','local') and not self.client:
            self.start_public_wave(seed);return
        if seed and seed.get('source') in ('audius','soundcloud'):
            source=getattr(self,seed['source']);source.previous_wave=set(self.wave_history.get(seed['id'],[]))
        super().start_wave(seed)

    def start_public_wave(self,seed):
        from discovery import PublicDiscovery
        if not hasattr(self,'public_discovery'):self.public_discovery=PublicDiscovery({'soundcloud':self.soundcloud,'audius':self.audius})
        self.wave_generation+=1;generation=self.wave_generation;self.wave_loading=True
        self.show_playback_notice('Ищу волну в открытых источниках…');pending=[True]
        def done(result):
            if generation!=self.wave_generation:return
            pending[0]=False;self.wave_loading=False;rows,context=result
            if not rows:
                self.show_playback_notice('Открытая волна пока недоступна: сервисы не вернули похожие записи. Попробуй другой трек.');return
            previous=set(self.wave_history.get(seed['id'],[]));random.SystemRandom().shuffle(rows);rows.sort(key=lambda r:r['id'] in previous)
            if hasattr(self,'prepare_wave_rows'):rows=self.prepare_wave_rows(rows,context)
            if not rows:self.show_playback_notice('Для выбранных фильтров нет рекомендаций. Измени настройки волны.');return
            self.wave_mode=True;self.wave_context=context;self.wave_waiting=False;self.queue=rows;self.view='wave'
            self.render(rows);self.wave_title='Волна: '+seed['title'];self.heading.setText(self.wave_title);self.remember_wave(seed)
            self.play_index(0);self.next_wave_batch()
        job=self.task(lambda _:self.public_discovery.wave(seed),done);job.wave_job=True;job.wave_generation=generation
        def expired():
            if pending[0] and generation==self.wave_generation and self.wave_loading:
                self.wave_generation+=1;self.wave_loading=False;self.show_playback_notice('Открытые источники не ответили. Попробуй запустить волну ещё раз.')
        QTimer.singleShot(28000,expired)

    def job_failed(self,payload):
        _,job=payload
        if getattr(job,'identity_job',False):
            self.jobs.discard(job)
            if job.identity_generation==self.identity_generation:
                self.cancel_identity();self.register_error.setText('Вход не завершён. Попробуй ещё раз или создай локальный профиль.')
            return
        if getattr(job,'artist_catalog',False):
            self.jobs.discard(job)
            if job.catalog_version==self.search_version:self.status.setText('Каталог временно недоступен. Попробуй открыть исполнителя ещё раз.')
            return
        super().job_failed(payload)

    def closeEvent(self,event):
        self.resolve_generation+=1
        if self.identity_flow:self.identity_flow.cancelled=True
        super().closeEvent(event)
