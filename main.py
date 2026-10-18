import base64
import ctypes
import json
import os
import sys
import threading
import random
import hashlib
import uuid
from pathlib import Path
from ctypes import wintypes

# Windows Media Foundation avoids the FFmpeg pause/seek/end deadlock on this build.
if sys.platform=='win32':os.environ.setdefault('QT_MEDIA_BACKEND','windows')

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QUrl, Qt, Signal, QEvent, QSize
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QSlider, QAbstractItemView, QMessageBox, QDialog, QCheckBox, QFileDialog, QListWidgetItem)
from yandex_music import Client
from shiboken6 import isValid
from skin import STYLE, DEFAULTS, VortexSurface, MetalButton
from library_ui import LIBRARY_STYLE, TrackList, TrackRow, CoverLoader, Artwork, ElidedLabel, TourOverlay
from pages import InAppPage

DATA = Path(os.environ.get('PULSE_DATA_DIR', os.environ.get('LOCALAPPDATA', str(Path.home())))) / 'PulseMusic-0.7.1'


def protect(raw, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buf = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    if decrypt:
        fn = ctypes.windll.crypt32.CryptUnprotectData
    else:
        fn = ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def save_json(path, value):
    DATA.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def clock(ms):
    seconds = max(0, int(ms) // 1000)
    return f'{seconds // 60}:{seconds % 60:02}'


class Signals(QObject):
    done = Signal(object, object)
    failed = Signal(object)
    code = Signal(object)
    progress = Signal(int)


class Job(QRunnable):
    def __init__(self, fn, done, failed):
        super().__init__()
        self.fn = fn
        self.signals = Signals()
        self.signals.done.connect(done)
        self.signals.failed.connect(failed)

    def run(self):
        try:
            self.signals.done.emit(self.fn(self.signals), self)
        except Exception as exc:
            # Never include raw API exception text: it can contain request credentials.
            self.signals.failed.emit((type(exc).__name__, self))


class BasePlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint,True)
        self.setWindowTitle('Pulse 0.15')
        self.resize(1280,820)
        self.setMinimumSize(940,640)
        self.pool=QThreadPool(self);self.pool.setMaxThreadCount(3)
        self.jobs=set();self.cancel=threading.Event();self.client=None
        self.rows=[];self.queue=[];self.current=-1
        self.search_version=self.play_version=self.auth_version=0
        self.auth_dialog=None;self.tour=None;self.view='favorites'
        self.favorites={};self.local_library={};self.profile={};self.theme=dict(DEFAULTS)
        for filename,attribute in [('favorites.json','favorites'),('library.json','local_library'),('profile.json','profile')]:
            try:
                value=json.loads((DATA/filename).read_text(encoding='utf-8'))
                if isinstance(value,dict):setattr(self,attribute,value)
            except (OSError,ValueError):pass
        try:
            saved=json.loads((DATA/'appearance.json').read_text(encoding='utf-8'))
            self.theme.update(hue=max(0,min(360,int(saved['hue']))),speed=max(0,min(3,float(saved['speed']))),
                complexity=max(1,min(5,int(saved['complexity']))),title=str(saved['title'])[:80],motion=bool(saved['motion']))
        except (OSError,ValueError,TypeError,KeyError):pass
        self.theme_timer=QTimer(self);self.theme_timer.setSingleShot(True);self.theme_timer.timeout.connect(self.persist_theme)
        self.audio=QAudioOutput(self);self.audio.setVolume(.65)
        from soundcloud_player import HybridMedia
        self.media=HybridMedia(self);self.media.setAudioOutput(self.audio)
        self.media.positionChanged.connect(self.position_changed)
        self.media.durationChanged.connect(lambda n:self.seek.setRange(0,n))
        self.media.playbackStateChanged.connect(self.state_changed)
        self.media.mediaStatusChanged.connect(self.media_status)
        self.media.errorOccurred.connect(lambda *_:self.status.setText('Не удалось воспроизвести трек. Проверь источник и повтори попытку.'))
        self.root=VortexSurface();self.root.gl.settings=self.theme;self.root.gl.extent=.98
        self.setCentralWidget(self.root)
        self.root.installEventFilter(self)
        self.cover_loader=CoverLoader(self)
        outer=QVBoxLayout(self.root);outer.setContentsMargins(8,8,8,8);outer.setSpacing(8)
        body=QHBoxLayout();body.setSpacing(10)
        rail=QWidget();rail.setObjectName('rail');rail.setFixedWidth(60)
        nav=QVBoxLayout(rail);nav.setContentsMargins(10,13,10,12);nav.setSpacing(15)
        self.home_nav=self.icon_button('home','Главная',self.show_home);nav.addWidget(self.home_nav)
        nav.addSpacing(12)
        self.search_nav=self.icon_button('search','Поиск музыки',self.open_search);nav.addWidget(self.search_nav)
        self.library_nav=self.icon_button('heart','Любимые треки',self.show_favorites);nav.addWidget(self.library_nav)
        self.favorites_nav=self.library_nav;self.favorites_nav.setCheckable(True)
        self.import_nav=self.icon_button('plus','Добавить музыку с компьютера',self.import_files);nav.addWidget(self.import_nav)
        nav.addStretch()
        nav.addWidget(self.icon_button('help','Краткое обучение',self.start_tour))
        self.settings_nav=self.icon_button('settings','Настройки оформления',self.toggle_settings);nav.addWidget(self.settings_nav)
        self.profile_nav=self.icon_button('user','Профиль и источники музыки',self.open_profile);nav.addWidget(self.profile_nav)
        body.addWidget(rail)
        self.content_host=QWidget();self.content_host.installEventFilter(self)
        content=QVBoxLayout(self.content_host);content.setContentsMargins(0,0,0,0);content.setSpacing(12)
        self.search_box=QWidget();self.search_box.setObjectName('searchBox')
        search=QHBoxLayout(self.search_box);search.setContentsMargins(13,5,8,5)
        self.query=QLineEdit();self.query.setPlaceholderText('Найти трек или исполнителя');self.query.returnPressed.connect(self.search)
        self.query.setStyleSheet('border:0;background:transparent;padding:9px;')
        search.addWidget(self.query,1);search.addWidget(self.button('Найти',self.search))
        search.addWidget(self.icon_button('close','Закрыть поиск',lambda:self.search_box.hide()))
        self.search_box.hide();content.addWidget(self.search_box)
        self.auth_box=QWidget();auth=QHBoxLayout(self.auth_box);auth.setContentsMargins(10,0,10,0)
        self.code_label=QLabel();self.code_label.setObjectName('code');self.code_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        auth.addWidget(self.code_label);auth.addWidget(QLabel('Код для страницы Яндекса'));auth.addStretch()
        auth.addWidget(self.button('Открыть страницу',self.open_auth));auth.addWidget(self.button('Отмена',self.cancel_auth))
        self.auth_url='';self.auth_box.hide();content.addWidget(self.auth_box)
        hero=QWidget();hero.setObjectName('hero');hero.setFixedHeight(184)
        hero_row=QHBoxLayout(hero);hero_row.setContentsMargins(20,18,24,18);hero_row.setSpacing(23)
        self.hero_art=Artwork(138,hero=True);hero_row.addWidget(self.hero_art)
        hero_text=QVBoxLayout();hero_text.setSpacing(5);hero_text.addStretch()
        self.heading=QLabel('Любимые');self.heading.setStyleSheet('font-size:32px;font-weight:700;letter-spacing:-.6px;')
        self.count_label=QLabel('0 треков');self.count_label.setObjectName('muted')
        hero_text.addWidget(self.heading);hero_text.addWidget(self.count_label);hero_text.addSpacing(10)
        hero_actions=QHBoxLayout()
        self.play_all=self.button('Играть все',self.play_all_tracks,primary=True);hero_actions.addWidget(self.play_all)
        hero_actions.addWidget(self.icon_button('search','Поиск музыки',self.open_search))
        hero_actions.addWidget(self.icon_button('queue','Очередь воспроизведения',self.show_queue));hero_actions.addStretch()
        hero_text.addLayout(hero_actions);hero_text.addStretch();hero_row.addLayout(hero_text,1)
        content.addWidget(hero)
        self.status=QLabel('Твои любимые треки будут здесь.');self.status.setObjectName('muted');self.status.setWordWrap(True)
        self.status.setStyleSheet('font-family:Segoe UI;font-size:13px;padding-left:7px;');content.addWidget(self.status)
        list_host=QWidget();list_layout=QVBoxLayout(list_host);list_layout.setContentsMargins(0,0,0,0)
        self.tracks=TrackList();list_layout.addWidget(self.tracks)
        self.empty=QWidget(self.tracks.viewport());empty_layout=QVBoxLayout(self.empty);empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter);empty_layout.setSpacing(10)
        empty_title=QLabel('Начни с любимого трека');empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title.setStyleSheet('font-size:19px;font-weight:600;color:#b6b6c0;')
        empty_hint=QLabel('Найди музыку или добавь файлы с компьютера.');empty_hint.setObjectName('muted');empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title);empty_layout.addWidget(empty_hint)
        empty_actions=QHBoxLayout();empty_actions.addStretch();empty_actions.addWidget(self.button('Найти музыку',self.open_search));empty_actions.addStretch()
        empty_layout.addLayout(empty_actions)
        self.tracks.viewport().installEventFilter(self)
        content.addWidget(list_host,1);body.addWidget(self.content_host,1);outer.addLayout(body,1)
        dock=QWidget();dock.setObjectName('dock');dock_layout=QVBoxLayout(dock);dock_layout.setContentsMargins(12,8,12,7);dock_layout.setSpacing(3)
        row=QHBoxLayout();row.setSpacing(10)
        self.dock_art=Artwork(44);row.addWidget(self.dock_art)
        text=QVBoxLayout();text.setSpacing(2)
        self.now=ElidedLabel('Пока ничего не играет');self.now.setFont(QFont('Segoe UI',10,QFont.Weight.DemiBold));self.now.setMaximumWidth(310)
        self.now_artist=ElidedLabel('Выбери трек');self.now_artist.setObjectName('muted');self.now_artist.setStyleSheet('font-size:10px;');self.now_artist.setMaximumWidth(310)
        text.addWidget(self.now);text.addWidget(self.now_artist);row.addLayout(text,1)
        self.current_favorite=self.icon_button('heart','В избранное',self.favorite_current);self.current_favorite.setCheckable(True);row.addWidget(self.current_favorite)
        row.addStretch(1)
        row.addWidget(self.icon_button('queue','Показать очередь',self.show_queue))
        row.addWidget(self.icon_button('previous','Предыдущий трек',lambda:self.step(-1)))
        self.play_button=self.icon_button('play','Воспроизведение / пауза',self.toggle);row.addWidget(self.play_button)
        row.addWidget(self.icon_button('next','Следующий трек',lambda:self.step(1)))
        self.shuffle_button=self.icon_button('shuffle','Перемешивать очередь',lambda:None);self.shuffle_button.setCheckable(True);row.addWidget(self.shuffle_button)
        row.addStretch(1)
        self.mute_button=self.icon_button('volume','Включить / выключить звук',self.toggle_mute);row.addWidget(self.mute_button)
        self.volume=QSlider(Qt.Orientation.Horizontal);self.volume.setRange(0,100);self.volume.setValue(65);self.volume.setFixedWidth(80)
        self.volume.valueChanged.connect(self.volume_changed);row.addWidget(self.volume)
        dock_layout.addLayout(row)
        timeline=QHBoxLayout();self.seek=QSlider(Qt.Orientation.Horizontal);self.seek.setRange(0,0)
        self.seek.sliderReleased.connect(lambda:self.media.setPosition(self.seek.value()));timeline.addWidget(self.seek,1)
        self.elapsed=QLabel('0:00 / 0:00');self.elapsed.setObjectName('muted');self.elapsed.setStyleSheet('font-size:12px;');self.elapsed.setMinimumWidth(80)
        timeline.addWidget(self.elapsed);dock_layout.addLayout(timeline);outer.addWidget(dock)
        self.build_settings()
        self.build_profile()
        self.setStyleSheet(STYLE+LIBRARY_STYLE)
        self.refresh_theme_labels()
        self.show_favorites()
        QShortcut(QKeySequence('Ctrl+F'),self,activated=self.open_search)
        QShortcut(QKeySequence(Qt.Key.Key_MediaTogglePlayPause),self,activated=self.toggle)
        QTimer.singleShot(100,lambda:self.restore())
        QTimer.singleShot(500,lambda:self.first_run())

    def button(self,text,callback,primary=False):
        button=MetalButton(text,primary=primary);button.clicked.connect(callback);return button

    def icon_button(self,icon,tooltip,callback,primary=False):
        button=MetalButton(icon=icon,primary=primary);button.setToolTip(tooltip);button.setAccessibleName(tooltip);button.clicked.connect(callback);return button

    def eventFilter(self,watched,event):
        if getattr(self,'closing',False) or event.type()!=QEvent.Type.Resize:return False
        if hasattr(self,'root') and watched==self.root and event.type()==QEvent.Type.Resize and self.tour:
            QTimer.singleShot(0,lambda:self.resize_tour())
        if hasattr(self,'tracks') and isValid(self.tracks) and watched==self.tracks.viewport():
            self.empty.setGeometry(self.tracks.viewport().rect())
        return super().eventFilter(watched,event)

    def resize_tour(self):
        if self.tour:
            self.tour.setGeometry(self.root.rect());self.tour.update_step()

    def open_search(self):
        self.search_box.show();self.query.setFocus()

    def show_home(self):
        self.show_favorites()

    def show_local(self):
        self.search_version+=1;self.view='local';self.render(list(self.local_library.values()))
        self.status.setText('Музыка с компьютера. Кнопка «+» слева добавляет файлы.')

    def play_all_tracks(self):
        if self.rows:self.start_row(0)
        else:self.open_search()

    def activate_track(self,index):
        self.tracks.setCurrentRow(index);self.start_row(index)

    def import_files(self):
        filenames,_=QFileDialog.getOpenFileNames(self,'Добавить музыку','','Музыка (*.mp3 *.flac *.wav *.ogg *.m4a *.aac)')
        if not filenames:return
        for filename in filenames:
            path=Path(filename).resolve()
            key='local:'+hashlib.sha256(str(path).lower().encode()).hexdigest()[:24]
            self.local_library[key]={'id':key,'title':path.stem,'artist':'На этом компьютере','duration':0,'source':'local','path':str(path)}
        try:save_json(DATA/'library.json',self.local_library)
        except OSError:self.status.setText('Не удалось сохранить список файлов.')
        self.show_local()

    def build_profile(self):
        self.profile_dialog=InAppPage(self.content_host);self.profile_dialog.setWindowTitle('Профиль Pulse');self.profile_dialog.setMinimumWidth(430)
        box=QVBoxLayout(self.profile_dialog.body);box.setContentsMargins(25,24,25,24);box.setSpacing(15)
        heading=QLabel('Твой профиль Pulse');heading.setStyleSheet('font-size:24px;font-weight:600;');box.addWidget(heading)
        hint=QLabel('Имя, избранное и настройки хранятся на этом компьютере. Сервер и пароль не нужны.');hint.setWordWrap(True);hint.setObjectName('muted');box.addWidget(hint)
        self.name_edit=QLineEdit(self.profile.get('name',''));self.name_edit.setPlaceholderText('Как тебя называть?');self.name_edit.setMaxLength(40);box.addWidget(self.name_edit)
        box.addWidget(self.button('Сохранить профиль',self.save_profile,primary=True))
        sources=QLabel('Источники музыки');sources.setStyleSheet('font-size:16px;font-weight:600;margin-top:16px;');box.addWidget(sources)
        self.account=QLabel('Яндекс Музыка · не подключена');self.account.setObjectName('muted');box.addWidget(self.account)
        self.login=self.button('Подключить Яндекс Музыку',self.connect_yandex,primary=True);box.addWidget(self.login)
        self.logout=self.button('Отключить Яндекс',self.sign_out);self.logout.hide();box.addWidget(self.logout)
        source_hint=QLabel('Для Яндекс Музыки нужен доступ твоего аккаунта. Файлы с компьютера можно слушать без подключения сервисов.');source_hint.setWordWrap(True);source_hint.setObjectName('muted');box.addWidget(source_hint)
        box.addWidget(self.button('Закрыть',self.profile_dialog.reject))
        self.profile_dialog.finished.connect(lambda _:self.maybe_tour())

    def connect_yandex(self):
        self.profile_dialog.blockSignals(True);self.profile_dialog.close();self.profile_dialog.blockSignals(False);self.sign_in()

    def open_profile(self):
        self.profile_dialog.show();self.profile_dialog.raise_();self.profile_dialog.activateWindow()

    def save_profile(self):
        name=self.name_edit.text().strip()
        if not name:self.name_edit.setFocus();self.name_edit.setPlaceholderText('Введи имя для профиля');return
        self.profile={'id':self.profile.get('id',str(uuid.uuid4())),'name':name}
        try:save_json(DATA/'profile.json',self.profile)
        except OSError:self.status.setText('Не удалось сохранить профиль.');return
        self.profile_nav.setToolTip(name+' · профиль и источники')
        self.profile_dialog.accept()

    def first_run(self):
        if '--smoke-test' in sys.argv or os.environ.get('PULSE_TEST_MODE')=='1':return
        if not self.profile:self.open_profile()
        else:self.maybe_tour()

    def maybe_tour(self):
        if getattr(self,'closing',False):return
        if not (DATA/'onboarding-v04.json').exists() and not self.auth_dialog:self.start_tour()

    def start_tour(self):
        if self.tour:self.tour.deleteLater()
        steps=[
            (self.favorites_nav,'Любимые треки','Нажми сердечко у трека — он появится здесь. Избранное хранится на этом компьютере.',self.show_favorites),
            (self.search_nav,'Поиск музыки','Здесь открывается поиск по Яндекс Музыке. Подключить аккаунт можно в профиле внизу слева.',self.open_search),
            (self.play_button,'Музыка всегда под рукой','Внизу — пауза, предыдущий и следующий трек, очередь и громкость. Нажатие на строку трека начинает воспроизведение.',None),
            (self.settings_nav,'Настрой под себя','Эта кнопка открывает оформление: оттенок, скорость, сложность и отключение фона. Настройки скрыты, пока ты их не откроешь.',None)]
        def done():
            try:save_json(DATA/'onboarding-v04.json',{'completed':True})
            except OSError:pass
            self.tour=None
        self.tour=TourOverlay(self.root,steps,done)

    def toggle_settings(self):
        if self.settings_dialog.isVisible():self.settings_dialog.close()
        else:self.settings_dialog.show();self.settings_dialog.raise_();self.settings_dialog.activateWindow()


    def build_settings(self):
        self.settings_dialog=InAppPage(self.content_host)
        self.settings_dialog.setWindowTitle('Оформление Pulse')
        panel=QVBoxLayout(self.settings_dialog.body)
        panel.setContentsMargins(0,0,0,0)
        self.settings_panel = QWidget()
        self.settings_panel.setObjectName('panel')
        self.settings_panel.setMinimumWidth(330)
        settings_layout = QVBoxLayout(self.settings_panel)
        settings_layout.setContentsMargins(20,20,20,20)
        settings_layout.setSpacing(17)
        panel_top = QHBoxLayout()
        panel_title = QLabel('Внешний вид')
        panel_title.setStyleSheet('font-size:15px;font-weight:600;')
        panel_top.addWidget(panel_title)
        panel_top.addStretch()
        panel_top.addWidget(self.icon_button('close','Скрыть настройки',self.toggle_settings))
        settings_layout.addLayout(panel_top)
        panel_caption = QLabel('LIQUID METAL VORTEX')
        panel_caption.setStyleSheet('font-size:9px;color:#87818a;letter-spacing:1.8px;')
        settings_layout.addWidget(panel_caption)
        self.theme_controls = {}
        self.theme_values = {}
        for key,label,maximum,factor in [('hue','Оттенок',360,1),('speed','Скорость',30,10),('complexity','Сложность',5,1)]:
            row = QHBoxLayout()
            name = QLabel(label)
            name.setObjectName('muted')
            row.addWidget(name)
            row.addStretch()
            value = QLabel()
            row.addWidget(value)
            settings_layout.addLayout(row)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(1 if key=='complexity' else 0,maximum)
            slider.setValue(round(self.theme[key]*factor))
            slider.valueChanged.connect(lambda n,k=key,f=factor:self.change_theme(k,n/f))
            self.theme_controls[key] = slider
            self.theme_values[key] = value
            settings_layout.addWidget(slider)
        title_caption = QLabel('Заголовок')
        title_caption.setObjectName('muted')
        settings_layout.addWidget(title_caption)
        self.title_edit = QLineEdit(self.theme['title'])
        self.title_edit.setMaxLength(80)
        self.title_edit.setStyleSheet('font-size:12px;border-radius:12px;padding:10px;')
        self.title_edit.textChanged.connect(lambda text:self.change_theme('title',text))
        settings_layout.addWidget(self.title_edit)
        self.motion_check = QCheckBox('Анимация фона')
        self.motion_check.setChecked(self.theme['motion'])
        self.motion_check.toggled.connect(lambda enabled:self.change_theme('motion',enabled))
        settings_layout.addWidget(self.motion_check)
        hint = QLabel('Вихрь едва заметно следует за курсором. Настройки сохраняются автоматически.')
        hint.setWordWrap(True)
        hint.setObjectName('muted')
        hint.setStyleSheet('font-size:11px;')
        settings_layout.addWidget(hint)
        settings_layout.addStretch(1)
        settings_layout.addWidget(self.button('Сбросить настройки',self.reset_theme))
        panel.addWidget(self.settings_panel)

    def refresh_theme_labels(self):
        self.theme_values['hue'].setText(f"{int(self.theme['hue'])}°")
        self.theme_values['speed'].setText(f"{self.theme['speed']:.1f}×")
        self.theme_values['complexity'].setText(str(int(self.theme['complexity'])))

    def change_theme(self,key,value):
        self.theme[key] = value
        self.root.gl.settings = self.theme
        self.root.gl.update()
        self.setWindowTitle('Pulse 0.15 · '+self.theme['title'])
        self.refresh_theme_labels()
        self.theme_timer.start(350)

    def persist_theme(self):
        try:
            save_json(DATA/'appearance.json',self.theme)
        except OSError:
            self.status.setText('Не удалось сохранить настройки внешнего вида.')

    def reset_theme(self):
        self.theme.update(DEFAULTS)
        for key,slider in self.theme_controls.items():
            slider.setValue(round(self.theme[key]*(10 if key=='speed' else 1)))
        self.title_edit.setText(self.theme['title'])
        self.motion_check.setChecked(self.theme['motion'])
        self.change_theme('hue',self.theme['hue'])

    def volume_changed(self,value):
        self.audio.setVolume(value/100)
        self.audio.setMuted(False)
        self.mute_button.setGlyph('mute' if value==0 else 'volume')

    def toggle_mute(self):
        self.audio.setMuted(not self.audio.isMuted())
        self.mute_button.setGlyph('mute' if self.audio.isMuted() or self.volume.value()==0 else 'volume')

    def show_queue(self):
        self.search_version += 1
        self.view = 'queue'
        self.render(list(self.queue))
        self.status.setText(f'Очередь воспроизведения: {len(self.queue)} треков.')

    def favorite_current(self):
        if 0<=self.current<len(self.queue):
            row = self.queue[self.current]
            if row['id'] in self.favorites:
                del self.favorites[row['id']]
            else:
                self.favorites[row['id']] = row.copy()
            save_json(DATA/'favorites.json',self.favorites)
            self.current_favorite.setChecked(row['id'] in self.favorites)
            if self.view=='favorites':self.show_favorites()
            else:self.render(self.rows)
        else:
            self.current_favorite.setChecked(False)
            self.status.setText('Сначала выбери трек для воспроизведения.')


    def task(self, fn, callback):
        job = Job(fn, self.job_done, self.job_failed)
        job.callback = callback
        self.jobs.add(job)
        self.pool.start(job)
        return job

    def job_done(self, result, job):
        self.jobs.discard(job)
        job.callback(result)

    def job_failed(self, payload):
        name, job = payload
        self.jobs.discard(job)
        if getattr(job, 'auth', False):
            if job.auth_version != self.auth_version:
                return
            self.login.setEnabled(True)
            self.code_label.setText('Запроси новый код')
            if self.auth_dialog:
                self.auth_hint.setText('Вход не завершён. Закрой это окно и нажми «Войти через Яндекс» ещё раз.')
                self.auth_open_button.setEnabled(False)
        if self.cancel.is_set() and name == 'DeviceAuthError':
            return
        messages = {'UnauthorizedError': 'Сессия истекла. Войди в Яндекс заново.',
                    'NetworkError': 'Нет связи с Яндексом. Проверь интернет и повтори.',
                    'TimedOutError': 'Яндекс не ответил вовремя. Повтори попытку.',
                    'DeviceAuthError': 'Вход не завершён или код истёк. Попробуй снова.'}
        self.status.setText(messages.get(name, f'Не удалось выполнить действие ({name}). Попробуй снова.'))

    def restore(self):
        path = DATA / 'session.bin'
        if path.exists():
            try:
                token = protect(path.read_bytes(), decrypt=True).decode()
            except Exception:
                self.status.setText('Не удалось восстановить вход. Войди через Яндекс ещё раз.')
                return
            self.status.setText('Подключаю Яндекс Музыку…')
            version = self.auth_version
            self.task(lambda _: Client(token).init(), lambda c: self.connected(c) if version == self.auth_version else None)

    def sign_in(self):
        self.cancel = threading.Event()
        cancel = self.cancel
        self.auth_version += 1
        version = self.auth_version
        self.login.setEnabled(False)
        self.status.setText('Получаю код входа…')
        def work(signals):
            client = Client()
            token = client.device_auth(on_code=signals.code.emit, should_cancel=cancel.is_set,
                                       timeout=300, device_name='Pulse Music')
            client.init()
            return client, token
        def finished(result):
            if version != self.auth_version:
                return
            client, token = result
            DATA.mkdir(parents=True, exist_ok=True)
            try:
                path = DATA / 'session.bin'
                path.write_bytes(protect(token.access_token.encode()))
            except OSError:
                self.status.setText('Вход выполнен, но сохранить сессию не удалось.')
            self.connected(client)
        job = Job(work, self.job_done, self.job_failed)
        job.callback = finished
        job.auth = True
        job.auth_version = version
        job.signals.code.connect(lambda code: self.show_code(code) if version == self.auth_version else None)
        self.jobs.add(job)
        self.pool.start(job)

    def show_code(self, code):
        self.code_label.setText(code.user_code)
        self.auth_url = code.verification_url
        self.auth_box.show()
        self.status.setText('Код готов. Скопируй его и открой страницу Яндекса кнопкой в окне входа.')
        self.close_auth_dialog()
        dialog = InAppPage(self.content_host)
        self.auth_dialog = dialog
        dialog.setWindowTitle('Вход в Яндекс Музыку · Pulse')
        dialog.setMinimumWidth(500)
        box = QVBoxLayout(dialog.body)
        box.setContentsMargins(28, 24, 28, 24)
        box.setSpacing(18)
        heading = QLabel('Код для входа в Яндекс')
        heading.setFont(QFont('Segoe UI', 20, QFont.Weight.Bold))
        box.addWidget(heading)
        large_code = QLabel(str(code.user_code))
        large_code.setStyleSheet('font-size:42px;font-weight:700;color:#c7b0ff;padding:16px;')
        large_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        large_code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(large_code)
        self.auth_hint = QLabel('Нажми кнопку ниже, затем вставь код на странице Яндекса.\nКод действует 5 минут. После подтверждения вернись в плеер.')
        self.auth_hint.setWordWrap(True)
        box.addWidget(self.auth_hint)
        def copy_and_open():
            QApplication.clipboard().setText(str(code.user_code))
            self.open_auth()
            self.auth_hint.setText('Код скопирован. На странице Яндекса нажми Ctrl+V и подтверди вход.\nПосле подтверждения плеер подключится автоматически.')
        self.auth_open_button = self.button('Скопировать код и открыть Яндекс', copy_and_open, primary=True)
        box.addWidget(self.auth_open_button)
        box.addWidget(self.button('Отмена', dialog.reject))
        dialog.rejected.connect(self.cancel_auth)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def close_auth_dialog(self):
        if self.auth_dialog:
            self.auth_dialog.blockSignals(True)
            self.auth_dialog.close()
            self.auth_dialog.deleteLater()
            self.auth_dialog = None

    def open_auth(self):
        url = QUrl(self.auth_url)
        if url.scheme() == 'https' and url.host() in ('oauth.yandex.ru', 'oauth.yandex.com', 'ya.ru', 'passport.yandex.ru'):
            QDesktopServices.openUrl(url)
        else:
            self.status.setText('Неожиданный адрес страницы входа. Вход остановлен.')
            self.cancel_auth()

    def cancel_auth(self):
        self.cancel.set()
        self.auth_version += 1
        self.close_auth_dialog()
        self.auth_box.hide()
        self.login.setEnabled(True)
        self.status.setText('Вход отменён. Можно попробовать снова.')

    def connected(self, client):
        self.close_auth_dialog()
        self.client = client
        self.login.setEnabled(True)
        self.login.hide()
        self.logout.show()
        self.auth_box.hide()
        account = client.me.account
        self.account.setText(f'Яндекс Музыка · {account.display_name or account.login}')
        self.status.setText('Подключено. Найди музыку или открой свои лайки Яндекса.')

    def sign_out(self):
        self.close_auth_dialog()
        self.cancel.set()
        self.auth_version += 1
        self.search_version += 1
        self.play_version += 1
        self.media.stop()
        self.media.setSource(QUrl())
        self.client = None
        self.queue, self.rows = [], []
        self.current = -1
        self.tracks.clear()
        self.now.setText('Пока ничего не играет')
        self.now_artist.setText('Выбери трек')
        self.dock_art.pixmap=None;self.dock_art.update()
        self.current_favorite.setChecked(False)
        (DATA / 'session.bin').unlink(missing_ok=True)
        self.account.setText('Яндекс Музыка · не подключена')
        self.login.show()
        self.logout.hide()
        self.status.setText('Выход выполнен. Избранное плеера сохранено на этом компьютере.')

    def require_client(self):
        if self.client is None:
            self.status.setText('Подключи Яндекс Музыку в профиле внизу слева.')
            self.open_profile()
            return False
        return True

    @staticmethod
    def track_data(track):
        return {'id': str(track.id), 'title': track.title or 'Без названия',
                'artist': ', '.join(a.name for a in track.artists),
                'duration': track.duration_ms or 0, 'source':'yandex',
                'cover':('https://'+track.cover_uri.replace('%%','100x100')) if getattr(track,'cover_uri',None) else None}

    def search(self):
        query = self.query.text().strip()
        if not query or not self.require_client():
            return
        self.search_version += 1
        version = self.search_version
        client = self.client
        self.status.setText('Ищу треки…')
        def work(_):
            result = client.search(query, type_='track')
            return [self.track_data(t) for t in (result.tracks.results if result.tracks else [])]
        def done(rows):
            if version == self.search_version:
                self.view = 'search'
                self.render(rows)
                self.status.setText(f'Найдено: {len(rows)}. Нажми на трек, чтобы включить его.')
        self.task(work, done)

    def load_likes(self):
        if not self.require_client():
            return
        self.search_version += 1
        version = self.search_version
        client = self.client
        self.status.setText('Загружаю до 100 последних лайков Яндекса…')
        def work(_):
            liked = client.users_likes_tracks()
            ids = [t.id for t in liked.tracks[:100]] if liked else []
            return [self.track_data(t) for t in client.tracks(ids)] if ids else []
        def done(rows):
            if version == self.search_version:
                self.view = 'likes'
                self.render(rows)
                self.status.setText(f'Мои лайки Яндекса: {len(rows)}. Показано до 100 последних треков.')
        self.task(work, done)

    def render(self, rows):
        self.rows=rows
        self.tracks.clear()
        for i,row in enumerate(rows):
            item=QListWidgetItem(self.tracks)
            item.setSizeHint(QSize(200,70))
            widget=TrackRow(i,row,row['id'] in self.favorites,self.cover_loader)
            widget.activated.connect(self.activate_track)
            widget.favorite.connect(self.favorite)
            self.tracks.setItemWidget(item,widget)
            if 0<=self.current<len(self.queue) and row['id']==self.queue[self.current]['id']:
                self.tracks.setCurrentRow(i)
        self.heading.setText({'favorites':'Любимые','search':'Результаты поиска','queue':'Очередь','local':'Моя музыка'}.get(self.view,'Моя музыка'))
        self.count_label.setText(f'{len(rows)} треков')
        self.favorites_nav.setChecked(self.view=='favorites')
        self.play_all.setEnabled(bool(rows))
        self.empty.setGeometry(self.tracks.viewport().rect())
        self.empty.setVisible(not rows)
        self.empty.raise_()

    def show_favorites(self):
        self.search_version += 1
        self.view = 'favorites'
        self.render(list(self.favorites.values()))
        self.status.setText('Любимые треки' if self.rows else 'Нажми сердечко у трека, чтобы добавить его сюда.')

    def favorite(self, index):
        row = self.rows[index]
        if row['id'] in self.favorites:
            del self.favorites[row['id']]
        else:
            self.favorites[row['id']] = row.copy()
        if 0 <= self.current < len(self.queue):
            self.current_favorite.setChecked(self.queue[self.current]['id'] in self.favorites)
        try:
            save_json(DATA / 'favorites.json', self.favorites)
        except OSError:
            self.status.setText('Не удалось сохранить избранное на диск.')
        if self.view == 'favorites':
            self.show_favorites()
        else:
            self.render(self.rows)

    def start_row(self, index):
        if not 0<=index<len(self.rows):return
        if self.rows[index].get('source')!='local' and not self.require_client():
            return
        self.queue = list(self.rows)
        self.play_index(index)

    def play_index(self, index):
        if not 0<=index<len(self.queue):return
        row=self.queue[index]
        if row.get('source')!='local' and not self.require_client():return
        self.current=index
        self.play_version += 1
        version = self.play_version
        client = self.client
        self.media.stop()
        self.now.setText(row['title'])
        self.now_artist.setText(row['artist'])
        self.dock_art.pixmap=None
        self.dock_art.update()
        self.cover_loader.load(row.get('cover'),self.dock_art)
        self.current_favorite.setChecked(row['id'] in self.favorites)
        self.status.setText('Подключаю трек…')
        if row.get('source')=='local':
            if not Path(row['path']).is_file():
                self.status.setText('Файл перемещён или удалён. Добавь его заново.');return
            self.media.setSource(QUrl.fromLocalFile(row['path']))
            self.media.play()
            self.status.setText('Музыка с компьютера')
            return
        def work(_):
            tracks = client.tracks([row['id']])
            if not tracks or not tracks[0].available:
                raise ValueError('unavailable')
            choices = tracks[0].get_download_info()
            choices = sorted([c for c in choices if c.codec == 'mp3'], key=lambda c: c.bitrate_in_kbps or 0, reverse=True)
            if not choices:
                raise ValueError('no_stream')
            return choices[0].get_direct_link()
        def done(url):
            if version != self.play_version:
                return
            self.media.setSource(QUrl(url))
            self.media.play()
            self.status.setText(f'Яндекс Музыка · трек {index + 1} из {len(self.queue)} в очереди')
        self.task(work, done)

    def toggle(self):
        if self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media.pause()
        elif self.media.source().isEmpty():
            row = self.tracks.currentRow()
            if row >= 0:
                self.start_row(row)
        else:
            self.media.play()

    def step(self, offset):
        if offset < 0 and self.media.position() > 3000:
            self.media.setPosition(0)
        elif offset > 0 and self.shuffle_button.isChecked() and len(self.queue) > 1:
            self.play_index(random.choice([i for i in range(len(self.queue)) if i != self.current]))
        else:
            self.play_index(self.current + offset)

    def position_changed(self, position):
        if not self.seek.isSliderDown():
            self.seek.setValue(position)
        self.elapsed.setText(f'{clock(position)} / {clock(self.media.duration())}')

    def state_changed(self, state):
        self.play_button.setGlyph('pause' if state == QMediaPlayer.PlaybackState.PlayingState else 'play')

    def media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.shuffle_button.isChecked() or self.current + 1 < len(self.queue):
                self.step(1)
            else:
                self.status.setText('Очередь закончилась.')

    def closeEvent(self, event):
        self.closing=True
        self.media.shutdown()
        self.root.removeEventFilter(self)
        self.tracks.viewport().removeEventFilter(self)
        if self.theme_timer.isActive():
            self.theme_timer.stop()
            self.persist_theme()
        self.cancel.set()
        self.media.stop()
        self.media.setSource(QUrl())
        event.accept()


from features import Features
from experience import Experience
from refinement import Refinement
from polish import Polish
from upgrades import Upgrades
from welcome import Welcome
from import_ui import ImportUI

class Player(Welcome,ImportUI,Upgrades,Polish,Refinement,Experience,Features,BasePlayer):
    def __init__(self):
        self.data_dir=DATA
        super().__init__()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName('Pulse')
    from windows_shell import prepare_application,apply_window_icon
    prepare_application(app)
    window = Player()
    window.show()
    apply_window_icon(window)
    if '--smoke-test' in sys.argv:
        def smoke_check():
            path=Path(sys.argv[sys.argv.index('--smoke-test')+1])
            report={'icon':not window.windowIcon().isNull(),'profile_embedded':not window.profile_dialog.isWindow(),
                'settings_embedded':not window.settings_dialog.isWindow(),'shader':bool(window.root.gl.program),
                'native_icons':len(getattr(window,'_shell_icons',[])),'background':window.backgrounds.data['effect'],
                'profile_present':bool(window.profile),'yandex_connected':window.client is not None,
                'saved_session':(DATA/'session.bin').exists(),'data_namespace':DATA.name}
            try:
                from identity import GoogleSignIn,TelegramSignIn
                report['identity_packaged']=bool(GoogleSignIn and TelegramSignIn)
                report['google_configured']=bool(window.identity_config.get('google',{}).get('client_id'))
                report['telegram_configured']=bool(window.identity_config.get('telegram',{}).get('server'))
            except Exception as exc:report['identity_packaged']=False;report['identity_error']=type(exc).__name__
            if '--smoke-registration' in sys.argv:
                window.open_registration();report['registration_locked']=not window.profile and not window.content_host.isEnabled() and not window.registration.close_button.isVisible()
            try:
                from yt_dlp.extractor.soundcloud import SoundcloudIE,SoundcloudSearchIE
                report['soundcloud_packaged']=bool(SoundcloudIE and SoundcloudSearchIE)
            except Exception as exc:report['soundcloud_packaged']=False;report['provider_error']=type(exc).__name__
            def finish(details=None):
                if details:
                    try:report['web']=json.loads(details)
                    except (ValueError,TypeError):report['web']={'error':'invalid report'}
                window.grab().save(str(path));path.with_suffix('.json').write_text(json.dumps(report),encoding='utf-8')
                window.close();app.quit()
            if window.backgrounds.web:
                view=window.backgrounds.web
                report['web_errors']=list(view.page().errors)
                view.page().runJavaScript("JSON.stringify({ready:!!window.setBackground,canvases:document.querySelectorAll('canvas').length,webgl:!!document.querySelector('canvas')?.getContext('webgl2'),errors:window.effectErrors})",finish)
            else:finish()
        QTimer.singleShot(2200,smoke_check)
    sys.exit(app.exec())
