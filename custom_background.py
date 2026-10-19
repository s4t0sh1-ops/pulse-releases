"""Local image backgrounds: bounded decoding, app-owned copy and no network upload."""
from pathlib import Path
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QImageReader,QPixmap,QPainter,QColor,QRadialGradient
from PySide6.QtWidgets import QWidget,QFileDialog

class ImageBackground(QWidget):
    def __init__(self,parent,data):
        super().__init__(parent);self.data=data;self.pixmap=QPixmap();self.fitted=QPixmap();self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    def load(self,path):
        self.pixmap=QPixmap(str(path));self.fit()
    def fit(self):
        self.fitted=self.pixmap.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation) if not self.pixmap.isNull() and self.width()>0 else QPixmap();self.update()
    def resizeEvent(self,event):self.fit();super().resizeEvent(event)
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#08090b'))
        if self.fitted.isNull():return
        p.drawPixmap((self.width()-self.fitted.width())//2,(self.height()-self.fitted.height())//2,self.fitted)
        p.fillRect(self.rect(),QColor(0,0,0,int(255*(1-float(self.data.get('intensity',.55))))))
        edge=QRadialGradient(self.rect().center(),max(self.width(),self.height())*.7);edge.setColorAt(.25,QColor(0,0,0,0));edge.setColorAt(1,QColor(0,0,0,int(180*self.data.get('edge',.8))));p.fillRect(self.rect(),edge)

def choose_background(manager):
    path,_=QFileDialog.getOpenFileName(manager.player,'Выбрать свой фон','','Изображения (*.png *.jpg *.jpeg *.webp *.bmp)')
    if not path:return
    try:
        reader=QImageReader(path);reader.setAutoTransform(True);size=reader.size()
        if size.width()<1 or size.height()<1:raise ValueError()
        size.scale(QSize(2560,2560),Qt.AspectRatioMode.KeepAspectRatio);reader.setScaledSize(size);image=reader.read()
        if image.isNull():raise ValueError()
        folder=manager.player.data_dir;folder.mkdir(parents=True,exist_ok=True);target=folder/'custom-background.jpg';tmp=folder/'custom-background.tmp.jpg'
        if not image.save(str(tmp),'JPEG',92):raise ValueError()
        tmp.replace(target);manager.data['custom_file']=str(target);manager.data['effect']='custom'
        if manager.custom:manager.custom.loaded_path=None
        manager.selector.setCurrentIndex(list(__import__('backgrounds_ui').NAMES).index('custom'));manager.rebuild();manager.save()
    except Exception:manager.player.status.setText('Не удалось открыть изображение. Выбери PNG, JPG или WebP.')
