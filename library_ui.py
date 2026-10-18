from PySide6.QtCore import Qt, Signal, QRectF, QPoint, QUrl, QObject,QVariantAnimation,QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPixmap, QFont, QPen
from PySide6.QtWidgets import (QWidget,QLabel,QHBoxLayout,QVBoxLayout,QListWidget,
    QListWidgetItem,QAbstractItemView,QPushButton)
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest
from skin import MetalButton,draw_icon
from glass import panel,border

LIBRARY_STYLE='''
QWidget#rail {background:#111A1E;border:1px solid #253238;border-radius:18px;}
QListWidget {border:0;background:transparent;outline:none;padding:0;}
QListWidget::item {border:0;background:transparent;padding:0;}
QListWidget::item:selected {background:transparent;}
QWidget#searchBox {background:#111A1E;border:1px solid #253238;border-radius:18px;}
QWidget#hero {background:#111A1E;border:1px solid #253238;border-radius:25px;}
QWidget#tourCard {background:#111A1E;border:1px solid #45424a;border-radius:18px;}
'''


class ElidedLabel(QLabel):
    def __init__(self,text='',parent=None):
        super().__init__('',parent)
        self.full_text=text
        self.setMinimumWidth(0)
        self.setText(text)

    def setText(self,text):
        self.full_text=str(text)
        self.setToolTip(self.full_text)
        self.refresh()

    def refresh(self):
        QLabel.setText(self,self.fontMetrics().elidedText(self.full_text,Qt.TextElideMode.ElideRight,max(20,self.width())))

    def resizeEvent(self,event):
        self.refresh()
        super().resizeEvent(event)


class SoftSurface(QWidget):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.hover_value=0.;self.touch_value=0.
        self.hover_motion=QVariantAnimation(self);self.hover_motion.setDuration(200);self.hover_motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hover_motion.valueChanged.connect(self.set_hover)
        self.touch_motion=QVariantAnimation(self);self.touch_motion.setDuration(260);self.touch_motion.valueChanged.connect(self.set_touch)
    def set_hover(self,value):self.hover_value=float(value);self.update()
    def set_touch(self,value):self.touch_value=float(value);self.update()
    def fade(self,animation,start,end):
        animation.stop();animation.setStartValue(start);animation.setEndValue(end);animation.start()
    def enterEvent(self,event):self.fade(self.hover_motion,self.hover_value,1.);super().enterEvent(event)
    def leaveEvent(self,event):self.fade(self.hover_motion,self.hover_value,0.);super().leaveEvent(event)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.fade(self.touch_motion,self.touch_value,1.)
        super().mousePressEvent(event)
    def mouseReleaseEvent(self,event):
        self.fade(self.touch_motion,max(.6,self.touch_value),0.);super().mouseReleaseEvent(event)


class Artwork(QWidget):
    def __init__(self,size=48,hero=False,parent=None):
        super().__init__(parent)
        self.setFixedSize(size,size)
        self.pixmap=None
        self.hero=hero
        self.seed=0

    def setPixmap(self,pixmap):
        self.pixmap=pixmap
        self.update()

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(self.rect()).adjusted(.5,.5,-.5,-.5)
        path=QPainterPath();path.addRoundedRect(rect,16 if self.hero else 9,16 if self.hero else 9)
        p.setClipPath(path)
        if self.pixmap:
            pix=self.pixmap.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap((self.width()-pix.width())//2,(self.height()-pix.height())//2,pix)
        else:
            gradient=QLinearGradient(0,0,self.width(),self.height())
            gradient.setColorAt(0,QColor('#212026') if self.hero else QColor.fromHsl(self.seed%360,30,44))
            gradient.setColorAt(1,QColor('#0c0d10'))
            p.fillPath(path,gradient)
            s=self.width()*(.40 if self.hero else .48)
            p.translate((self.width()-s)/2,(self.height()-s)/2)
            draw_icon(p,'heart' if self.hero else 'queue',QColor('#dd929d' if self.hero else '#a4a3ac'),s)


class CoverLoader(QObject):
    def __init__(self,parent):
        super().__init__(parent)
        self.network=QNetworkAccessManager(self)
        self.cache={}

    def load(self,url,target):
        if not url:return
        target.cover_url=url
        qurl=QUrl(url)
        if qurl.scheme()!='https' or not qurl.host() or qurl.userInfo():
            return
        if url in self.cache:
            target.setPixmap(self.cache[url]);return
        request=QNetworkRequest(qurl);request.setTransferTimeout(6500)
        reply=self.network.get(request)
        reply.downloadProgress.connect(lambda received,total:reply.abort() if received>8*1024*1024 else None)
        def done():
            if reply.error()==reply.NetworkError.NoError:
                image=QPixmap();image.loadFromData(bytes(reply.readAll()))
                if not image.isNull():
                    if image.width()>640 or image.height()>640:image=image.scaled(640,640,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                    if sum(p.width()*p.height()*4 for p in self.cache.values())>24*1024*1024:self.cache.clear()
                    self.cache[url]=image
                    try:
                        if getattr(target,'cover_url',None)==url:target.setPixmap(image)
                    except RuntimeError:pass
            reply.deleteLater()
        reply.finished.connect(done)


class TrackRow(SoftSurface):
    activated=Signal(int)
    favorite=Signal(int)
    def __init__(self,index,row,liked,loader,parent=None):
        super().__init__(parent)
        self.index=index
        self.hovered=False
        self.selected=False
        self.setFixedHeight(70)
        layout=QHBoxLayout(self)
        layout.setContentsMargins(12,10,16,10)
        layout.setSpacing(12)
        self.art=Artwork(48)
        self.art.seed=sum(map(ord,row['title']))
        layout.addWidget(self.art)
        loader.load(row.get('cover'),self.art)
        words=QVBoxLayout();words.setSpacing(3);words.setContentsMargins(0,0,0,0)
        title=ElidedLabel(row['title']);title.setFont(QFont('Manrope',11,QFont.Weight.DemiBold))
        artist=ElidedLabel(row['artist']);artist.setStyleSheet('font-family:Segoe UI;font-size:13px;font-weight:500;color:#c3c6d1;')
        words.addWidget(title);words.addWidget(artist)
        layout.addLayout(words,1)
        self.like=MetalButton(icon='heart')
        self.like.setCheckable(True);self.like.setChecked(liked)
        self.like.setToolTip('В избранное плеера')
        self.like.clicked.connect(lambda:self.favorite.emit(self.index))
        heart_host=QWidget();heart_host.setFixedSize(38,38);self.like.setParent(heart_host)
        self.like.setVisible(liked);layout.addWidget(heart_host)
        duration=QLabel(f"{int(row['duration'])//60000}:{int(row['duration'])//1000%60:02}" if row['duration'] else '—')
        duration.setStyleSheet('font-family:Segoe UI;font-size:13px;font-weight:500;color:#c3c6d1;')
        duration.setMinimumWidth(36);duration.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(duration)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self,event):
        self.like.show()
        self.hovered=True;self.update();super().enterEvent(event)

    def leaveEvent(self,event):
        self.like.setVisible(self.like.isChecked())
        self.hovered=False;self.update();super().leaveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.activated.emit(self.index)
        super().mouseReleaseEvent(event)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        k=self.hover_value;touch=self.touch_value
        p.setBrush(panel(36 if self.selected else int(16*k+22*touch)))
        p.setPen(QPen(QColor(255,255,255,65) if self.selected else border(),1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),14,14)


class TrackList(QListWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setSpacing(5)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.currentRowChanged.connect(self.selection_changed)

    def selection_changed(self,row):
        for i in range(self.count()):
            widget=self.itemWidget(self.item(i))
            if widget:widget.selected=(row==i);widget.update()


class TourOverlay(QWidget):
    finished=Signal()
    def __init__(self,parent,steps,on_done):
        super().__init__(parent)
        self.steps=steps;self.index=0;self.revealed=False;self.on_done=on_done
        self.setGeometry(parent.rect())
        self.card=QWidget(self);self.card.setObjectName('tourCard');self.card.setFixedWidth(350)
        box=QVBoxLayout(self.card);box.setContentsMargins(20,17,20,17);box.setSpacing(13)
        self.counter=QLabel();self.counter.setStyleSheet('font-size:10px;color:#a797a7;letter-spacing:1px;')
        self.title=QLabel();self.title.setStyleSheet('font-size:20px;font-weight:600;')
        self.text=QLabel();self.text.setWordWrap(True);self.text.setMinimumHeight(55);self.text.setStyleSheet('color:#bfc0c8;font-size:13px;')
        box.addWidget(self.counter);box.addWidget(self.title);box.addWidget(self.text)
        actions=QHBoxLayout()
        self.next=MetalButton('Далее',primary=True);self.next.clicked.connect(self.advance)
        actions.addStretch();actions.addWidget(self.next)
        box.addLayout(actions)
        self.update_step()
        self.show();self.raise_()

    def target_rect(self):
        widget=self.steps[self.index][0]
        pos=widget.mapTo(self.parentWidget(),QPoint(0,0))
        return QRectF(pos.x(),pos.y(),widget.width(),widget.height()).adjusted(-6,-6,6,6)

    def update_step(self):
        _,title,description,_=self.steps[self.index]
        self.counter.setText(f'ЗНАКОМСТВО С PULSE · {self.index+1} / {len(self.steps)}')
        self.title.setText(title)
        self.text.setText(description if self.revealed else 'Нажми на подсвеченную кнопку, чтобы узнать, как она работает.')
        self.next.setVisible(self.revealed)
        self.next.setText('Готово' if self.index==len(self.steps)-1 else 'Далее')
        self.card.adjustSize()
        rect=self.target_rect()
        x=min(max(18,int(rect.right()+20)),self.width()-self.card.width()-18)
        y=min(max(18,int(rect.center().y()-self.card.height()/2)),self.height()-self.card.height()-18)
        if x<rect.right() and rect.top()<y+self.card.height() and rect.bottom()>y:
            y=max(18,int(rect.top()-self.card.height()-22))
        self.card.move(x,y)
        self.update()

    def mouseReleaseEvent(self,event):
        if self.target_rect().contains(event.position()):
            self.revealed=True
            action=self.steps[self.index][3]
            if action:action()
            self.update_step()

    def advance(self):
        if not self.revealed:return
        if self.index==len(self.steps)-1:self.finish();return
        self.index+=1;self.revealed=False;self.update_step()

    def finish(self):
        if not self.revealed or self.index!=len(self.steps)-1:return
        self.on_done();self.finished.emit();self.deleteLater()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path=QPainterPath();path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addRect(QRectF(self.rect()));path.addRoundedRect(self.target_rect(),15,15)
        p.fillPath(path,QColor(0,0,0,192))
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('#dfbcc9'),1.5))
        p.drawRoundedRect(self.target_rect(),15,15)
