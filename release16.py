"""Cross-platform release refinements: artist albums, recommendations and mandatory signed updates."""
import os,sys,time
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QLabel,QVBoxLayout,QHBoxLayout,QScrollArea,QDialog,QProgressBar
from library_ui import Artwork
from album_ui import AlbumCard,AlbumScroll
import updates
from catalog_extensions import albums,album_tracks,rank_for_you

class UpdateGate(QDialog):
    def reject(self):pass
    def closeEvent(self,event):event.ignore()

class Release16:
    def __init__(self):
        self.reco_signature=None;self.reco_pending=False;self.album_generation=0;self.required_update=False
        super().__init__()
        self.album_panel=QWidget();box=QVBoxLayout(self.album_panel);box.setContentsMargins(0,0,0,0)
        head=QHBoxLayout();self.album_heading=QLabel('Альбомы');head.addWidget(self.album_heading);head.addStretch();self.album_toggle=self.button('Показать',self.toggle_albums);self.album_toggle.setFixedHeight(30);head.addWidget(self.album_toggle);box.addLayout(head)
        self.album_scroll=AlbumScroll();self.album_scroll.setWidgetResizable(True);self.album_scroll.setFixedHeight(138);self.album_scroll.setFrameShape(QScrollArea.Shape.NoFrame);self.album_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.album_scroll.setStyleSheet('QScrollArea{background:transparent;border:0;} QScrollBar:horizontal{height:4px;background:transparent;margin:0;} QScrollBar::handle:horizontal{background:#68616e;border-radius:2px;min-width:40px;} QScrollBar::handle:horizontal:hover{background:#b0a3b4;} QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0;height:0;} QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal{background:transparent;}');self.album_scroll.hide()
        self.album_host=QWidget();self.album_cards=QHBoxLayout(self.album_host);self.album_cards.setContentsMargins(0,0,0,4);self.album_cards.setSpacing(8);self.album_scroll.setWidget(self.album_host);box.addWidget(self.album_scroll)
        layout=self.content_host.layout();layout.insertWidget(layout.indexOf(self.artist_shelf)+1,self.album_panel);self.album_panel.hide()
        self.update_auto.setChecked(True);self.update_auto.hide()
        self.update_text.setText('Новые версии загружаются и устанавливаются автоматически. Профиль и библиотека сохраняются.')
        self.update_period=QTimer(self);self.update_period.timeout.connect(lambda:self.check_updates(True));self.update_period.start(15*60*1000)

    def open_artist(self,artist):
        super().open_artist(artist)
        self.album_generation+=1;generation=self.album_generation
        if not hasattr(self,'album_panel'):return
        self.album_panel.show();self.album_scroll.hide();self.album_toggle.setText('Показать');self.library_hero.setFixedHeight(156);self.hero_art.setFixedSize(112,112);self.heading.setStyleSheet('font-size:30px;font-weight:800;');self.clear_layout(self.album_cards);self.album_heading.setText('Загружаем альбомы…')
        def done(rows):
            if generation!=self.album_generation or self.view!='artist':return
            self.album_heading.setText('Альбомы · '+str(len(rows)) if rows else 'Источник не вернул альбомы')
            for album in rows:
                self.album_cards.addWidget(AlbumCard(album,self.cover_loader,self.open_album))
            self.album_cards.addStretch()
        job=self.task(lambda _:albums(self,dict(artist)),done);job.albums_job=True;job.albums_generation=generation

    def toggle_albums(self):
        expanded=self.album_scroll.isHidden();self.album_scroll.setVisible(expanded);self.album_toggle.setText('Скрыть' if expanded else 'Показать')

    def open_album(self,album):
        self.album_generation+=1;generation=self.album_generation;self.status.setText('Открываю альбом…')
        def done(rows):
            if generation!=self.album_generation:return
            self.hide_pages();self.view='album';self.render(rows);self.heading.setText(album['title']);self.cover_loader.load(album.get('cover'),self.hero_art);self.status.clear()
        job=self.task(lambda _:album_tracks(self,album),done);job.albums_job=True;job.albums_generation=generation

    def render(self,rows):
        super().render(rows)
        if hasattr(self,'album_panel'):self.album_panel.setVisible(self.view=='artist')

    def show_home(self):
        super().show_home()
        if hasattr(self,'soundcloud') and self.profile:self.load_home_recommendations()

    def load_home_recommendations(self):
        if self.reco_pending:return
        favorites=list(self.favorites.values());history=list(self.stats['history'][:40]);signature=tuple(r['id'] for r in favorites)+tuple(r['id'] for r in history)
        if self.reco_signature==signature and self.home_rows:return
        self.reco_pending=True
        def work(_):
            pool=[];seen=set();anchors=0
            for seed in favorites+history:
                artist=seed.get('artist','')
                if artist in seen:continue
                seen.add(artist)
                try:
                    source=seed.get('source','yandex')
                    if source in ('soundcloud','audius'):pool+=getattr(self,source).related(seed)
                    else:
                        from discovery import PublicDiscovery
                        rows,_=PublicDiscovery({'soundcloud':self.soundcloud,'audius':self.audius}).wave(seed);pool+=rows
                except Exception:pass
                anchors+=1
                if anchors>=2:break
            if not pool:pool=self.audius.trending(limit=50)
            return rank_for_you(pool,favorites,history)
        def done(rows):
            self.reco_pending=False;self.reco_signature=signature;self.home_rows=rows
            if self.view=='home':self.render(rows)
        job=self.task(work,done);job.personal_reco=True

    def check_updates(self,automatic=False):
        if self.update_busy:return
        self.update_busy=True;self.update_check.setEnabled(False)
        def done(release):
            self.update_busy=False;self.update_check.setEnabled(True);self.available_release=release
            if not release:self.update_text.setText('Установлена последняя опубликованная версия.');return
            self.required_update=True;self.show_update_gate(release);self.download_update()
        job=self.task(lambda _:updates.check_release(),done);job.update_job='check'

    def show_update_gate(self,release):
        if getattr(self,'update_gate',None):self.update_gate.show();return
        self.update_gate=UpdateGate(self);self.update_gate.setWindowTitle('Обновление Pulse');self.update_gate.setWindowFlag(Qt.WindowType.WindowCloseButtonHint,False);self.update_gate.setModal(True);self.update_gate.setMinimumWidth(440)
        box=QVBoxLayout(self.update_gate);box.setContentsMargins(26,24,26,24);box.setSpacing(16)
        self.gate_text=QLabel('Обновляем Pulse до '+release['version']+'…');self.gate_text.setWordWrap(True);box.addWidget(self.gate_text)
        self.gate_progress=QProgressBar();box.addWidget(self.gate_progress)
        box.addWidget(self.button('Повторить загрузку',self.download_update));box.addWidget(self.button('Закрыть Pulse',self.close));self.update_gate.show()

    def download_update(self):
        if self.update_busy or not getattr(self,'available_release',None):return
        self.update_busy=True;release=dict(self.available_release)
        self.gate_text.setText('Загружаем и проверяем Pulse '+release['version']+'…')
        def done(path):
            self.update_busy=False;self.update_ready=(path,release);self.gate_progress.setValue(100)
            if getattr(sys,'frozen',False):self.install_update()
            else:self.gate_text.setText('Обновление проверено. При запуске EXE оно установится автоматически; исходники не заменяются.')
        job=self.task(lambda signals:updates.download_release(release,self.data_dir/'updates',signals.progress.emit),done);job.update_job='download';job.signals.progress.connect(self.gate_progress.setValue)

    def job_failed(self,payload):
        _,job=payload
        if getattr(job,'albums_job',False):
            self.jobs.discard(job)
            if job.albums_generation==self.album_generation:self.album_heading.setText('Не удалось загрузить альбомы · открой исполнителя ещё раз')
            return
        if getattr(job,'personal_reco',False):self.jobs.discard(job);self.reco_pending=False;return
        if getattr(job,'update_job',None)=='download' and getattr(self,'update_gate',None):self.gate_text.setText('Не удалось загрузить или проверить обновление. Проверь сеть и повтори.')
        super().job_failed(payload)
