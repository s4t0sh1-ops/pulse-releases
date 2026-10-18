"""Native Qt liquid-metal skin. Original shaders inspired by the linked references."""
import math
import struct
import time
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import (QColor, QPainter, QPen, QPainterPath, QLinearGradient,
    QConicalGradient, QRadialGradient, QFont, QCursor, QVector2D, QSurfaceFormat)
from PySide6.QtWidgets import QWidget, QPushButton, QSizePolicy
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram, QOpenGLBuffer, QOpenGLVertexArrayObject, QOpenGLFramebufferObject

DEFAULTS = {'hue': 0, 'speed': 1.0, 'complexity': 5, 'title': 'Твоя музыка. Твой ритм.', 'motion': True}

STYLE = '''
QComboBox {background:#151820;border:1px solid #303646;border-radius:12px;padding:10px 16px;min-height:26px;font-size:13px;}
QComboBox::drop-down {subcontrol-origin:padding;subcontrol-position:top right;width:30px;border:0;}
QComboBox QAbstractItemView {background:#171b25;color:#eeeef7;border:1px solid #363e51;padding:8px;selection-background-color:#343b51;}
QCheckBox {spacing:10px;padding:6px 0;}
QLabel#muted {font-family:Segoe UI;font-size:13px;font-weight:500;}

QWidget {color:#eeeef0;font-family:'Manrope';font-size:13px;background:transparent;}
QMainWindow,QDialog {background:#08090b;}
QLabel#muted {color:#b9bbc7;}
QLabel#title {font-size:40px;font-weight:700;letter-spacing:-1px;color:#fafafa;}
QLabel#code {font-size:24px;font-weight:600;color:#ecd5d4;}
QLineEdit {background:rgba(14,15,18,215);border:1px solid #343438;border-radius:18px;padding:12px 16px;selection-background-color:#6a4d52;}
QLineEdit:focus {border-color:#898085;background:rgba(18,18,22,240);}
QWidget#panel {background:rgba(15,16,19,237);border:1px solid #26272b;border-radius:20px;}
QWidget#dock {background:rgba(10,11,13,245);border:1px solid #27282c;border-radius:20px;}
QLabel#section {font-size:13px;font-weight:600;color:#d7d7dc;}
QTableWidget {background:rgba(9,10,13,214);border:1px solid #27272c;border-radius:18px;gridline-color:transparent;selection-background-color:rgba(83,69,76,125);outline:none;}
QTableWidget::item {padding:10px 14px;border-bottom:1px solid rgba(255,255,255,12);}
QTableWidget::item:hover {background:rgba(255,255,255,12);}
QHeaderView {background:transparent;}
QHeaderView::section {background:#101114;color:#81828a;border:0;padding:13px;}
QTableCornerButton::section {background:#101114;border:0;}
QScrollBar:vertical {width:6px;background:transparent;margin:6px 1px;}
QScrollBar::handle:vertical {background:#44444b;min-height:30px;border-radius:3px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QSlider::groove:horizontal {height:3px;background:#323239;border-radius:1px;}
QSlider::sub-page:horizontal {background:#d4c9cc;border-radius:1px;}
QSlider::handle:horizontal {background:#e8e4e6;width:9px;margin:-3px 0;border-radius:4px;}
QSlider::handle:horizontal:hover {background:#fff;width:11px;margin:-4px 0;}
QCheckBox {color:#b5b5bd;spacing:9px;}
QCheckBox::indicator {width:16px;height:16px;border:1px solid #55545b;border-radius:5px;background:#15161a;}
QCheckBox::indicator:checked {background:#c4b6bc;border-color:#c4b6bc;}
QToolTip {background:#202126;color:#eee;border:1px solid #45464d;padding:7px;border-radius:6px;}
'''

FRAGMENT = '''
#version 120
uniform vec2 resolution;
uniform vec2 mouse;
uniform float seconds;
uniform float hue;
uniform float complexity;
uniform float extent;
mat2 turn(float a){return mat2(cos(a),-sin(a),sin(a),cos(a));}
float field(vec3 p){
    vec3 q=p;
    q.xz=turn(p.y*.38+seconds*.10)*q.xz;
    float scale=2.2+complexity*.18;
    vec3 s=q*scale;
    float fluid=dot(sin(s),cos(s.zxy+vec3(0.,0.,seconds*.12)));
    float sheets=(abs(fluid)-.16)/(scale*2.);
    float envelope=(length(p*vec3(.62,.31,1.10))-.94)*.8;
    return max(sheets,envelope);
}
vec3 normalAt(vec3 p){
    vec2 e=vec2(.002,0.);
    return normalize(vec3(field(p+e.xyy)-field(p-e.xyy),field(p+e.yxy)-field(p-e.yxy),field(p+e.yyx)-field(p-e.yyx)));
}
vec3 palette(float h){return .65+.35*cos(6.28318*(h+vec3(0.,.67,.33)));}
void main(){
    vec2 uv=gl_FragCoord.xy/resolution;
    uv.y=1.-uv.y;
    vec2 p=(uv-vec2(extent*.57,.38))*vec2(resolution.x/resolution.y,1.);
    vec3 ro=vec3(mouse.x*.09,mouse.y*.07,3.3);
    vec3 rd=normalize(vec3(p.x*3.2,-p.y*3.8,-2.65));
    ro.xy+=vec2(.02,-.08);
    float d=0.;float hit=0.;vec3 pos=ro;
    for(int i=0;i<42;i++){
        pos=ro+rd*d;
        float s=field(pos);
        if(s<.003){hit=1.;break;}
        d+=s*.73;
        if(d>6.)break;
    }
    vec3 bg=vec3(.030,.033,.041);
    vec3 color=bg;
    if(hit>.5){
        vec3 n=normalAt(pos);
        vec3 r=reflect(rd,n);
        float bands=pow(max(0.,sin(r.y*2.+r.z*1.5+r.x*2.)),8.);
        float strip=pow(max(0.,1.-abs(r.x*.8+r.y*.3)),12.);
        float light=pow(max(dot(n,normalize(vec3(-.5,1.,1.6))),0.),3.);
        float fres=pow(1.-max(dot(-rd,n),0.),3.);
        vec3 tint=mix(vec3(.96,.77,.76),palette(hue/360.),.48);
        color=vec3(.045,.047,.055)+vec3(.92,.94,.98)*bands*.9+tint*strip*.85;
        color+=light*.19+tint*fres*.30;
        color*=.75+.25*cos(pos.z*7.+pos.x*5.);
    }
    float side=smoothstep(.015,.16,uv.x)*(1.-smoothstep(extent*.78,extent+.04,uv.x));
    float bottom=1.-smoothstep(.61,.91,uv.y);
    float top=smoothstep(0.,.12,uv.y);
    float vignette=side*bottom*top;
    // Keep enough contrast behind titles and controls, with no hard image edges.
    color=mix(bg,color,vignette*.76);
    float grain=fract(sin(dot(gl_FragCoord.xy,vec2(12.9898,78.233)))*43758.5453)-.5;
    color+=grain*.009*vignette;
    gl_FragColor=vec4(color,1.);
}
'''


class VortexGL(QOpenGLWidget):
    def __init__(self, parent):
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setVersion(2, 1)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
        self.setFormat(fmt)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.settings = dict(DEFAULTS)
        self.elapsed = 0.
        self.last = time.monotonic()
        self.extent = .80
        self.mouse_x = 0.
        self.mouse_y = 0.
        self.program = None
        self.scene = None
        self.scene_time = 0.
        self.frames = 0
        self.frame_intervals = []
        self.paint_time = 0.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.start(16)

    def tick(self):
        now = time.monotonic()
        delta = min(.12, now - self.last)
        self.last = now
        if self.settings['motion'] and self.isVisible() and not self.window().isMinimized():
            pos = self.mapFromGlobal(QCursor.pos())
            tx = max(-1,min(1,pos.x()/max(1,self.width())*2-1))
            ty = max(-1,min(1,pos.y()/max(1,self.height())*2-1))
            ease = 1.-math.exp(-delta*3.8)
            self.mouse_x += (tx-self.mouse_x)*ease
            self.mouse_y += (ty-self.mouse_y)*ease
            self.elapsed += delta * self.settings['speed']
            self.update()

    def initializeGL(self):
        self.program = QOpenGLShaderProgram(self)
        ok = self.program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex,
            '#version 120\nattribute vec2 position;void main(){gl_Position=vec4(position,0.,1.);}')
        ok = ok and self.program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FRAGMENT)
        ok = ok and self.program.link()
        if not ok:
            self.program = None
            return
        self.display = QOpenGLShaderProgram(self)
        self.display.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex,
            '#version 120\nattribute vec2 position;varying vec2 uv;void main(){uv=position*.5+.5;gl_Position=vec4(position,0.,1.);}')
        self.display.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, '''
            #version 120
            varying vec2 uv;
            uniform sampler2D surface;
            uniform vec2 pointer;
            uniform vec2 texel;
            void main(){
                vec2 q=uv+pointer*vec2(.009,.007);
                vec3 c=texture2D(surface,q).rgb*.20;
                c+=(texture2D(surface,q+vec2(texel.x,0.)).rgb+texture2D(surface,q-vec2(texel.x,0.)).rgb)*.12;
                c+=(texture2D(surface,q+vec2(0.,texel.y)).rgb+texture2D(surface,q-vec2(0.,texel.y)).rgb)*.12;
                c+=(texture2D(surface,q+texel).rgb+texture2D(surface,q-texel).rgb)*.08;
                c+=(texture2D(surface,q+vec2(texel.x,-texel.y)).rgb+texture2D(surface,q-vec2(texel.x,-texel.y)).rgb)*.08;
                c=mix(vec3(.030,.033,.041),c,.24);
                gl_FragColor=vec4(c,1.);
            }
        ''')
        self.display.link()
        self.buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self.vao = QOpenGLVertexArrayObject(self)
        self.vao.create()
        self.vao.bind()
        self.buffer.create()
        self.buffer.bind()
        self.buffer.allocate(struct.pack('8f', -1,-1, 1,-1, -1,1, 1,1), 32)
        self.buffer.release()
        self.vao.release()
        self.context().aboutToBeDestroyed.connect(self.cleanup)

    def cleanup(self):
        self.makeCurrent()
        if hasattr(self, 'buffer'):
            self.buffer.destroy()
            self.vao.destroy()
        self.program = None
        self.display = None
        self.scene = None
        self.doneCurrent()

    def paintGL(self):
        now=time.monotonic()
        if self.paint_time:
            self.frame_intervals.append(now-self.paint_time)
            self.frame_intervals=self.frame_intervals[-180:]
        self.paint_time=now
        self.frames+=1
        gl = self.context().functions()
        gl.glClearColor(.030,.033,.041,1.)
        gl.glClear(0x00004000)
        if not self.program:
            return
        self.vao.bind()
        self.buffer.bind()
        ratio = self.devicePixelRatioF()
        width=getattr(self,'render_width',360)
        size=(width,max(120,round(width*self.height()/max(1,self.width()))))
        changed=tuple(self.settings.values())+(self.extent,)
        if self.scene is None or self.scene.width()!=size[0] or self.scene.height()!=size[1]:
            self.scene=QOpenGLFramebufferObject(*size)
            self.scene_time=0.
        if now-self.scene_time>=1/getattr(self,'scene_fps',30) or getattr(self,'scene_settings',None)!=changed:
            self.scene_settings=changed
            self.scene_time=now
            self.scene.bind()
            gl.glViewport(0,0,*size)
            program=self.program
            program.bind()
            gl.glUniform2f(program.uniformLocation(b'resolution'),*size)
            gl.glUniform2f(program.uniformLocation(b'mouse'),0.,0.)
            gl.glUniform1f(program.uniformLocation(b'seconds'),float(self.elapsed))
            gl.glUniform1f(program.uniformLocation(b'hue'),float(self.settings['hue']))
            gl.glUniform1f(program.uniformLocation(b'complexity'),float(self.settings['complexity']))
            gl.glUniform1f(program.uniformLocation(b'extent'),float(self.extent))
            self.draw_quad(program,gl)
            program.release()
        gl.glBindFramebuffer(0x8D40,self.defaultFramebufferObject())
        gl.glViewport(0,0,round(self.width()*ratio),round(self.height()*ratio))
        program=self.display
        program.bind()
        gl.glActiveTexture(0x84C0)
        gl.glBindTexture(0x0DE1,self.scene.texture())
        gl.glTexParameteri(0x0DE1,0x2801,0x2601)
        gl.glTexParameteri(0x0DE1,0x2800,0x2601)
        gl.glUniform1i(program.uniformLocation(b'surface'),0)
        gl.glUniform2f(program.uniformLocation(b'pointer'),self.mouse_x,self.mouse_y)
        gl.glUniform2f(program.uniformLocation(b'texel'),4./size[0],4./size[1])
        self.draw_quad(program,gl)
        gl.glBindTexture(0x0DE1,0)
        self.buffer.release()
        self.vao.release()
        program.release()

    def draw_quad(self,program,gl):
        location=program.attributeLocation(b'position')
        program.enableAttributeArray(location)
        program.setAttributeBuffer(location,0x1406,0,2,8)
        gl.glDrawArrays(0x0005,0,4)
        program.disableAttributeArray(location)


class VortexSurface(QWidget):
    def __init__(self):
        super().__init__()
        self.gl = VortexGL(self)
        self.gl.lower()

    def resizeEvent(self, event):
        self.gl.setGeometry(self.rect())
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#08090b'))


def draw_icon(painter, icon, color, size=22):
    painter.save()
    painter.scale(size / 24, size / 24)
    painter.setPen(QPen(color, 1.45, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    def line(x,y,x2,y2):
        path.moveTo(x,y);path.lineTo(x2,y2)
    if icon == 'play':
        path.moveTo(7,4);path.cubicTo(7,3,8,3,9,4);path.lineTo(20,11);path.quadTo(21.5,12,20,13);path.lineTo(9,20);path.quadTo(7,21.5,7,20);path.closeSubpath()
    elif icon == 'pause':
        path.addRoundedRect(QRectF(6,4,4,16),1,1);path.addRoundedRect(QRectF(14,4,4,16),1,1)
    elif icon in ('next','previous'):
        if icon == 'previous':
            painter.translate(24,0);painter.scale(-1,1)
        path.moveTo(5,5);path.quadTo(5,3.5,6.5,4.5);path.lineTo(17,11);path.quadTo(18.5,12,17,13);path.lineTo(6.5,19.5);path.quadTo(5,20.5,5,19);path.closeSubpath();line(20,4,20,20)
    elif icon in ('volume','mute'):
        path.moveTo(4,9);path.lineTo(8,9);path.lineTo(13,5);path.lineTo(13,19);path.lineTo(8,15);path.lineTo(4,15);path.closeSubpath()
        if icon == 'volume':
            path.moveTo(17,8);path.quadTo(21,12,17,16)
            path.moveTo(20,5);path.quadTo(26,12,20,19)
        else:
            line(17,9,22,15);line(22,9,17,15)
    elif icon in ('plus','minus'):
        line(6,12,18,12)
        if icon == 'plus':line(12,6,12,18)
    elif icon == 'maximize':
        path.addRoundedRect(QRectF(5,5,14,14),1.5,1.5)
    elif icon == 'lyrics':
        line(5,5,19,5);line(12,5,12,20);line(8,20,16,20)
    elif icon == 'queue':
        line(3,5,15,5);line(3,10,13,10);line(3,15,10,15);line(18,8,18,18);line(18,8,22,7);path.addEllipse(QRectF(12,16,6,4))
    elif icon == 'shuffle':
        path.moveTo(3,6);path.lineTo(6,6);path.cubicTo(11,6,13,18,18,18);path.lineTo(21,18)
        path.moveTo(3,18);path.lineTo(6,18);path.cubicTo(9,18,10,15,11,13)
        path.moveTo(13,9);path.quadTo(15,6,18,6);path.lineTo(21,6)
        line(18,3,21,6);line(21,6,18,9);line(18,15,21,18);line(21,18,18,21)
    elif icon == 'heart':
        path.moveTo(12,20);path.cubicTo(9,18,3,13,3,8);path.cubicTo(3,2,10,2,12,7);path.cubicTo(14,2,21,2,21,8);path.cubicTo(21,13,15,18,12,20)
    elif icon == 'settings':
        for x,y in ((6,7),(12,16),(18,9)):
            line(x,3,x,y-3);line(x,y+3,x,21);path.addEllipse(QRectF(x-2.5,y-2.5,5,5))
    elif icon == 'search':
        path.addEllipse(QRectF(4,4,12,12));line(14,14,21,21)
    elif icon == 'close':
        line(6,6,18,18);line(18,6,6,18)
    elif icon == 'home':
        path.moveTo(3,11);path.lineTo(12,3);path.lineTo(21,11);path.lineTo(20,21);path.lineTo(4,21);path.closeSubpath();line(10,21,10,15);line(14,21,14,15)
    elif icon == 'cloud':
        path.moveTo(6,18);path.cubicTo(0,18,1,10,6,10);path.cubicTo(5,2,17,2,18,10);path.cubicTo(25,10,24,18,19,18);path.closeSubpath()
    elif icon == 'user':
        path.addEllipse(QRectF(8,3,8,8));path.moveTo(4,21);path.cubicTo(4,12,20,12,20,21)
    elif icon == 'help':
        path.addEllipse(QRectF(3,3,18,18));path.moveTo(9,8);path.cubicTo(9,4,17,6,14,10);path.quadTo(12,11,12,14);line(12,17,12,17.1)
    elif icon == 'support':
        path.moveTo(4,13);path.cubicTo(4,1,20,1,20,13);path.addRoundedRect(QRectF(2,11,4,8),2,2);path.addRoundedRect(QRectF(18,11,4,8),2,2)
        path.moveTo(20,18);path.quadTo(20,22,13,22);line(11,22,14,22)
    painter.drawPath(path)
    painter.restore()


class MetalButton(QPushButton):
    def __init__(self, text='', parent=None, icon=None, primary=False):
        super().__init__(text, parent)
        self.glyph = icon
        self.primary = primary
        self.hover_value = 0.
        self.press_value = 0.
        self.pulse_value = 1.
        self.phase = 0.
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        if icon:
            self.setFixedSize(38,38)
        self.hover_animation = QVariantAnimation(self)
        self.hover_animation.setDuration(190)
        self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hover_animation.valueChanged.connect(self.hover_changed)
        self.press_animation = QVariantAnimation(self)
        self.press_animation.setDuration(140)
        self.press_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.press_animation.valueChanged.connect(self.press_changed)
        self.pressed.connect(lambda: self.animate(self.press_animation,self.press_value,1.))
        self.released.connect(lambda: self.animate(self.press_animation,self.press_value,0.))
        self.click_animation=QVariantAnimation(self)
        self.click_animation.setDuration(440)
        self.click_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.click_animation.valueChanged.connect(self.pulse_changed)
        self.clicked.connect(lambda:self.animate(self.click_animation,0.,1.))
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.shimmer)
        # Idle chrome stays still; animate only while the button is in use.

    def sizeHint(self):
        size = super().sizeHint()
        size.setWidth(38 if self.glyph else self.fontMetrics().horizontalAdvance(self.text())+40)
        size.setHeight(44)
        return size

    def minimumSizeHint(self):
        return self.sizeHint()

    def animate(self, animation, start, end):
        animation.stop();animation.setStartValue(start);animation.setEndValue(end);animation.start()

    def hover_changed(self, value):
        self.hover_value=float(value);self.update()

    def press_changed(self, value):
        self.press_value=float(value);self.update()

    def pulse_changed(self,value):
        self.pulse_value=float(value);self.update()

    def shimmer(self):
        if self.isVisible() and self.isEnabled() and not self.window().isMinimized():
            self.phase=(self.phase+.6+self.hover_value*.7)%360
            if not self.glyph or self.hover_value>.01:
                self.update()

    def enterEvent(self,event):
        self.timer.start(16)
        self.animate(self.hover_animation,self.hover_value,1.)
        super().enterEvent(event)

    def leaveEvent(self,event):
        self.timer.stop()
        self.animate(self.hover_animation,self.hover_value,0.)
        self.animate(self.press_animation,self.press_value,0.)
        super().leaveEvent(event)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():painter.setOpacity(.40)
        painter.translate(self.width()/2,self.height()/2+self.press_value)
        scale=1.-self.press_value*.045
        painter.scale(scale,scale)
        rect=QRectF(-self.width()/2+2,-self.height()/2+2,self.width()-4,self.height()-4)
        radius=rect.height()/2
        ring=QConicalGradient(rect.center(),self.phase)
        ring.setColorAt(0,QColor('#292a2f'));ring.setColorAt(.12,QColor('#d5d1d5'))
        ring.setColorAt(.22,QColor('#38383f'));ring.setColorAt(.40,QColor('#7e727d'))
        ring.setColorAt(.53,QColor('#f0edef'));ring.setColorAt(.64,QColor('#3c3d44'))
        ring.setColorAt(.85,QColor('#aaa7af'));ring.setColorAt(1,QColor('#292a2f'))
        opacity=1. if not self.glyph or self.primary else self.hover_value*.75
        painter.save();painter.setOpacity(painter.opacity()*opacity)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(ring);painter.drawRoundedRect(rect,radius,radius)
        fill=QLinearGradient(0,rect.top(),0,rect.bottom())
        fill.setColorAt(0,QColor('#313035' if self.hover_value>.4 else '#242428'))
        fill.setColorAt(.48,QColor('#101114'));fill.setColorAt(1,QColor('#08090b'))
        painter.setBrush(fill)
        inner=rect.adjusted(1.35,1.35,-1.35,-1.35)
        painter.drawRoundedRect(inner,radius,radius)
        if self.hover_value>.01:
            sheen=QRadialGradient(QPointF(math.sin(math.radians(self.phase))*rect.width()*.35,rect.top()),rect.width()*.7)
            sheen.setColorAt(0,QColor(230,218,228,int(35*self.hover_value)))
            sheen.setColorAt(1,QColor(255,255,255,0))
            painter.setBrush(sheen);painter.drawRoundedRect(inner,radius,radius)
        painter.restore()
        if self.pulse_value<1:
            glow=QColor(211,224,237,int(105*(1-self.pulse_value)))
            painter.setPen(QPen(glow,1.5));painter.setBrush(Qt.BrushStyle.NoBrush)
            inset=(1-self.pulse_value)*rect.height()*.23
            pulse=rect.adjusted(inset,inset,-inset,-inset)
            painter.drawRoundedRect(pulse,pulse.height()/2,pulse.height()/2)
        color=QColor('#ffffff' if self.hover_value>.2 or self.primary else '#b9b9c2')
        if self.isCheckable() and self.isChecked():color=QColor('#f3b7bc')
        if not self.icon().isNull():
            clip=QPainterPath();clip.addEllipse(QRectF(-13,-13,26,26));painter.setClipPath(clip)
            painter.drawPixmap(-13,-13,self.icon().pixmap(26,26))
        elif self.glyph:
            painter.translate(-11,-11)
            draw_icon(painter,self.glyph,color)
        else:
            painter.setPen(color)
            painter.setFont(QFont('Manrope',10,QFont.Weight.DemiBold if self.primary else QFont.Weight.Normal))
            painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,self.text())

    def setGlyph(self, glyph):
        self.glyph=glyph
        self.update()
