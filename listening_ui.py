import bisect,math
from PySide6.QtCore import Qt,Signal,QRectF,QPointF,QVariantAnimation,QEasingCurve
from PySide6.QtGui import QPainter,QColor,QFont,QTextLayout,QTextCharFormat,QLinearGradient,QPixmap,QIcon
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QSlider,QSizePolicy,QStackedWidget
from skin import MetalButton
from library_ui import Artwork,ElidedLabel
from pages import InAppPage

class TitleBar(QWidget):
    def __init__(self,player):
        super().__init__();self.player=player;self.setFixedHeight(38);self.setObjectName('titleBar')
        box=QHBoxLayout(self);box.setContentsMargins(10,0,0,0);box.setSpacing(8)
        logo=QLabel();logo.setPixmap(player.windowIcon().pixmap(20,20));box.addWidget(logo)
        label=QLabel('Pulse');label.setStyleSheet('font-family:Manrope;font-size:12px;font-weight:600;letter-spacing:.4px;color:#a5a4af');box.addWidget(label);box.addStretch()
        for glyph,tip,fn in [('minus','Свернуть',player.showMinimized),('maximize','Развернуть',self.maximize),('close','Закрыть',player.close)]:
            b=MetalButton(icon=glyph);b.setFixedSize(42,32);b.setToolTip(tip);b.clicked.connect(fn);box.addWidget(b)
    def maximize(self):self.player.showNormal() if self.player.isMaximized() else self.player.showMaximized()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.player.windowHandle():self.player.windowHandle().startSystemMove()
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.maximize()

class ClickArtwork(Artwork):
    clicked=Signal()
    def __init__(self,size=48):super().__init__(size);self.setCursor(Qt.CursorShape.PointingHandCursor)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.clicked.emit()

class LyricsCanvas(QWidget):
    seeked=Signal(int)
    def __init__(self):
        super().__init__();self.lines=[];self.times=[];self.layouts=[];self.positions=[];self.active=-1;self.word=-1;self.previous_word=-1;self.position=0;self.offset=0.;self.blend=1.
        self.message='Выбери трек';self.setMinimumWidth(260);self.setMinimumHeight(280)
        self.scroll=QVariantAnimation(self);self.scroll.setDuration(460);self.scroll.setEasingCurve(QEasingCurve.Type.OutCubic);self.scroll.valueChanged.connect(self.scrolled)
        self.word_motion=QVariantAnimation(self);self.word_motion.setDuration(150);self.word_motion.valueChanged.connect(self.blended)
    def scrolled(self,value):self.offset=float(value);self.update()
    def blended(self,value):self.blend=float(value);self.update()
    def set_data(self,data):
        self.scroll.stop();self.word_motion.stop();self.offset=0.;self.active=-1;self.word=-1;self.previous_word=-1
        self.lines=data.get('lines',[]);self.untimed=not self.lines and bool(data.get('plain'))
        if self.untimed:self.lines=[{'time':0,'text':line,'words':[]} for line in data['plain'].splitlines()[:1500]]
        self.times=[r['time'] for r in self.lines]
        self.message='В этом треке нет вокала' if data.get('instrumental') else 'Текст пока не найден' if data.get('missing') else data.get('plain') or 'Текст загружается…'
        self.relayout();self.set_position(self.position);self.update()
    def relayout(self):
        self.layouts=[];self.positions=[];y=0;self.font=QFont('Manrope',22,QFont.Weight.DemiBold)
        for row in self.lines:
            text=QTextLayout(row['text'] or '♪',self.font);text.beginLayout();h=0
            while True:
                line=text.createLine()
                if not line.isValid():break
                line.setLineWidth(max(120,self.width()-52));line.setPosition(QPointF(0,h));h+=line.height()+3
            text.endLayout();self.layouts.append(text);self.positions.append(y);y+=max(84,h+34)
        self.total_height=y
    def set_position(self,position):
        self.position=position
        if not self.lines or getattr(self,'untimed',False):return
        index=bisect.bisect_right(self.times,position)-1
        if index!=self.active:
            self.active=index;self.previous_word=-1;self.word=-1
            target=self.positions[max(0,index)]
            self.scroll.stop();self.scroll.setStartValue(self.offset);self.scroll.setEndValue(float(target));self.scroll.start()
        if index>=0:
            words=self.lines[index].get('words',[]);word=bisect.bisect_right([w['time'] for w in words],position)-1
            if word>=0 and words[word].get('end') is not None and position>=words[word]['end']:word=-1
            if word!=self.word:
                self.previous_word=self.word;self.word=word;self.word_motion.stop();self.word_motion.setStartValue(0.);self.word_motion.setEndValue(1.);self.word_motion.start()
        self.update()
    def resizeEvent(self,event):
        self.relayout()
        if self.active>=0:self.offset=float(self.positions[self.active])
        super().resizeEvent(event)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.lines:
            p.setFont(QFont('Manrope',15));p.setPen(QColor('#9a9ca9'));p.drawText(QRectF(self.rect()).adjusted(20,20,-20,-20),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,self.message[:18000]);return
        center=self.height()*.4
        for i,layout in enumerate(self.layouts):
            y=center+self.positions[i]-self.offset
            if y < -150 or y>self.height()+80:continue
            distance=abs(y-center);alpha=max(.14,1-distance/max(1,self.height()*.7));p.setOpacity(alpha)
            active=i==self.active;words=self.lines[i].get('words',[])
            base=QTextCharFormat();base.setForeground(QColor('#b8b9c6' if active and words else '#f2f2fa' if active else '#6f7383'))
            whole=QTextLayout.FormatRange();whole.start=0;whole.length=len(self.lines[i]['text'].encode('utf-16-le'))//2;whole.format=base;formats=[whole]
            if active and words:
                offset=0
                for j,word in enumerate(words):
                    length=len(word['text'].encode('utf-16-le'))//2
                    strength=self.blend if j==self.word else 1-self.blend if j==self.previous_word else 0
                    f=QTextCharFormat();f.setForeground(QColor(int(160+95*strength),int(167+88*strength),int(190+65*strength)))
                    item=QTextLayout.FormatRange();item.start=offset;item.length=length;item.format=f;formats.append(item);offset+=length
            layout.setFormats(formats);layout.beginLayout();height=0
            while True:
                line=layout.createLine()
                if not line.isValid():break
                line.setLineWidth(max(120,self.width()-52));line.setPosition(QPointF(0,height));height+=line.height()+3
            layout.endLayout();layout.draw(p,QPointF(24,y))
        p.setOpacity(1)
    def wheelEvent(self,event):
        if getattr(self,'untimed',False):
            self.offset=max(0,min(max(0,self.total_height-self.height()*.5),self.offset-event.angleDelta().y()));self.update();event.accept()
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or not self.lines or getattr(self,'untimed',False):return
        y=event.position().y()-self.height()*.4+self.offset
        index=max(0,min(len(self.lines)-1,bisect.bisect_right(self.positions,y)-1));self.seeked.emit(self.times[index])

class ListeningPage(InAppPage):
    def __init__(self,player):
        super().__init__(player.content_host,'Сейчас играет');self.player=player
        self.setStyleSheet('QWidget#inAppPage{background:#091017;border:1px solid #252a35;border-radius:22px;}')
        box=QHBoxLayout(self.body);box.setContentsMargins(24,16,24,20);box.setSpacing(32)
        left=QWidget();left.setMinimumWidth(320);left.setMaximumWidth(480);panel=QVBoxLayout(left);panel.setContentsMargins(0,0,0,0);panel.setSpacing(15);panel.addStretch()
        self.art=Artwork(300,hero=True);panel.addWidget(self.art,0,Qt.AlignmentFlag.AlignHCenter)
        self.title=ElidedLabel();self.title.setStyleSheet('font-size:23px;font-weight:800');self.title.setAlignment(Qt.AlignmentFlag.AlignCenter);panel.addWidget(self.title)
        self.artist=ElidedLabel();self.artist.setStyleSheet('font-size:14px;color:#a1a6b6');self.artist.setAlignment(Qt.AlignmentFlag.AlignCenter);panel.addWidget(self.artist)
        self.timeline=QSlider(Qt.Orientation.Horizontal);self.timeline.sliderReleased.connect(lambda:player.media.setPosition(self.timeline.value()));panel.addWidget(self.timeline)
        timing=QHBoxLayout();self.time=QLabel('0:00');self.duration=QLabel('0:00');timing.addWidget(self.time);timing.addStretch();timing.addWidget(self.duration);panel.addLayout(timing)
        controls=QHBoxLayout();controls.setSpacing(13);controls.addStretch()
        self.like=player.icon_button('heart','Любимый трек',player.favorite_current);self.like.setCheckable(True);controls.addWidget(self.like)
        controls.addWidget(player.icon_button('previous','Предыдущий',lambda:player.step(-1)))
        self.play=player.icon_button('play','Воспроизведение / пауза',player.toggle);self.play.setFixedSize(58,58);controls.addWidget(self.play)
        controls.addWidget(player.icon_button('next','Следующий',lambda:player.step(1)))
        controls.addWidget(player.icon_button('queue','Очередь',player.show_queue));controls.addStretch();panel.addLayout(controls)
        self.toggle_lyrics=player.button('Показать текст песни',self.show_lyrics);panel.addWidget(self.toggle_lyrics,0,Qt.AlignmentFlag.AlignHCenter);panel.addStretch();box.addWidget(left,1)
        self.lyrics_host=QWidget();lyrics=QVBoxLayout(self.lyrics_host);lyrics.setContentsMargins(0,0,0,0)
        label=QLabel('Текст песни');label.setStyleSheet('font-size:20px;font-weight:800');lyrics.addWidget(label)
        self.caption=QLabel();self.caption.setStyleSheet('color:#8c92a4;font-size:11px');self.caption.setWordWrap(True);lyrics.addWidget(self.caption)
        self.canvas=LyricsCanvas();self.canvas.seeked.connect(player.media.setPosition);lyrics.addWidget(self.canvas,1)
        self.lyrics_host.hide();box.addWidget(self.lyrics_host,1)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'art'):
            size=max(200,min(380,self.height()-350));self.art.setFixedSize(size,size)
    def show_lyrics(self):
        self.lyrics_host.setVisible(not self.lyrics_host.isVisible());self.toggle_lyrics.setText('Скрыть текст' if self.lyrics_host.isVisible() else 'Показать текст песни')
        if self.lyrics_host.isVisible():self.player.load_lyrics()
    def update_row(self,row):
        self.title.setText(row['title']);self.artist.setText(row['artist']);self.art.pixmap=None;self.art.update()
        url=row.get('cover')
        if url:self.player.cover_loader.load(url.replace('100x100','600x600'),self.art)
        self.like.setChecked(row['id'] in self.player.favorites)
    def update_position(self,position,duration):
        if not self.isVisible():return
        self.timeline.setRange(0,duration)
        if not self.timeline.isSliderDown():self.timeline.setValue(position)
        def clock(ms):s=max(0,ms)//1000;return f'{s//60}:{s%60:02}'
        self.time.setText(clock(position));self.duration.setText(clock(duration))
        if self.lyrics_host.isVisible():self.canvas.set_position(position)
