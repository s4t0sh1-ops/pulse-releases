"""User-owned local playlists, independent of provider libraries and playback queues."""
import json,uuid,copy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QInputDialog,QLineEdit,QMessageBox
from pages import InAppPage,CollectionTile


class Playlists:
    def __init__(self):
        self.playlists={};self.active_playlist=None
        try:
            data=json.loads((self.data_dir/'playlists.json').read_text(encoding='utf8'))
            if isinstance(data,dict):self.playlists={k:v for k,v in data.items() if isinstance(v,dict) and isinstance(v.get('tracks'),list)}
        except (OSError,ValueError):pass
        super().__init__()
        tile=CollectionTile('Мои плейлисты','Твои подборки музыки','queue');tile.activated.connect(self.show_playlists)
        # Same compact row as history and favorites; no additional height above songs.
        self.home_panel.layout().itemAt(1).layout().addWidget(tile)

    def persist_playlists(self):self.save_data('playlists.json',self.playlists)

    def create_playlist(self,name):
        name=name.strip()
        if not name or len(name)>80:raise ValueError('Название: от 1 до 80 символов')
        identity=uuid.uuid4().hex;self.playlists[identity]={'name':name,'tracks':[]};self.persist_playlists();return identity

    def add_to_playlist(self,identity,row):
        rows=self.playlists[identity]['tracks']
        if any(r['id']==row['id'] for r in rows):return False
        rows.insert(0,copy.deepcopy(row));self.persist_playlists();return True

    def playlist_name(self,title,value=''):
        dialog=QInputDialog(self);dialog.setWindowTitle(title);dialog.setLabelText('Название плейлиста');dialog.setTextValue(value)
        dialog.setOkButtonText('Сохранить');dialog.setCancelButtonText('Отмена');dialog.findChild(QLineEdit).setMaxLength(80)
        if dialog.exec() and dialog.textValue().strip():return dialog.textValue().strip()

    def new_playlist(self,row=None):
        name=self.playlist_name('Новый плейлист')
        if not name:return
        identity=self.create_playlist(name)
        if row is not None:self.add_to_playlist(identity,row)
        self.open_playlist(identity)

    def show_playlists(self):
        self.hide_pages()
        page=InAppPage(self.content_host,'Мои плейлисты');self.extra_pages.append(page)
        box=QVBoxLayout(page.body);box.setSpacing(12);box.addWidget(self.button('Создать плейлист',lambda:self.new_playlist()))
        for identity,p in sorted(self.playlists.items(),key=lambda kv:kv[1]['name'].casefold()):
            tile=CollectionTile(p['name'],f"{len(p['tracks'])} треков",'queue');tile.activated.connect(lambda key=identity:self.open_playlist(key));box.addWidget(tile)
        if not self.playlists:
            label=QLabel('Создай плейлист. Добавляй песни через ПКМ → «В плейлист».');label.setWordWrap(True);box.addWidget(label)
        box.addStretch();page.show()

    def open_playlist(self,identity):
        if identity not in self.playlists:return
        self.hide_pages();self.search_version+=1;self.view='playlist';self.active_playlist=identity
        self.search_box.hide();self.suggestions.hide();self.artist_shelf.hide();self.home_panel.hide();self.library_hero.show();self.more_artist.hide()
        p=self.playlists[identity];self.render(list(p['tracks']));self.heading.setText(p['name']);self.status.setText('ПКМ по песне — добавить или убрать из плейлиста.')
        if hasattr(self,'playlist_tools'):self.playlist_tools.show()

    def rename_playlist(self):
        identity=self.active_playlist
        if identity not in self.playlists:return
        name=self.playlist_name('Переименовать плейлист',self.playlists[identity]['name'])
        if name:self.playlists[identity]['name']=name;self.persist_playlists();self.open_playlist(identity)

    def delete_playlist(self):
        identity=self.active_playlist
        if identity not in self.playlists:return
        dialog=QMessageBox(self);dialog.setWindowTitle('Удалить плейлист?');dialog.setText('Удалить «'+self.playlists[identity]['name']+'»?')
        dialog.setInformativeText('Песни останутся в источниках и любимом.');yes=dialog.addButton('Удалить',QMessageBox.ButtonRole.DestructiveRole);dialog.addButton('Отмена',QMessageBox.ButtonRole.RejectRole);dialog.exec()
        if dialog.clickedButton() is yes:
            del self.playlists[identity];self.persist_playlists();self.active_playlist=None;self.show_playlists()

    def remove_from_playlist(self,row):
        identity=self.active_playlist
        if identity not in self.playlists:return
        self.playlists[identity]['tracks']=[r for r in self.playlists[identity]['tracks'] if r['id']!=row['id']];self.persist_playlists();self.open_playlist(identity)

    def render(self,rows):
        super().render(rows)
        if not hasattr(self,'library_hero'):return
        if not hasattr(self,'playlist_tools'):
            self.playlist_tools=QWidget();box=QHBoxLayout(self.playlist_tools);box.setContentsMargins(0,0,0,0)
            box.addWidget(self.button('Все плейлисты',self.show_playlists));box.addStretch();box.addWidget(self.button('Переименовать',self.rename_playlist));box.addWidget(self.button('Удалить плейлист',self.delete_playlist))
            self.content_host.layout().insertWidget(self.content_host.layout().indexOf(self.library_hero)+1,self.playlist_tools)
        self.playlist_tools.setVisible(self.view=='playlist')

    def track_menu(self,index,pos):
        super().track_menu(index,pos)
        if not 0<=index<len(self.rows):return
        row=copy.deepcopy(self.rows[index]);menu=self.active_menu.addMenu('В плейлист')
        menu.addAction('Создать новый…').triggered.connect(lambda:self.new_playlist(row))
        if self.playlists:menu.addSeparator()
        for identity,p in sorted(self.playlists.items(),key=lambda kv:kv[1]['name'].casefold()):
            action=menu.addAction(p['name']);action.triggered.connect(lambda checked=False,key=identity:self.add_to_playlist(key,row))
            action.setEnabled(not any(r['id']==row['id'] for r in p['tracks']))
        if self.view=='playlist':self.active_menu.addAction('Убрать из этого плейлиста').triggered.connect(lambda:self.remove_from_playlist(row))
