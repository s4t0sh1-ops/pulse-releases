"""Local, unmodified React Bits components hosted behind the native player."""
import copy,json,sys,time
from custom_background import ImageBackground,choose_background
from pathlib import Path
from PySide6.QtCore import Qt,QUrl,QTimer,QEvent
from PySide6.QtGui import QColor,QCursor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QSlider,QCheckBox,QLineEdit,QGroupBox
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile,QWebEngineUrlRequestInterceptor

# label, property, default, minimum, maximum, step. Boolean/color controls are inferred.
SCHEMAS={
'chrome':[
 ('Цвет металла','color','#7c3aed'),('Скорость','speed',.2,0,3,.01),('Сила изгибов','amplitude',.3,0,2,.01),
 ('Частота по горизонтали','frequencyX',3,.1,10,.1),('Частота по вертикали','frequencyY',3,.1,10,.1),
 ('Детализация','detail',4,1,8,1),('Толщина','thickness',1,.25,4,.01),('Глубина','depth',1,0,3,.01),
 ('Шероховатость','roughness',.3,0,1,.01),('Экспозиция','exposure',1,.1,3,.01),
 ('Реакция на курсор','interactive',True),('Сила ряби','rippleStrength',1,0,3,.01),('Размер ряби','rippleSize',1,.2,4,.01),
 ('Наклон за курсором','tilt',1,0,3,.01),('Плавное появление','intro',True),('Светлый металл','lightMode',False),
 ('Плотность пикселей','maxDevicePixelRatio',2,.5,3,.1)],
'veil':[
 ('Цвет','color','#6b12ff'),('Скорость','speed',.5,0,3,.01),('Масштаб','scale',.8,.1,3,.01),('Поворот','rotation',0,0,360,1),
 ('Течение','flow',1,0,3,.01),('Искажение','warp',0,0,3,.01),('Вариация','variation',0,0,10,.01),
 ('Яркость эффекта','brightness',1,0,3,.01),('Блеск','sheen',0,0,2,.01),('Свечение','glow',.4,0,2,.01),
 ('Зерно','grain',.03,0,.2,.001),('Качество','quality',.5,.25,1,.01),('Реакция на курсор','mouseInteraction',True),
 ('Сила реакции','mouseStrength',1,0,3,.01),('Плавное появление','intro',True),('Затухание','fade',0,0,1,.01),
 ('Непрозрачность','opacity',1,0,1,.01),('Светлый режим','lightMode',False),('Плотность пикселей','dpr',1,.5,2,.1)],
'silk':[
 ('Цвет ткани','color','#7B7481'),('Цвет бликов','sheenColor','#ffffff'),('Скорость','speed',5,0,10,.1),
 ('Масштаб','scale',1,.1,5,.01),('Шум','noiseIntensity',1.5,0,5,.01),('Поворот','rotation',0,0,6.283,.01),
 ('Блеск','sheen',.5,0,2,.01),('Глубина','depth',.5,0,1,.01),('Свечение','glow',.3,0,2,.01),
 ('Рябь','ripple',1,0,3,.01),('Волны','wave',1,0,3,.01),('Вариация','variation',0,0,10,.01),
 ('Реакция на курсор','mouseInteraction',True),('Сила реакции','interactionStrength',1,0,3,.01),
 ('Рябь от нажатия','clickRipple',True),('Плавное появление','intro',True),('Затухание','fade',0,0,1,.01),
 ('Светлый режим','lightMode',False),('Плотность пикселей','dpr',1,.5,2,.1)],
'iridescence':[
 ('Оттенок','color','#ffffff'),('Скорость','speed',1,0,5,.01),('Амплитуда','amplitude',.1,0,1,.01),
 ('Реакция на курсор','mouseReact',True),('Масштаб','scale',1,.1,5,.01),('Детализация','detail',8,1,24,1),
 ('Поворот','rotation',0,0,360,1),('Искажение','warp',1,0,3,.01),('Сдвиг цвета','hueShift',0,0,360,1),
 ('Насыщенность','saturation',1,0,3,.01),('Яркость эффекта','brightness',1.5,0,3,.01),('Контраст','contrast',1,0,3,.01),
 ('Перемешивание курсором','stir',.5,0,3,.01),('Блеск','sheen',.3,0,2,.01),('Вихрь от нажатия','clickSwirl',True),
 ('Зерно','grain',0,0,1,.001),('Затухание','fade',0,0,1,.01),('Непрозрачность','opacity',1,0,1,.01),
 ('Разрешение','resolution',1,.1,2,.01)]}
NAMES={'vortex':'Liquid Metal Vortex','chrome':'Liquid Chrome','veil':'Dark Veil','silk':'Silk','iridescence':'Iridescence','custom':'Своя картинка'}

def defaults():
    return {'effect':'vortex','intensity':.55,'edge':.8,'blur':0.,'performance':'balanced','props':{k:{x[1]:x[2] for x in rows} for k,rows in SCHEMAS.items()}}

class LocalOnly(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self,info):
        if info.requestUrl().scheme() not in ('file','data','qrc','about'):info.block(True)

class EffectPage(QWebEnginePage):
    def __init__(self,parent):
        self.local_profile=QWebEngineProfile(parent)
        super().__init__(self.local_profile,parent)
        self.guard=LocalOnly(self);self.local_profile.setUrlRequestInterceptor(self.guard)
        self.errors=[]
    def javaScriptConsoleMessage(self,level,message,line,source):
        if level==QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:self.errors.append(message)
    def acceptNavigationRequest(self,url,kind,isMainFrame):return url.scheme() in ('file','about','data')

class EffectView(QWebEngineView):
    def __init__(self,parent):
        super().__init__(parent);self.setPage(EffectPage(self));self.page().setBackgroundColor(QColor('#08090b'))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu);self.ready=False;self.config=None
        self.loadFinished.connect(self.loaded)
        path=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'backgrounds'/'index.html'
        self.local_url=QUrl.fromLocalFile(str(path));self.started=False
    def loaded(self,ok):
        self.ready=ok
        if ok:
            self.publish();QTimer.singleShot(150,self.publish)
    def configure(self,config):
        self.config=config
        if not self.started and config.get('effect') not in ('vortex',''):
            self.started=True;self.setUrl(self.local_url)
        self.publish()
    def publish(self):
        if self.ready and self.config:
            self.page().runJavaScript('window.setBackground && window.setBackground('+json.dumps(self.config)+')')

class Backgrounds:
    def __init__(self,player):
        self.player=player;self.data=defaults();self.web=None;self.custom=None;self.preview=None;self.editor=None;self.last_mouse=None
        try:
            saved=json.loads((player.data_dir/'backgrounds.json').read_text(encoding='utf8'))
            for k in ('effect','intensity','edge','blur','performance','custom_file'):
                if k in saved:self.data[k]=saved[k]
            for k,v in saved.get('props',{}).items():
                if k in self.data['props']:self.data['props'][k].update(v)
        except (OSError,ValueError,TypeError):pass
        if self.data['effect'] not in NAMES:self.data['effect']='vortex'
        self.timer=QTimer(player);self.timer.setInterval(33);self.timer.timeout.connect(self.pointer)
        self.save_timer=QTimer(player);self.save_timer.setSingleShot(True);self.save_timer.timeout.connect(self.save)
        player.root.installEventFilter(player);self.apply()
    def config(self,preview=False):
        effect=self.data['effect'];props=copy.deepcopy(self.data['props'].get(effect,{}))
        paused=not self.player.theme['motion'] or self.player.isMinimized()
        mode=self.data.get('performance','balanced');fps={'eco':24,'balanced':30,'high':60}.get(mode,30)
        if mode!='high':
            props['maxDevicePixelRatio']=min(props.get('maxDevicePixelRatio',1),.75 if mode=='eco' else 1)
            props['dpr']=min(props.get('dpr',1),.75 if mode=='eco' else 1)
        return {'effect':effect,'props':props,'paused':paused,'fps':fps,'intensity':1 if preview else self.data['intensity'],
                'edge':0 if preview else self.data['edge'],'blur':0 if preview else self.data['blur']}
    def apply(self):
        root=self.player.root;native=self.data['effect']=='vortex'
        if self.data['effect']=='custom':
            root.gl.hide();root.gl.timer.stop();self.timer.stop()
            if self.web:self.web.hide();self.web.configure(dict(self.config(),effect='',paused=True))
            if self.custom is None:
                from PySide6.QtWidgets import QGraphicsBlurEffect
                self.custom=ImageBackground(root,self.data);self.custom_blur=QGraphicsBlurEffect(self.custom);self.custom.setGraphicsEffect(self.custom_blur)
            self.custom_blur.setBlurRadius(float(self.data.get('blur',0)))
            path=self.data.get('custom_file','')
            if getattr(self.custom,'loaded_path',None)!=path:self.custom.load(path);self.custom.loaded_path=path
            self.custom.setGeometry(root.rect());self.custom.lower();self.custom.show();self.custom.update()
            if self.preview:self.preview.hide();self.preview.configure(dict(self.config(),effect='',paused=True))
            return
        if self.custom:self.custom.hide()
        if not root.gl.timer.isActive():root.gl.timer.start()

        mode=self.data.get('performance','balanced');root.gl.scene_fps={'eco':24,'balanced':30,'high':50}.get(mode,30);root.gl.render_width={'eco':260,'balanced':360,'high':440}.get(mode,360)
        root.gl.timer.setInterval(16 if mode=='high' else 33)
        root.gl.setVisible(native)
        if not native:
            if self.web is None:self.web=EffectView(root);self.web.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            self.web.setGeometry(root.rect());self.web.lower();self.web.show();self.web.configure(self.config());self.timer.start()
        else:
            if self.web:self.web.hide();self.web.configure(dict(self.config(),effect=''))
            self.timer.stop()
        if self.preview:
            self.preview.configure(self.config(True) if self.preview.isVisible() else dict(self.config(True),effect='',paused=True))
    def resize(self):
        if self.custom:self.custom.setGeometry(self.player.root.rect())
        if self.web:self.web.setGeometry(self.player.root.rect())
    def pointer(self,kind='pointermove'):
        if not self.web or not self.web.isVisible() or self.player.isMinimized():return
        point=self.web.mapFromGlobal(QCursor.pos());xy=(point.x(),point.y())
        if kind=='pointermove' and self.last_mouse==xy:return
        self.last_mouse=xy
        self.web.page().runJavaScript(f"window.forwardPointer && window.forwardPointer({xy[0]},{xy[1]},'{kind}')")
    def save(self):self.player.save_data('backgrounds.json',self.data)
    def change(self,key,value,effect=None):
        if effect:self.data['props'][effect][key]=value
        else:self.data[key]=value
        self.apply();self.save_timer.start(350)
    def controls(self,parent):
        self.editor=QWidget(parent);box=QVBoxLayout(self.editor);box.setContentsMargins(0,0,0,0);box.setSpacing(16)
        label=QLabel('Фон приложения');label.setStyleSheet('font-size:20px;font-weight:600');box.addWidget(label)
        select=QComboBox();select.setMinimumHeight(46);select.setObjectName('backgroundSelect');[select.addItem(v,k) for k,v in NAMES.items()];select.setCurrentIndex(list(NAMES).index(self.data['effect']));box.addWidget(select)
        box.addWidget(self.player.button('Выбрать свою картинку',lambda:choose_background(self)))
        self.parameters=QWidget();self.parameters_box=QVBoxLayout(self.parameters);self.parameters_box.setContentsMargins(0,0,0,0);self.parameters_box.setSpacing(15);box.addWidget(self.parameters)
        self.preview=EffectView(parent);self.preview.setMinimumSize(260,200);self.preview.setMaximumHeight(250);box.addWidget(self.preview)
        self.preview.hide()
        self.preview_toggle=self.player.button('Показать предпросмотр',self.toggle_preview);box.addWidget(self.preview_toggle)
        self.preview_caption=QLabel('Предпросмотр оригинального эффекта');self.preview_caption.setObjectName('muted');box.addWidget(self.preview_caption)
        appearance=QWidget();a=QVBoxLayout(appearance);a.setContentsMargins(0,12,0,0);a.setSpacing(15);title=QLabel('За кнопками плеера');title.setStyleSheet('font-size:16px;font-weight:700;');a.addWidget(title)
        for label,key,lo,hi,step in [('Яркость фона','intensity',0,1,.01),('Затемнение по краям','edge',0,1,.01),('Размытие','blur',0,12,.1)]:
            self.add_control(a,(label,key,self.data[key],lo,hi,step),lambda k,v:self.change(k,v))
        box.addWidget(appearance)
        self.appearance_group=appearance
        box.addWidget(QLabel('Производительность'))
        performance=QComboBox();performance.setMinimumHeight(44)
        for text,value in [('Экономичный · 24 кадра/с','eco'),('Сбалансированный · 30 кадров/с','balanced'),('Плавный · 60 кадров/с','high')]:performance.addItem(text,value)
        performance.setCurrentIndex(max(0,performance.findData(self.data.get('performance','balanced'))));performance.currentIndexChanged.connect(lambda _:self.change('performance',performance.currentData()));box.addWidget(performance)
        select.currentIndexChanged.connect(lambda _:self.select_effect(select.currentData()))
        self.selector=select;self.rebuild();return self.editor
    def select_effect(self,effect):self.change('effect',effect);self.rebuild()
    def rebuild(self):
        layout=self.parameters_box
        while layout.count():
            item=layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        effect=self.data['effect'];native=effect=='vortex';custom=effect=='custom'
        self.preview.hide();self.preview_caption.hide();self.preview_toggle.setVisible(not native and not custom);self.preview_toggle.setText('Показать предпросмотр');self.appearance_group.setVisible(not native)
        if custom:
            layout.addWidget(QLabel('Своя картинка · хранится только на этом компьютере'))
        if not native and not custom:
            advanced=QWidget();advanced_box=QVBoxLayout(advanced);advanced_box.setContentsMargins(0,0,0,0);advanced_box.setSpacing(15)
            fold=self.player.button('Тонкая настройка  +',lambda:None);fold.setCheckable(True);advanced_box.addWidget(fold)
            advanced_body=QWidget();advanced_inner=QVBoxLayout(advanced_body);advanced_inner.setContentsMargins(8,8,8,8);advanced_inner.setSpacing(17);advanced_box.addWidget(advanced_body);advanced_body.hide()
            fold.toggled.connect(lambda checked,w=advanced_body,b=fold:(w.setVisible(checked),b.setText('Тонкая настройка  −' if checked else 'Тонкая настройка  +')))
            for schema in SCHEMAS[effect]:
                target=layout if schema[1] in ('color','speed','scale') else advanced_inner
                self.add_control(target,schema,lambda k,v,e=effect:self.change(k,v,e),self.data['props'][effect])
            layout.addWidget(advanced)
            reset=self.player.button('Сбросить этот фон',self.reset_current);layout.addWidget(reset)
        self.apply()
    def toggle_preview(self):
        visible=not self.preview.isVisible();self.preview.setVisible(visible);self.preview_caption.setVisible(visible)
        self.preview_toggle.setText('Скрыть предпросмотр' if visible else 'Показать предпросмотр');self.apply()
    def reset_current(self):
        effect=self.data['effect']
        if effect=='custom':self.data['effect']='vortex';self.selector.setCurrentIndex(0);self.rebuild();self.save();return
        self.data['props'][effect]=defaults()['props'][effect];self.rebuild();self.save_timer.start(350)
    def add_control(self,layout,schema,callback,values=None):
        label,key,default,*bounds=schema;value=(values or {}).get(key,default)
        host=QWidget();v=QVBoxLayout(host);v.setContentsMargins(0,0,0,0);v.setSpacing(6)
        if isinstance(default,bool):
            control=QCheckBox(label);control.setChecked(value);control.toggled.connect(lambda n:callback(key,n));v.addWidget(control)
        elif isinstance(default,str):
            row=QHBoxLayout();row.addWidget(QLabel(label));control=QLineEdit(str(value));control.setMaxLength(7);control.setMaximumWidth(110);row.addWidget(control);v.addLayout(row)
            def color(text):
                if len(text)==7 and text.startswith('#') and QColor(text).isValid():
                    control.setStyleSheet('border-color:'+text);callback(key,text)
            control.textChanged.connect(color);control.setToolTip('Цвет в формате #7c3aed. Можно вставить любой HEX-код.')
            palette=QHBoxLayout()
            for name,c in [('Фиолет.','#7c3aed'),('Серебро','#b9bac4'),('Бирюза','#29a4b5'),('Розовый','#ed7da7')]:
                b=self.player.button(name,lambda checked=False,c=c:control.setText(c));b.setMinimumWidth(0);palette.addWidget(b)
            v.addLayout(palette)
        else:
            lo,hi,step=bounds;row=QHBoxLayout();row.addWidget(QLabel(label));number=QLabel(f'{value:g}');row.addStretch();row.addWidget(number);v.addLayout(row)
            control=QSlider(Qt.Orientation.Horizontal);control.setRange(round(lo/step),round(hi/step));control.setValue(round(value/step));v.addWidget(control)
            def changed(n):
                value=round(n*step,4);number.setText(f'{value:g}');callback(key,int(value) if isinstance(default,int) else value)
            control.valueChanged.connect(changed)
        host.setProperty('settingKey',key);layout.addWidget(host)
    def close(self):
        self.save();self.timer.stop();self.save_timer.stop()
        for view in (self.web,self.preview):
            if view:view.setUrl(QUrl('about:blank'))
