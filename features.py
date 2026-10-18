import json,os,sys,time,random,uuid,re,unicodedata
from pathlib import Path
from datetime import datetime,timezone
from PySide6.QtCore import Qt,QTimer,QUrl,QEvent,QDir,QStandardPaths
from PySide6.QtGui import QIcon,QPixmap
from PySide6.QtWidgets import (QApplication,QWidget,QLabel,QVBoxLayout,QHBoxLayout,
    QComboBox,QMenu,QFileDialog,QTreeView,QFileSystemModel,QLineEdit,QAbstractItemView,QSlider,QCheckBox)
from PySide6.QtMultimedia import QMediaPlayer
from yandex_music import SessionEvent
from pages import InAppPage,ArtistCard,WaveHero,CollectionTile
from library_ui import Artwork
from services import AudioCache,SoundCloud


class Features:
    def __init__(self):
        self.wave_seeds=[]
        try:self.wave_seeds=json.loads((self.data_dir/'wave-seeds.json').read_text(encoding='utf8'))[:8]
        except (OSError,ValueError,TypeError):pass
        self.sleep_deadline=0;self.repeat_mode=0
        self.cache=AudioCache(self.data_dir);self.soundcloud=SoundCloud(self.data_dir)
        self.stats={'seconds':0.,'plays':0,'unique':[],'artists':{},'history':[],'sessions':0}
        try:self.stats.update(json.loads((self.data_dir/'listening.json').read_text(encoding='utf-8')))
        except (OSError,ValueError,TypeError):pass
        self.stats['sessions']+=1
        self.track_listened=0.;self.track_counted=False;self.last_position=0;self.last_wall=time.monotonic()
        self.wave_mode=False;self.wave_context=None;self.wave_loading=False;self.wave_generation=0;self.wave_waiting=False;self.wave_failures=0
        self.loading_audio=False;self.want_playing=False;self.has_progress=False;self.ending_handled=False
        self.resume_position=0;self.recoveries=0;self.last_advance=time.monotonic();self.last_stats_save=0
        self.suggestion_seq=0;self.artist_info=None;self.artist_page_index=0;self.extra_pages=[];self.home_reco_loading=False;self.home_rows=[]
        super().__init__()
        self.setWindowTitle('Pulse 0.15 · '+self.theme.get('title','Pulse'))
        asset=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'pulse.ico'
        if asset.exists():
            icon=QIcon(str(asset));self.setWindowIcon(icon);QApplication.instance().setWindowIcon(icon)
        self.library_hero=self.heading.parentWidget()
        self.home_panel=QWidget();home=QVBoxLayout(self.home_panel);home.setContentsMargins(0,0,0,0);home.setSpacing(13)
        self.wave_hero=WaveHero(self.cover_loader);self.wave_hero.played.connect(lambda:self.start_wave())
        self.wave_hero.seed_played.connect(self.start_wave)
        self.refresh_wave_seeds()
        home.addWidget(self.wave_hero)
        tiles=QHBoxLayout();history=CollectionTile('История','Недавно прослушанные треки','queue');history.activated.connect(self.show_history)
        favorites=CollectionTile('Любимые треки','Твоя коллекция музыки','heart');favorites.activated.connect(self.show_favorites)
        tiles.addWidget(history);tiles.addWidget(favorites);home.addLayout(tiles)
        heading=QLabel('Для вас');heading.setStyleSheet('font-size:22px;font-weight:600;');home.addWidget(heading)
        layout=self.content_host.layout();layout.insertWidget(layout.indexOf(self.library_hero),self.home_panel)
        self.suggestions=QWidget();self.suggestions_layout=QHBoxLayout(self.suggestions);self.suggestions_layout.setContentsMargins(0,0,0,0)
        layout.insertWidget(layout.indexOf(self.search_box)+1,self.suggestions);self.suggestions.hide()
        self.artist_shelf=QWidget();self.artist_layout=QHBoxLayout(self.artist_shelf);self.artist_layout.setContentsMargins(0,0,0,0)
        layout.insertWidget(layout.indexOf(self.library_hero)+1,self.artist_shelf);self.artist_shelf.hide()
        self.more_artist=self.button('Показать ещё треки',self.more_artist_tracks);layout.insertWidget(layout.count()-1,self.more_artist);self.more_artist.hide()
        self.suggest_timer=QTimer(self);self.suggest_timer.setSingleShot(True);self.suggest_timer.timeout.connect(self.fetch_suggestions)
        self.query.textEdited.connect(lambda _:self.suggest_timer.start(350))
        self.stats_timer=QTimer(self);self.stats_timer.timeout.connect(self.playback_tick);self.stats_timer.start(1000)
        self.media.errorOccurred.disconnect()
        self.media.errorOccurred.connect(self.playback_error)
        self.show_home()
        self.refresh_profile()

    def save_data(self,name,value):
        self.data_dir.mkdir(parents=True,exist_ok=True)
        path=self.data_dir/name;temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');temp.replace(path)

    def eventFilter(self,watched,event):
        if hasattr(self,'backgrounds') and event.type()==QEvent.Type.Resize and watched==self.root:self.backgrounds.resize()
        if hasattr(self,'backgrounds') and event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonRelease):self.backgrounds.pointer('pointerdown' if event.type()==QEvent.Type.MouseButtonPress else 'pointerup')
        if not getattr(self,'closing',False) and hasattr(self,'content_host') and watched==self.content_host and event.type()==QEvent.Type.Resize:
            for page in self.content_host.findChildren(InAppPage,options=Qt.FindChildOption.FindDirectChildrenOnly):page.setGeometry(self.content_host.rect())
        return super().eventFilter(watched,event)

    def build_profile(self):
        self.profile_dialog=InAppPage(self.content_host,'Профиль Pulse')
        outer=QVBoxLayout(self.profile_dialog.body);outer.setContentsMargins(24,22,24,26)
        form=QWidget();form.setMaximumWidth(840);box=QVBoxLayout(form);box.setContentsMargins(0,0,0,0);box.setSpacing(24)
        outer.addWidget(form,0,Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignHCenter);outer.addStretch()
        header=QHBoxLayout();header.setSpacing(22);self.profile_avatar=Artwork(88);header.addWidget(self.profile_avatar)
        words=QVBoxLayout();words.setSpacing(10);heading=QLabel('Твой профиль Pulse');heading.setStyleSheet('font-size:24px;font-weight:600');words.addWidget(heading)
        avatar=self.button('Изменить аватар',self.choose_avatar);words.addWidget(avatar,0,Qt.AlignmentFlag.AlignLeft);header.addLayout(words);header.addStretch();box.addLayout(header)
        metrics=QHBoxLayout();metrics.setSpacing(18);self.profile_metrics=[]
        for text in ('Время','Прослушано','Разных треков'):
            label=QLabel(text);label.setMinimumHeight(78);label.setMinimumWidth(160);label.setStyleSheet('font-size:16px;color:#c3c4cf;padding:14px;background:#15171d;border-radius:12px;')
            metrics.addWidget(label,1);self.profile_metrics.append(label)
        box.addLayout(metrics);self.top_artist=QLabel();self.top_artist.setWordWrap(True);box.addWidget(self.top_artist)
        hint=QLabel('Твой профиль, история и настройки сохраняются на этом компьютере.');hint.setObjectName('muted');hint.setWordWrap(True);box.addWidget(hint)
        name=QVBoxLayout();name.setSpacing(12);name.addWidget(QLabel('Имя в профиле'))
        self.name_edit=QLineEdit(self.profile.get('name',''));self.name_edit.setMaxLength(40);self.name_edit.setPlaceholderText('Как тебя называть?');name.addWidget(self.name_edit)
        name.addWidget(self.button('Сохранить профиль',self.save_profile,primary=True),0,Qt.AlignmentFlag.AlignLeft);box.addLayout(name)
        box.addSpacing(8);sources=QLabel('Источники музыки');sources.setStyleSheet('font-size:18px;font-weight:600');box.addWidget(sources)
        source=QVBoxLayout();source.setSpacing(14);self.account=QLabel('Яндекс Музыка · не подключена');self.account.setObjectName('muted');source.addWidget(self.account)
        self.login=self.button('Подключить Яндекс Музыку',self.connect_yandex,primary=True);source.addWidget(self.login,0,Qt.AlignmentFlag.AlignLeft)
        self.logout=self.button('Отключить Яндекс',self.sign_out);self.logout.hide();source.addWidget(self.logout,0,Qt.AlignmentFlag.AlignLeft)
        source.addWidget(self.button('Открыть лайки Яндекса',self.load_likes),0,Qt.AlignmentFlag.AlignLeft)
        sc=QLabel('SoundCloud · выбирай источник в поиске, чтобы найти публичные треки и ремиксы.');sc.setWordWrap(True);sc.setObjectName('muted');source.addWidget(sc);box.addLayout(source)
        self.profile_dialog.finished.connect(lambda _:self.maybe_tour())

    def refresh_profile(self):
        if not hasattr(self,'profile_metrics'):return
        seconds=int(self.stats['seconds']);values=(f'{seconds//3600} ч {(seconds%3600)//60} мин',str(self.stats['plays']),str(len(self.stats['unique'])))
        for label,title,value in zip(self.profile_metrics,('Слушал','Прослушано','Разных треков'),values):label.setText(value+'\n'+title)
        artists=self.stats.get('artists',{})
        top=max(artists,key=artists.get) if artists else 'Пока нет — включи любимую музыку'
        self.top_artist.setText('Чаще всего слушаешь: '+top)
        avatar=self.data_dir/'avatar.png'
        if avatar.exists():
            self.profile_avatar.setPixmap(QPixmap(str(avatar)));self.profile_nav.setIcon(QIcon(str(avatar)))

    def open_profile(self):
        self.refresh_profile();super().open_profile()

    def build_settings(self):
        from backgrounds_ui import Backgrounds
        self.settings_dialog=InAppPage(self.content_host,'Оформление Pulse')
        outer=QVBoxLayout(self.settings_dialog.body);outer.setContentsMargins(20,20,20,20)
        self.settings_panel=QWidget();self.settings_panel.setMinimumWidth(530);self.settings_panel.setMaximumWidth(660)
        layout=QVBoxLayout(self.settings_panel);layout.setContentsMargins(0,0,0,0);layout.setSpacing(20)
        outer.addWidget(self.settings_panel,0,Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop);outer.addStretch()
        self.backgrounds=Backgrounds(self);layout.addWidget(self.backgrounds.controls(self.settings_panel))
        self.vortex_controls=QWidget();native=QVBoxLayout(self.vortex_controls);native.setContentsMargins(0,0,0,0);native.setSpacing(15)
        self.theme_controls={};self.theme_values={}
        for key,label,maximum,factor in [('hue','Оттенок',360,1),('speed','Скорость',30,10),('complexity','Сложность',5,1)]:
            row=QHBoxLayout();row.addWidget(QLabel(label));row.addStretch();value=QLabel();row.addWidget(value);native.addLayout(row)
            slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(1 if key=='complexity' else 0,maximum);slider.setValue(round(self.theme[key]*factor))
            slider.valueChanged.connect(lambda n,k=key,f=factor:self.change_theme(k,n/f));native.addWidget(slider)
            self.theme_controls[key]=slider;self.theme_values[key]=value
        native.addWidget(self.button('Сбросить вихрь',self.reset_theme));layout.addWidget(self.vortex_controls)
        layout.addWidget(QLabel('Название окна'));self.title_edit=QLineEdit(self.theme['title']);self.title_edit.setMaxLength(80)
        self.title_edit.textChanged.connect(lambda text:self.change_theme('title',text));layout.addWidget(self.title_edit)
        self.motion_check=QCheckBox('Анимация фона');self.motion_check.setChecked(self.theme['motion']);self.motion_check.toggled.connect(lambda b:self.change_theme('motion',b));layout.addWidget(self.motion_check)
        self.backgrounds.selector.currentIndexChanged.connect(self.update_background_controls);self.update_background_controls()
        layout.addSpacing(14);layout.addWidget(QLabel('Воспроизведение'))
        self.repeat_select=QComboBox();self.repeat_select.addItems(['Без повтора','Повторять очередь','Повторять один трек']);self.repeat_select.currentIndexChanged.connect(lambda i:setattr(self,'repeat_mode',i));layout.addWidget(self.repeat_select)
        self.sleep_select=QComboBox();self.sleep_select.addItems(['Таймер сна выключен','Через 15 минут','Через 30 минут','Через 60 минут','Через 90 минут']);self.sleep_select.currentIndexChanged.connect(lambda i:self.set_sleep([0,15,30,60,90][i]));layout.addWidget(self.sleep_select)
        self.sleep_timer=QTimer(self);self.sleep_timer.setSingleShot(True);self.sleep_timer.timeout.connect(self.sleep_now)

    def update_background_controls(self):
        self.vortex_controls.setVisible(self.backgrounds.data['effect']=='vortex')

    def change_theme(self,key,value):
        super().change_theme(key,value)
        if hasattr(self,'backgrounds'):self.backgrounds.apply()

    def set_sleep(self,minutes):
        self.sleep_timer.stop();self.sleep_deadline=time.monotonic()+minutes*60 if minutes else 0
        if minutes:self.sleep_timer.start(minutes*60000)

    def sleep_now(self):
        self.sleep_timer.stop()
        self.want_playing=False;self.media.pause();self.sleep_deadline=0
        self.sleep_select.setCurrentIndex(0);self.status.setText('Таймер сна · воспроизведение приостановлено')

    def hide_pages(self):
        if hasattr(self,'content_host'):
            for page in self.content_host.findChildren(InAppPage,options=Qt.FindChildOption.FindDirectChildrenOnly):page.hide()

    def open_search(self):self.hide_pages();super().open_search()
    def show_favorites(self):self.hide_pages();super().show_favorites()
    def show_local(self):self.hide_pages();super().show_local()
    def show_queue(self):self.hide_pages();super().show_queue()
    def load_likes(self):self.hide_pages();super().load_likes()
    def sign_out(self):
        self.wave_generation+=1;self.wave_mode=False;self.wave_context=None;self.wave_loading=False;self.wave_waiting=False;self.want_playing=False
        super().sign_out()

    def save_profile(self):
        name=self.name_edit.text().strip()
        if not name:self.name_edit.setFocus();return
        self.profile.update(id=self.profile.get('id',str(uuid.uuid4())),name=name)
        try:self.save_data('profile.json',self.profile)
        except OSError:self.status.setText('Не удалось сохранить профиль.');return
        self.profile_nav.setToolTip(name+' · профиль');self.profile_dialog.accept()

    def embedded_picker(self,title,filters,multiple,callback):
        page=InAppPage(self.content_host,title);box=QVBoxLayout(page.body)
        location=QLineEdit(str(Path.home()));box.addWidget(location)
        shortcuts=QHBoxLayout();box.addLayout(shortcuts)
        model=QFileSystemModel(page)
        model.setFilter(QDir.Filter.AllDirs|QDir.Filter.Files|QDir.Filter.NoDotAndDotDot)
        model.setNameFilters(filters.split('(',1)[1].rstrip(')').split());model.setNameFilterDisables(False)
        tree=QTreeView();tree.setModel(model);tree.setColumnWidth(0,350);tree.hideColumn(2)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection if multiple else QAbstractItemView.SelectionMode.SingleSelection)
        tree.setStyleSheet('QTreeView{background:#111218;color:#eee;border:1px solid #292a32;border-radius:12px;padding:8px;} QTreeView::item:selected{background:#3c3545;}')
        tree.setSortingEnabled(True);tree.sortByColumn(0,Qt.SortOrder.AscendingOrder);box.addWidget(tree,1)
        def folder(path):
            if Path(path).is_dir():location.setText(str(path));tree.setRootIndex(model.setRootPath(str(path)))
        for label,key in [('Домой',QStandardPaths.StandardLocation.HomeLocation),('Рабочий стол',QStandardPaths.StandardLocation.DesktopLocation),('Изображения',QStandardPaths.StandardLocation.PicturesLocation),('Музыка',QStandardPaths.StandardLocation.MusicLocation)]:
            path=QStandardPaths.writableLocation(key)
            shortcuts.addWidget(self.button(label,lambda checked=False,p=path:folder(p)))
        shortcuts.addWidget(self.button('Выше',lambda:folder(str(Path(location.text()).parent))))
        location.returnPressed.connect(lambda:folder(location.text()));folder(str(Path.home()))
        message=QLabel('Выбери файл'+('ы. Для нескольких зажми Ctrl.' if multiple else '.'));message.setObjectName('muted');box.addWidget(message)
        def accepted():
            paths=[model.filePath(index) for index in tree.selectionModel().selectedRows(0) if not model.isDir(index)]
            if not paths:message.setText('Сначала выбери файл.');return
            callback(paths);page.accept()
        def double_clicked(index):
            if model.isDir(index):folder(model.filePath(index))
            elif not multiple:accepted()
        tree.doubleClicked.connect(double_clicked)
        choose=self.button('Выбрать',accepted,primary=True);box.addWidget(choose)
        page.file_tree=tree;page.file_model=model;page.choose_button=choose;page.open_folder=folder
        page.finished.connect(lambda _:(self.extra_pages.remove(page),page.deleteLater()))
        self.extra_pages.append(page);page.show()

    def choose_avatar(self):
        def selected(paths):
            image=QPixmap(paths[0])
            if image.isNull():self.status.setText('Не удалось открыть изображение.');return
            self.data_dir.mkdir(parents=True,exist_ok=True)
            image.scaled(512,512,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation).save(str(self.data_dir/'avatar.png'))
            self.profile['avatar']='avatar.png';self.save_data('profile.json',self.profile);self.refresh_profile()
            QTimer.singleShot(0,lambda:self.open_profile())
        self.embedded_picker('Аватар профиля','Изображения (*.png *.jpg *.jpeg *.webp)',False,selected)

    def import_files(self):
        import hashlib
        def selected(paths):
            for value in paths:
                path=Path(value).resolve();key='local:'+hashlib.sha256(str(path).lower().encode()).hexdigest()[:24]
                self.local_library[key]={'id':key,'title':path.stem,'artist':'На этом компьютере','duration':0,'source':'local','path':str(path)}
            self.save_data('library.json',self.local_library);self.show_local()
        self.embedded_picker('Добавить музыку','Музыка (*.mp3 *.flac *.wav *.ogg *.m4a *.aac)',True,selected)

    @staticmethod
    def artist_data(artist):
        cover=getattr(getattr(artist,'cover',None),'uri',None)
        return {'id':str(artist.id),'name':artist.name,'source':'yandex','cover':('https://'+cover.replace('%%','100x100')) if cover else None}

    @staticmethod
    def track_data(track):
        cover=getattr(track,'cover_uri',None)
        return {'id':str(track.id),'title':track.title or 'Без названия','artist':', '.join(a.name for a in track.artists),
            'duration':track.duration_ms or 0,'source':'yandex','artists':[Features.artist_data(a) for a in track.artists],
            'cover':('https://'+cover.replace('%%','100x100')) if cover else None}

    @staticmethod
    def artist_key(text):
        table=dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
            ['a','b','v','g','d','e','e','zh','z','i','y','k','l','m','n','o','p','r','s','t','u','f','h','ts','ch','sh','sch','','y','','e','yu','ya']))
        value=''.join(table.get(c,c) for c in unicodedata.normalize('NFKD',text.lower()))
        return re.sub('[^a-z0-9]','',value)

    def clear_layout(self,layout):
        while layout.count():
            item=layout.takeAt(0)
            if item.widget():item.widget().deleteLater()

    def fetch_suggestions(self):
        query=self.query.text().strip();self.suggestion_seq+=1;version=self.suggestion_seq
        if len(query)<2:self.suggestions.hide();return
        client=self.client or self.catalog
        def work(_):
            result=client.search_suggest(query,timeout=6)
            return list(result.suggestions or [])[:5] if result else []
        def done(words):
            if version!=self.suggestion_seq or self.query.text().strip()!=query:return
            self.clear_layout(self.suggestions_layout)
            for word in words:
                def choose(checked=False,text=word):self.query.setText(text);self.search()
                self.suggestions_layout.addWidget(self.button(word[:28],choose))
            self.suggestions_layout.addStretch();self.suggestions.setVisible(bool(words))
        job=self.task(work,done);job.silent=True

    def search(self):
        query=self.query.text().strip()
        if not query:return
        sc=hasattr(self,'provider') and self.provider.currentIndex()==1
        if not sc and not self.require_client():return
        self.search_version+=1;version=self.search_version;client=self.client
        self.status.setText('Поиск треков и исполнителей…')
        if hasattr(self,'suggestions'):self.suggestions.hide()
        def work(_):
            if sc:return self.soundcloud.search(query)
            result=client.search(query,type_='all')
            artists=[self.artist_data(a) for a in (result.artists.results if getattr(result,'artists',None) else [])][:6]
            rows=[self.track_data(t) for t in (result.tracks.results if result.tracks else [])]
            key=self.artist_key(query)
            matches=[a for a in artists if len(key)>=3 and self.artist_key(a['name']).startswith(key)]
            if not matches and artists and getattr(getattr(result,'best',None),'type',None)=='artist':matches=artists[:1]
            if matches:
                selected=matches[0];catalog=[]
                for page in range(2):
                    data=client.artists_tracks(selected['id'],page=page,page_size=100)
                    batch=[self.track_data(t) for t in data.tracks];catalog+=batch
                    total=getattr(getattr(data,'pager',None),'total',len(catalog)) or len(catalog)
                    if not batch or len(catalog)>=total:break
                if catalog:rows=catalog
            return rows,artists
        def done(result):
            if version!=self.search_version:return
            rows,artists=result;self.view='search';self.render(rows);self.show_artists(artists)
            self.status.setText(f'Треки: {len(rows)} · исполнители: {len(artists)} · '+('SoundCloud' if sc else 'Яндекс Музыка'))
        job=self.task(work,done);job.search_version=version

    def show_artists(self,artists):
        self.clear_layout(self.artist_layout)
        limit=max(1,min(4,self.content_host.width()//225))
        for artist in artists[:limit]:
            card=ArtistCard(artist,self.cover_loader);card.activated.connect(self.open_artist);self.artist_layout.addWidget(card)
        self.artist_layout.addStretch();self.artist_shelf.setVisible(bool(artists))

    def open_artist(self,artist):
        self.hide_pages()
        self.artist_info=artist;self.artist_page_index=0;self.search_version+=1;version=self.search_version
        if artist.get('source') not in ('soundcloud','audius') and not self.require_client():return
        self.status.setText('Открываю исполнителя…');client=self.client
        def work(_):
            if artist.get('source') in ('soundcloud','audius'):return getattr(self,artist['source']).artist(artist),False
            data=client.artists_tracks(artist['id'],page=0,page_size=50)
            rows=[self.track_data(t) for t in data.tracks]
            pager=getattr(data,'pager',None);total=getattr(pager,'total',len(rows)) or len(rows)
            return rows,total>len(rows)
        def done(result):
            if version!=self.search_version:return
            rows,more=result;self.view='artist';self.render(rows);self.heading.setText(artist['name'])
            self.hero_art.pixmap=None;self.hero_art.hero=False;self.cover_loader.load(artist.get('cover'),self.hero_art);self.hero_art.update()
            self.more_artist.setVisible(more);self.status.setText('Треки исполнителя · '+artist['name'])
        self.task(work,done)

    def more_artist_tracks(self):
        artist=self.artist_info
        if not artist or not self.client:return
        version=self.search_version;page=self.artist_page_index+1;client=self.client
        self.more_artist.setEnabled(False)
        def work(_):
            data=client.artists_tracks(artist['id'],page=page,page_size=50)
            return [self.track_data(t) for t in data.tracks],getattr(getattr(data,'pager',None),'total',0)
        def done(result):
            self.more_artist.setEnabled(True)
            if version!=self.search_version or self.view!='artist':return
            rows,total=result;self.artist_page_index=page;combined=self.rows+rows
            self.render(combined);self.more_artist.setVisible(bool(rows) and len(combined)<(total or len(combined)+1))
        self.task(work,done)

    def render(self,rows):
        super().render(rows)
        if hasattr(self,'home_panel'):
            home=self.view=='home';self.home_panel.setVisible(home);self.library_hero.setVisible(not home)
            self.artist_shelf.hide();self.more_artist.hide()
            if self.view=='artist' and self.artist_info:self.heading.setText(self.artist_info['name'])
            elif self.view=='history':self.heading.setText('История')
            else:self.hero_art.hero=True;self.hero_art.pixmap=None;self.hero_art.update()
        for i in range(self.tracks.count()):
            widget=self.tracks.itemWidget(self.tracks.item(i));widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            widget.customContextMenuRequested.connect(lambda pos,index=i,w=widget:self.track_menu(index,w.mapToGlobal(pos)))

    def track_menu(self,index,pos):
        if not 0<=index<len(self.rows):return
        row=self.rows[index];menu=QMenu(self);menu.setStyleSheet('QMenu{background:#191a20;color:#eee;border:1px solid #3b3c44;padding:6px;} QMenu::item{padding:10px 16px;} QMenu::item:selected{background:#37303c;}')
        wave=menu.addAction('Играть мою волну по этому треку');wave.triggered.connect(lambda:self.start_wave(row))
        menu.addAction('Слушать следующим').triggered.connect(lambda:self.enqueue_next(row))
        artists=row.get('artists') or []
        if not artists and row.get('artist_url'):artists=[{'id':row['artist_url'],'url':row['artist_url'],'name':row['artist'],'source':'soundcloud'}]
        if artists:menu.addAction('Перейти к исполнителю').triggered.connect(lambda:self.open_artist(artists[0]))
        menu.addAction('Убрать из любимых' if row['id'] in self.favorites else 'Добавить в любимые').triggered.connect(lambda:self.favorite(index))
        menu.popup(pos);self.active_menu=menu

    def enqueue_next(self,row):
        if self.current<0 or not self.queue:self.queue=[dict(row)];self.play_index(0);return
        self.queue.insert(self.current+1,dict(row));self.status.setText('Следующим: '+row['title'])
        if self.view=='queue':self.render(list(self.queue))
        self.prefetch_next()

    def show_home(self):
        if not hasattr(self,'home_panel'):return super().show_home()
        self.hide_pages();self.search_version+=1;self.view='home';self.search_box.hide();self.suggestions.hide()
        rows=self.home_rows or self.stats['history'][:20] or list(self.favorites.values())[:20]
        self.render(rows);self.status.setText('Персональная музыка по твоим вкусам и любимым трекам')
        avatar=self.data_dir/'avatar.png'
        if avatar.exists():self.wave_hero.art.setPixmap(QPixmap(str(avatar)))
        elif rows:self.cover_loader.load(rows[0].get('cover'),self.wave_hero.art)
        if self.client and not self.home_rows:self.load_home_recommendations()

    def show_history(self):
        self.hide_pages()
        self.search_version+=1;self.view='history';self.render(list(self.stats['history']));self.status.setText('Недавно прослушанные треки')

    def connected(self,client):
        super().connected(client)
        if hasattr(self,'home_panel') and self.view=='home':
            self.status.setText('Моя волна готова · рекомендации твоего аккаунта Яндекса');self.load_home_recommendations()

    def load_home_recommendations(self):
        if not self.client or self.home_reco_loading:return
        self.home_reco_loading=True;client=self.client
        def work(_):
            session=client.rotor_session_new('user:onyourwave',include_tracks_in_response=True)
            return [self.track_data(item.track) for item in (session.sequence or []) if item.track and item.track.available]
        def done(rows):
            self.home_reco_loading=False
            if self.client is not client:return
            self.home_rows=rows
            if self.view!='home':return
            self.render(rows)
            if rows:self.cover_loader.load(rows[0].get('cover'),self.wave_hero.art)
            self.refresh_wave_seeds()
        job=self.task(work,done);job.silent=True;job.home_reco=True

    def refresh_wave_seeds(self):
        if not hasattr(self,'wave_hero'):return
        for art,row in zip(self.wave_hero.preview_art,self.wave_seeds):
            art.row=row;art.pixmap=None;art.setToolTip('Волна: '+row['title']+' · '+row.get('artist',''));self.cover_loader.load(row.get('cover'),art);art.show()
        for art in self.wave_hero.preview_art[len(self.wave_seeds):]:art.hide()
        if hasattr(self.wave_hero,'seed_hint'):self.wave_hero.seed_hint.setVisible(not bool(self.wave_seeds))

    def remember_wave(self,row):
        self.wave_seeds=[dict(row)]+[r for r in self.wave_seeds if r['id']!=row['id']][:7]
        self.save_data('wave-seeds.json',self.wave_seeds);self.refresh_wave_seeds()

    def start_wave(self,seed=None):
        if seed is None and self.wave_mode and self.queue:self.toggle();return
        personal=seed is None
        if seed is None and not self.client:
            candidates=[r for r in list(self.favorites.values())+self.stats['history'][:20] if r.get('source')=='soundcloud']
            if candidates:seed=random.choice(candidates)
        sc=seed and seed.get('source') in ('soundcloud','audius')
        if not sc and not self.require_client():return
        self.wave_generation+=1;generation=self.wave_generation;self.wave_loading=True;client=self.client
        self.status.setText('Настраиваю твою волну…')
        def work(_):
            if sc:return getattr(self,'audius' if seed['source']=='audius' else 'soundcloud').related(seed),{'source':seed['source'],'seed':seed}
            seeds=['track:'+seed['id']] if seed and seed.get('source')!='local' else ['user:onyourwave']
            if seed and seed.get('source')=='local':
                found=client.search(seed['title'],type_='track')
                if found.tracks and found.tracks.results:seeds=['track:'+str(found.tracks.results[0].id)]
            elif not seed:
                liked=[r['id'] for r in self.favorites.values() if r.get('source','yandex')=='yandex']
                if liked:seeds+=['track:'+i for i in random.sample(liked,min(2,len(liked)))]
            session=client.rotor_session_new(seeds,include_tracks_in_response=True,queue=list(dict.fromkeys((self.wave_history.get(seed['id'],[]) if seed else [])+[r['id'] for r in self.stats['history'] if r.get('source')=='yandex']))[:60])
            if not session or not session.sequence:raise ValueError('empty_wave')
            rows=[dict(self.track_data(item.track),_wave_batch=session.batch_id) for item in session.sequence if item.track and item.track.available]
            return rows,{'source':'yandex','id':session.radio_session_id,'batch':session.batch_id,'seeds':seeds}
        def done(result):
            if generation!=self.wave_generation:return
            self.wave_loading=False;self.wave_failures=0;rows,context=result
            if hasattr(self,'prepare_wave_rows'):rows=self.prepare_wave_rows(rows,context)
            if not rows:self.status.setText('Пока нет рекомендаций для этой волны.');return
            self.wave_mode=True;self.wave_context=context;self.wave_waiting=False;self.queue=list(rows)
            self.view='wave';self.render(rows);self.heading.setText('Моя волна' if personal else 'Волна по треку')
            self.wave_title='Моя волна' if personal else 'Волна: '+seed['title']
            self.heading.setText(self.wave_title)
            if not personal:self.remember_wave(seed)
            self.feedback('radioStarted');self.play_index(0);self.next_wave_batch()
        job=self.task(work,done);job.wave_job=True;job.wave_generation=generation

    def next_wave_batch(self):
        if self.wave_loading or not self.wave_context:return
        self.wave_loading=True;generation=self.wave_generation;context=dict(self.wave_context);client=self.client
        queued=list(self.queue);seen={r['id'] for r in queued[-(60 if context['source']=='audius' else 250):]};needed=max(1,50-(len(queued)-max(0,self.current)))
        def work(_):
            added=[];empty=0;cursor=queued[-1]
            for attempt in range(20):
                if generation!=self.wave_generation or getattr(self,'closing',False):break
                if context['source'] in ('soundcloud','audius'):rows=getattr(self,context['source']).related(cursor)
                else:
                    data=client.rotor_session_tracks(context['id'],queue=[r['id'] for r in (queued+added)[-60:]])
                    rows=[dict(self.track_data(x.track),_wave_batch=data.batch_id) for x in (data.sequence or []) if x.track and x.track.available]
                    context['batch']=data.batch_id
                fresh=[r for r in rows if r['id'] not in seen]
                if hasattr(self,'prepare_wave_rows'):fresh=self.prepare_wave_rows(fresh,context,queued+added)
                if not fresh:
                    empty+=1
                    if empty>=2:break
                    if rows:cursor=rows[-1]
                    continue
                empty=0
                for row in fresh:
                    if row['id'] not in seen:added.append(row);seen.add(row['id'])
                cursor=added[-1]
                if len(added)>=needed:break
            return added,context
        def done(result):
            if generation!=self.wave_generation:return
            self.wave_loading=False;self.wave_failures=0;rows,ctx=result
            self.wave_context=ctx;self.queue.extend(rows)
            if self.view=='wave':self.render(list(self.queue));self.heading.setText(getattr(self,'wave_title','Моя волна'))
            if self.wave_waiting:
                if self.current+1<len(self.queue):
                    self.wave_waiting=False;self.play_index(self.current+1)
                else:
                    self.status.setText('Жду новые рекомендации от сервиса…')
                    QTimer.singleShot(5000,lambda:self.next_wave_batch() if generation==self.wave_generation and self.wave_mode else None)
        job=self.task(work,done);job.wave_job=True;job.wave_generation=generation

    def feedback(self,event):
        ctx=self.wave_context;client=self.client
        if not self.wave_mode or not ctx or ctx.get('source')!='yandex' or not client:return
        row=self.queue[self.current] if 0<=self.current<len(self.queue) else None
        if event!='radioStarted' and not row:return
        data=SessionEvent(event,datetime.now(timezone.utc).isoformat(),track_id=row['id'] if row and event!='radioStarted' else None,
            total_played_seconds=round(self.track_listened,2) if event in ('trackFinished','skip') else None)
        def work(_):
            try:return client.rotor_session_feedback(ctx['id'],data,batch_id=row.get('_wave_batch',ctx.get('batch')) if row else ctx.get('batch'),from_='pulse')
            except Exception:return False
        job=self.task(work,lambda _:None);job.silent=True

    def start_row(self,index):
        if not 0<=index<len(self.rows):return
        if self.wave_mode and self.view in ('wave','queue'):
            target=next((i for i,r in enumerate(self.queue) if r['id']==self.rows[index]['id']),None)
            if target is not None:self.feedback('skip');self.play_index(target);return
        if self.wave_mode:self.feedback('skip')
        self.wave_mode=False;self.wave_generation+=1;self.wave_loading=False;self.wave_context=None
        self.queue=list(self.rows);self.play_index(index)

    def play_index(self,index,resume=0,recovery=False):
        if not 0<=index<len(self.queue):return
        row=self.queue[index];source=row.get('source','yandex')
        if source=='yandex' and not self.require_client():return
        if not recovery:
            self.track_listened=0.;self.track_counted=False;self.recoveries=0
        self.current=index;self.play_version+=1;version=self.play_version
        self.loading_audio=True;self.want_playing=True;self.has_progress=False;self.ending_handled=False
        self.resume_position=resume;self.last_position=resume;self.last_wall=time.monotonic();self.last_advance=time.monotonic()
        self.media.stop();self.media.setSource(QUrl())
        self.now.setText(row['title']);self.now_artist.setText(row['artist']);self.dock_art.pixmap=None;self.dock_art.update()
        self.cover_loader.load(row.get('cover'),self.dock_art);self.current_favorite.setChecked(row['id'] in self.favorites)
        self.status.setText('Буферизация трека…' if source=='yandex' else 'Подключаю трек…')
        client=self.client
        def work(signals):
            if source=='local':
                if not Path(row['path']).exists():raise FileNotFoundError()
                return row['path']
            if source=='soundcloud':return self.soundcloud.stream(row)
            if source=='audius':return self.cache.public(row,self.audius.stream(row),on_progress=signals.progress.emit)
            return self.cache.yandex(client,row,on_progress=signals.progress.emit)
        def done(value):
            if version!=self.play_version:return
            self.loading_audio=False;url=QUrl(value) if str(value).startswith(('https:','http:','file:')) else QUrl.fromLocalFile(str(value))
            self.active_audio=value;self.media.setSource(url)
            if self.want_playing:self.media.play()
            self.status.setText(('Моя волна · ' if self.wave_mode else '')+{'yandex':'Яндекс Музыка','soundcloud':'SoundCloud','local':'Музыка с компьютера','audius':'Audius'}[source])
            if not recovery:self.feedback('trackStarted')
            if source in ('yandex','audius','soundcloud'):
                try:self.cache.trim((str(value),))
                except OSError:pass
            if self.wave_mode and len(self.queue)-self.current<30:self.next_wave_batch()
            if source=='yandex':self.prefetch_next()
        job=self.task(work,done);job.play_version=version
        job.signals.progress.connect(lambda percent:self.status.setText(f'Буферизация трека · {percent}%') if version==self.play_version and self.loading_audio else None)

    def prefetch_next(self):
        index=self.current+1
        if not self.client or index>=len(self.queue):return
        row=self.queue[index];client=self.client
        if row.get('source','yandex')!='yandex':return
        def done(value):
            try:self.cache.trim((str(value),str(getattr(self,'active_audio',''))))
            except OSError:pass
        job=self.task(lambda _:self.cache.yandex(client,row),done);job.silent=True

    def toggle(self):
        if self.loading_audio:self.want_playing=not self.want_playing;return
        if self.media.playbackState()==QMediaPlayer.PlaybackState.PlayingState:
            self.want_playing=False;self.media.pause()
        elif self.media.source().isEmpty():
            row=self.tracks.currentRow()
            if self.rows:self.start_row(max(0,row))
        else:self.want_playing=True;self.media.play()

    def step(self,offset):
        if offset<0 and self.media.position()>3000:self.media.setPosition(0);return
        self.feedback('skip')
        if offset>0 and self.shuffle_button.isChecked() and not self.wave_mode and len(self.queue)>1:
            self.play_index(random.choice([i for i in range(len(self.queue)) if i!=self.current]))
        elif self.current+offset<len(self.queue) and self.current+offset>=0:self.play_index(self.current+offset)
        elif offset>0 and self.wave_mode:self.wave_waiting=True;self.next_wave_batch()

    def advance_finished(self):
        if self.ending_handled or self.loading_audio or not self.has_progress:return
        self.ending_handled=True;self.feedback('trackFinished');self.count_track(force=True)
        if self.repeat_mode==2:self.play_index(self.current);return
        if self.shuffle_button.isChecked() and not self.wave_mode and len(self.queue)>1:
            self.play_index(random.choice([i for i in range(len(self.queue)) if i!=self.current]))
        elif self.current+1<len(self.queue):self.play_index(self.current+1)
        elif self.wave_mode:self.wave_waiting=True;self.next_wave_batch()
        elif self.repeat_mode==1 and self.queue:self.play_index(0)
        else:self.want_playing=False;self.status.setText('Очередь закончилась.')

    def media_status(self,status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia,QMediaPlayer.MediaStatus.BufferedMedia) and self.resume_position:
            position=self.resume_position;self.resume_position=0;self.media.setPosition(position)
        if status==QMediaPlayer.MediaStatus.EndOfMedia:
            expected=self.queue[self.current].get('duration',0) if 0<=self.current<len(self.queue) else 0
            if expected and self.media.duration() and self.media.duration()<expected-7000 and self.recoveries<2:
                self.recover_playback();return
            QTimer.singleShot(40,lambda:self.advance_finished())

    def position_changed(self,position):
        super().position_changed(position)
        if position>0:
            if not self.has_progress and 0<=self.current<len(self.queue):
                row=self.queue[self.current];self.stats['history']=[row]+[r for r in self.stats['history'] if r['id']!=row['id']][:99]
            self.has_progress=True

    def playback_error(self,*_):
        if self.loading_audio or not self.want_playing:return
        version=self.play_version;QTimer.singleShot(200,lambda:self.recover_playback() if version==self.play_version else None)

    def recover_playback(self):
        if self.loading_audio or not self.want_playing or not 0<=self.current<len(self.queue):return
        if self.recoveries>=2:
            self.status.setText('Трек недоступен. Перехожу к следующему.');self.has_progress=True;self.advance_finished();return
        self.recoveries+=1;row=self.queue[self.current]
        if row.get('source','yandex')=='yandex':self.cache.invalidate(row)
        position=max(0,self.media.position());self.play_index(self.current,resume=position,recovery=True)

    def count_track(self,force=False):
        if self.track_counted or not 0<=self.current<len(self.queue):return
        row=self.queue[self.current];duration=row.get('duration',0) or self.media.duration()
        threshold=min(30,max(1,duration/2000))
        if self.track_listened<threshold:return
        self.track_counted=True;self.stats['plays']+=1
        counts=self.stats.setdefault('track_plays',{});counts[row['id']]=counts.get(row['id'],0)+1
        if row['id'] not in self.stats['unique']:self.stats['unique'].append(row['id'])
        self.stats['history']=[row]+[r for r in self.stats['history'] if r['id']!=row['id']][:99]

    def playback_tick(self):
        now=time.monotonic();position=self.media.position();dt=min(2.,now-self.last_wall)
        delta=position-self.last_position
        if self.media.playbackState()==QMediaPlayer.PlaybackState.PlayingState and delta>0:
            self.last_advance=now
            played=min(dt,delta/1000) if delta<3000 else 0
            self.stats['seconds']+=played;self.track_listened+=played
            if 0<=self.current<len(self.queue):
                artist=self.queue[self.current]['artist'];self.stats['artists'][artist]=self.stats['artists'].get(artist,0)+played
            self.count_track()
        elif self.want_playing and not self.loading_audio:
            duration=self.media.duration()
            if duration>0 and position>=duration-300 and now-self.last_advance>1.5:self.advance_finished()
            elif now-self.last_advance>(10 if self.has_progress else 18):self.recover_playback();self.last_advance=now
        self.last_position=position;self.last_wall=now
        if now-self.last_stats_save>10:
            self.last_stats_save=now
            try:self.save_data('listening.json',self.stats)
            except OSError:pass
            if self.profile_dialog.isVisible():self.refresh_profile()

    def job_failed(self,payload):
        name,job=payload
        if getattr(job,'silent',False):
            if getattr(job,'home_reco',False):self.home_reco_loading=False
            self.jobs.discard(job);return
        if hasattr(job,'search_version') and job.search_version!=self.search_version:self.jobs.discard(job);return
        if getattr(job,'wave_job',False):
            if job.wave_generation!=self.wave_generation:self.jobs.discard(job);return
            self.wave_loading=False;self.wave_failures+=1
            if self.wave_waiting and self.wave_failures<=2:
                self.jobs.discard(job);QTimer.singleShot(1500,lambda:self.next_wave_batch());self.status.setText('Восстанавливаю продолжение волны…');return
        if hasattr(job,'play_version'):
            self.jobs.discard(job)
            if job.play_version!=self.play_version:return
            self.loading_audio=False
            if name in ('TrackUnavailable','FileNotFoundError'):
                self.status.setText('Трек недоступен. Перехожу к следующему.');self.has_progress=True;self.advance_finished();return
            if name=='SoundCloudUnavailable':
                self.want_playing=False;self.status.setText('SoundCloud не ответил. Проверь доступ к сервису и попробуй ещё раз.');return
            self.status.setText('SoundCloud не ответил. Проверь доступ к сервису.' if name=='SoundCloudUnavailable' else 'Не удалось загрузить трек. Повторяю подключение…')
            version=self.play_version;QTimer.singleShot(1000,lambda:self.recover_playback() if version==self.play_version else None);return
        if name=='SoundCloudUnavailable':self.jobs.discard(job);self.status.setText('SoundCloud не ответил. Проверь доступ к сервису и повтори поиск.');return
        super().job_failed(payload)

    def closeEvent(self,event):
        if hasattr(self,'backgrounds'):self.backgrounds.close()
        if hasattr(self,'stats_timer'):self.stats_timer.stop()
        try:self.save_data('listening.json',self.stats)
        except OSError:pass
        super().closeEvent(event)

    def state_changed(self,state):
        super().state_changed(state)
        if hasattr(self,'wave_hero'):self.wave_hero.play.setGlyph('pause' if self.wave_mode and state==QMediaPlayer.PlaybackState.PlayingState else 'play')

    def favorite(self,index):
        current_id=self.queue[self.current]['id'] if 0<=self.current<len(self.queue) else None
        row=self.rows[index];liked=row['id'] not in self.favorites
        super().favorite(index)
        if row['id']==current_id:self.feedback('like' if liked else 'unlike')

    def favorite_current(self):
        row=self.queue[self.current] if 0<=self.current<len(self.queue) else None
        liked=row and row['id'] not in self.favorites
        super().favorite_current()
        if row:self.feedback('like' if liked else 'unlike')
