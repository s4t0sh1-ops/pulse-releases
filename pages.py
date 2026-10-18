from PySide6.QtCore import Qt,Signal,QRectF,QPointF
from PySide6.QtGui import QPainter,QColor,QLinearGradient,QPen,QPainterPath,QFont
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QScrollArea,QSizePolicy
from skin import MetalButton,draw_icon
from library_ui import Artwork,ElidedLabel,SoftSurface
from glass import panel,border


class InAppPage(QWidget):
    finished=Signal(int)
    rejected=Signal()
    def __init__(self,parent,title=''):
        super().__init__(parent)
        self.hidden_siblings={}
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        self.setObjectName('inAppPage')
        self.setStyleSheet('QWidget#inAppPage {background:rgba(18,18,23,175);border:1px solid rgba(255,255,255,28);border-radius:20px;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(22,16,22,20)
        header=QHBoxLayout()
        back=MetalButton(icon='previous');self.back_button=back;back.setToolTip('Назад');back.clicked.connect(self.reject);header.addWidget(back)
        self.page_title=QLabel(title);self.page_title.setStyleSheet('font-size:21px;font-weight:600;');header.addWidget(self.page_title);header.addStretch()
        close=MetalButton(icon='close');self.close_button=close;close.clicked.connect(self.reject);header.addWidget(close)
        layout.addLayout(header)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(scroll.Shape.NoFrame)
        self.body=QWidget();scroll.setWidget(self.body);layout.addWidget(scroll,1)
        self.hide()

    def setWindowTitle(self,title):
        self.page_title.setText(title)

    def show(self):
        for page in self.parentWidget().findChildren(InAppPage,options=Qt.FindChildOption.FindDirectChildrenOnly):
            if page is not self:page.hide()
        self.suppress_siblings()
        self.setGeometry(self.parentWidget().rect());super().show();self.raise_()

    def suppress_siblings(self):
        for widget in self.parentWidget().findChildren(QWidget,options=Qt.FindChildOption.FindDirectChildrenOnly):
            if widget is self or isinstance(widget,InAppPage):continue
            if widget.__class__.__name__ in ('VortexGL','EffectView','TitleBar'):continue
            if widget.isVisible():self.hidden_siblings[widget]=True;widget.hide()

    def hide(self):
        super().hide()
        pending=self.hidden_siblings;self.hidden_siblings={}
        for widget,visible in pending.items():
            try:widget.setVisible(visible)
            except RuntimeError:pass

    def accept(self):self.hide();self.finished.emit(1)
    def reject(self):self.hide();self.rejected.emit();self.finished.emit(0)
    def closeEvent(self,event):self.hide();self.finished.emit(0);event.accept()


class ArtistCard(SoftSurface):
    activated=Signal(object)
    def __init__(self,artist,loader):
        super().__init__()
        self.artist=artist;self.setFixedWidth(210)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        box=QHBoxLayout(self);box.setContentsMargins(7,8,7,8);box.setSpacing(9)
        art=Artwork(42);box.addWidget(art);loader.load(artist.get('cover'),art)
        words=QVBoxLayout();words.setSpacing(1)
        name=ElidedLabel(artist['name']);name.setFont(QFont('Manrope',10,QFont.Weight.DemiBold));words.addWidget(name)
        caption=QLabel('Исполнитель');caption.setStyleSheet('color:#bfc1cd;font-size:13px;');words.addWidget(caption)
        box.addLayout(words,1)

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        if event.button()==Qt.MouseButton.LeftButton:self.activated.emit(self.artist)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        k=self.hover_value+self.touch_value
        p.setBrush(panel(int(16*k)));p.setPen(border());p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),12,12)


class WaveHero(QWidget):
    played=Signal()
    seed_played=Signal(object)
    def __init__(self,loader):
        super().__init__();self.setFixedHeight(292)
        box=QHBoxLayout(self);box.setContentsMargins(28,22,28,22);box.setSpacing(35)
        self.art=Artwork(156,hero=True);box.addWidget(self.art)
        text=QVBoxLayout();text.setSpacing(8);text.addStretch()
        label=QLabel('Моя\nволна');label.setStyleSheet('font-size:54px;font-weight:700;line-height:1;');text.addWidget(label)
        self.subtitle=QLabel('Обычная · по твоим вкусам');self.subtitle.setStyleSheet('color:#bfc1cd;font-size:13px;');text.addWidget(self.subtitle)
        text.addStretch();box.addLayout(text,1)
        right=QVBoxLayout();right.setSpacing(12);right.addStretch()
        self.seeds_title=QLabel('ТВОИ ПОСЛЕДНИЕ ВОЛНЫ');self.seeds_title.setStyleSheet('font-size:10px;letter-spacing:1.5px;color:#b1aebc;');right.addWidget(self.seeds_title)
        covers=QHBoxLayout();covers.setSpacing(10);self.preview_art=[WaveSeed(),WaveSeed(),WaveSeed()]
        for art in self.preview_art:
            art.clicked.connect(lambda checked=False,a=art:self.seed_played.emit(a.row) if a.row else None)
            covers.addWidget(art);art.hide()
        right.addLayout(covers)
        self.seed_hint=QLabel('ПКМ по треку → волна');self.seed_hint.setStyleSheet('font-size:10px;color:#928e9d;');right.addWidget(self.seed_hint)
        self.play=WavePlay();self.play.setToolTip('Включить мою волну');self.play.clicked.connect(self.played.emit)
        right.addWidget(self.play,0,Qt.AlignmentFlag.AlignRight);right.addStretch();box.addLayout(right)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g=QLinearGradient(0,0,self.width(),self.height());g.setColorAt(0,panel(13));g.setColorAt(1,panel(-26))
        p.setBrush(g);p.setPen(border());p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),24,24)
        p.setPen(QPen(QColor(218,211,231,20),3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        path=QPainterPath();w=self.width();h=self.height()
        path.moveTo(w*.69,h*.70);path.cubicTo(w*1.23,h*.17,w*1.03,-h*.1,w*.80,h*.32)
        path.cubicTo(w*.63,h*.61,w*1.21,h*.04,w*.93,h*.75)
        p.drawPath(path)


class WavePlay(MetalButton):
    def __init__(self):super().__init__(icon='play');self.setFixedSize(72,72)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(36,36+self.press_value);p.scale(1-self.press_value*.045,1-self.press_value*.045)
        p.setPen(QPen(QColor(255,255,255,65),1));p.setBrush(QColor('#605967' if self.hover_value>.3 else '#433e4c'))
        p.drawEllipse(QRectF(-35,-35,70,70))
        if self.pulse_value<1:
            p.setPen(QPen(QColor(155,235,245,int((1-self.pulse_value)*180)),2));p.setBrush(Qt.BrushStyle.NoBrush)
            r=23+self.pulse_value*12;p.drawEllipse(QRectF(-r,-r,r*2,r*2))
        p.translate(-14,-14);draw_icon(p,self.glyph,QColor('white'),28)


class WaveSeed(MetalButton):
    def __init__(self):
        super().__init__(icon='play');self.setFixedSize(66,66);self.row=None;self.pixmap=None
    def setPixmap(self,pixmap):self.pixmap=pixmap;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(33,33+self.press_value);s=1+self.hover_value*.035-self.press_value*.065;p.scale(s,s)
        rect=QRectF(-30,-30,60,60);path=QPainterPath();path.addRoundedRect(rect,13,13);p.setClipPath(path)
        if self.pixmap and not self.pixmap.isNull():
            image=self.pixmap.scaled(66,66,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(-image.width()//2,-image.height()//2,image)
        else:p.fillRect(rect,panel(35))
        p.fillRect(rect,QColor(0,0,0,int(50+self.hover_value*45)))
        p.setOpacity(.5+.5*self.hover_value);p.translate(-10,-10);draw_icon(p,'play',QColor('white'),20)


class CollectionTile(SoftSurface):
    activated=Signal()
    def __init__(self,title,subtitle,icon):
        super().__init__();self.setFixedHeight(65);self.setCursor(Qt.CursorShape.PointingHandCursor)
        box=QHBoxLayout(self);box.setContentsMargins(17,10,15,10)
        glyph=MetalButton(icon=icon);glyph.clicked.connect(self.activated.emit);box.addWidget(glyph)
        words=QVBoxLayout();words.setSpacing(2)
        name=QLabel(title);name.setStyleSheet('font-size:15px;font-weight:600;');words.addWidget(name)
        text=QLabel(subtitle);text.setStyleSheet('font-family:Segoe UI;font-size:13px;font-weight:500;color:#c3c6d1;');words.addWidget(text)
        box.addLayout(words,1)
    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        if event.button()==Qt.MouseButton.LeftButton:self.activated.emit()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        k=self.hover_value+self.touch_value
        p.setBrush(panel(int(18*k)));p.setPen(border());p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),14,14)
