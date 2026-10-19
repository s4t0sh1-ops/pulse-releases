"""Compact album controls. The track list keeps priority on short windows."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QAbstractButton,QLabel,QVBoxLayout,QScrollArea
from library_ui import Artwork

class AlbumCard(QAbstractButton):
    def __init__(self,album,loader,activate,parent=None):
        super().__init__(parent);self.setObjectName('albumCard');self.setFixedSize(132,126)
        self.setCursor(Qt.CursorShape.PointingHandCursor);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Альбом '+album['title']);self.setToolTip(album['title']+(' · '+album['year'] if album.get('year') else ''))
        box=QVBoxLayout(self);box.setContentsMargins(8,5,8,5);box.setSpacing(6)
        art=Artwork(76);art.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);loader.load(album.get('cover'),art);box.addWidget(art)
        title=QLabel();title.setWordWrap(True);title.setFixedSize(116,34);title.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft);title.setStyleSheet('font-size:12px;font-weight:600;color:#e7e3ea;background:transparent;');title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        metrics=QFontMetrics(title.font());value=album['title'];lines=[]
        while value and len(lines)<2:
            if metrics.horizontalAdvance(value)<=116:lines.append(value);break
            if len(lines)==1:lines.append(metrics.elidedText(value,Qt.TextElideMode.ElideRight,116));break
            n=len(value)
            while n>1 and metrics.horizontalAdvance(value[:n])>116:n-=1
            split=value.rfind(' ',0,n+1);n=split if split>0 else n;lines.append(value[:n].strip());value=value[n:].lstrip()
        title.setText('\n'.join(lines));box.addWidget(title)
        self.setStyleSheet('QAbstractButton#albumCard{background:transparent;border:1px solid transparent;border-radius:12px;}QAbstractButton#albumCard:hover{background:rgba(255,255,255,10);}QAbstractButton#albumCard:focus{border-color:#a99bac;}')
        self.clicked.connect(lambda:activate(album))
    def paintEvent(self,event):
        from PySide6.QtWidgets import QStylePainter,QStyleOption,QStyle
        painter=QStylePainter(self);option=QStyleOption();option.initFrom(self);painter.drawPrimitive(QStyle.PrimitiveElement.PE_Widget,option)

class AlbumScroll(QScrollArea):
    def wheelEvent(self,event):
        delta=event.angleDelta().x() or event.angleDelta().y()
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-delta)
        event.accept()
