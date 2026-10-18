"""Native media with a background SoundCloud playback backend."""
import json,secrets,sys,subprocess,threading
from shiboken6 import isValid
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from PySide6.QtCore import QObject,Signal,QUrl,QTimer,QProcess,Qt
from PySide6.QtWidgets import QWidget
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile,QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

class WidgetPage(QWebEnginePage):
    def __init__(self,profile,parent,receiver):super().__init__(profile,parent);self.receiver=receiver
    def javaScriptConsoleMessage(self,level,message,line,source):
        if message.startswith('PULSE_SC:'):
            try:self.receiver(json.loads(message[9:]))
            except (ValueError,TypeError,KeyError):pass

class EdgeBrowser(QWidget):
    """Microsoft's installed WebView2 supplies the audio codecs absent from Qt Chromium."""
    arrived=Signal(object)
    def __init__(self,owner,receiver):
        super().__init__(owner);self.receiver=receiver;self.ready=False;self.pending=[];self.closing=False
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow,True);self.arrived.connect(self.handle_event)
        asset=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'soundcloud-host'/'PulseSoundCloudHost.exe'
        self.process=subprocess.Popen([str(asset),str(int(self.winId())),str(owner.data_dir/'sc-browser')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        def read_events():
            try:
                for line in self.process.stdout:
                    if self.closing:return
                    try:self.arrived.emit(json.loads(line.decode('utf-8-sig')))
                    except (ValueError,UnicodeError):continue
            except (OSError,RuntimeError):return
        self.reader=threading.Thread(target=read_events,daemon=True);self.reader.start()
    def handle_event(self,event):
        if self.closing:return
        if event.get('host_ready'):
            self.ready=True
            for command in self.pending:self.send(command)
            self.pending=[]
        else:self.receiver(event)
    def send(self,command):
        if self.closing:return
        if not self.ready:self.pending.append(command);return
        try:self.process.stdin.write((json.dumps(command,ensure_ascii=False)+'\n').encode('utf-8'));self.process.stdin.flush()
        except (OSError,ValueError):self.receiver({'host_error':True})
    def setHtml(self,html,base=None):self.send({'op':'load','html':html,'tag':getattr(self.owner_media,'tag','')})
    def runJavaScript(self,script):self.send({'op':'script','script':script})
    def shutdown(self):
        if self.closing:return
        self.send({'op':'close'});self.closing=True
        try:
            self.process.stdin.close();self.process.wait(timeout=1.2)
        except (OSError,subprocess.TimeoutExpired):self.process.kill();self.process.wait(timeout=1)

class HybridMedia(QObject):
    positionChanged=Signal(int);durationChanged=Signal(int);playbackStateChanged=Signal(object);mediaStatusChanged=Signal(object);errorOccurred=Signal(object,str)
    def __init__(self,parent):
        super().__init__(parent);self.owner=parent;self.native=QMediaPlayer(parent);self.browser=None;self.mode='native';self.audio=None
        self._source=QUrl();self._state=QMediaPlayer.PlaybackState.StoppedState;self._status=QMediaPlayer.MediaStatus.NoMedia
        self._position=0;self._duration=0;self._ready=False;self._wanted=False;self._error=QMediaPlayer.Error.NoError;self._error_text='';self.tag=''
        for signal in ('positionChanged','durationChanged','playbackStateChanged','mediaStatusChanged','errorOccurred'):
            getattr(self.native,signal).connect(lambda *args,name=signal:getattr(self,name).emit(*args) if self.mode=='native' else None)
    def setAudioOutput(self,audio):
        self.audio=audio;self.native.setAudioOutput(audio);audio.volumeChanged.connect(lambda _:self.sync_volume());audio.mutedChanged.connect(lambda _:self.sync_volume())
    def ensure_browser(self):
        if self.browser:return
        if sys.platform=='win32':
            self.browser=EdgeBrowser(self.owner,self.receive);self.browser.owner_media=self;self.page=self.browser
        else:
            self.browser=QWebEngineView(self.owner);self.profile=QWebEngineProfile(self.browser);self.page=WidgetPage(self.profile,self.browser,self.receive);self.browser.setPage(self.page)
            settings=self.page.settings();settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture,False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,True)
        self.browser.resize(640,86);self.browser.setObjectName('soundcloudSource');self.browser.hide()
    def setSource(self,url):
        self.stop();self.tag=secrets.token_hex(12);self._source=QUrl(url)
        parsed=urlparse(url.toString());widget=parsed.scheme=='https' and parsed.hostname=='w.soundcloud.com' and parsed.path.startswith('/player/')
        if not widget:
            self.mode='native'
            if self.browser:self.browser.hide()
            self.native.setSource(url);return
        track=parse_qs(parsed.query).get('url',[''])[0];host=urlparse(track)
        if host.scheme!='https' or host.hostname not in ('soundcloud.com','m.soundcloud.com'):return
        self.native.setSource(QUrl());self.mode='soundcloud';self.ensure_browser();self.browser.hide()
        self._ready=False;self._wanted=False;self._position=0;self._duration=0;self._error=QMediaPlayer.Error.NoError;self._error_text=''
        self._status=QMediaPlayer.MediaStatus.LoadingMedia;self.mediaStatusChanged.emit(self._status);self.positionChanged.emit(0);self.durationChanged.emit(0)
        tag=json.dumps(self.tag);src=json.dumps(url.toString())
        html="""<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;background:#15151a;height:100%;overflow:hidden}iframe{width:100%;height:100%;border:0}</style></head><body>
<iframe id='sc' allow='autoplay; encrypted-media' title='SoundCloud'></iframe><script src='https://w.soundcloud.com/player/api.js'></script><script>
const TAG=__TAG__;function report(type,data={}){const payload={tag:TAG,type,...data};if(window.chrome&&window.chrome.webview)window.chrome.webview.postMessage(payload);else console.log('PULSE_SC:'+JSON.stringify(payload))}
const frame=document.getElementById('sc');frame.src=__SRC__;let W=SC.Widget(frame),ready=false,wanted=false,vol=65,pendingSeek=0;
window.pulseCommand=function(command,value){if(command==='volume')vol=value;if(command==='play')wanted=true;if(command==='pause'||command==='stop')wanted=false;if(command==='seek')pendingSeek=value;if(!ready)return;
if(command==='volume')W.setVolume(vol);if(command==='play')W.play();if(command==='pause'||command==='stop')W.pause();if(command==='seek')W.seekTo(value)};
W.bind(SC.Widget.Events.READY,()=>{ready=true;W.getDuration(duration=>{report('ready',{duration});W.setVolume(vol);if(pendingSeek)W.seekTo(pendingSeek);if(wanted)W.play()})});
W.bind(SC.Widget.Events.PLAY,()=>report('play'));W.bind(SC.Widget.Events.PAUSE,()=>report('pause'));
W.bind(SC.Widget.Events.PLAY_PROGRESS,event=>report('progress',{position:event.currentPosition}));
W.bind(SC.Widget.Events.SEEK,event=>report('seek',{position:event.currentPosition}));
W.bind(SC.Widget.Events.FINISH,()=>report('finish'));W.bind(SC.Widget.Events.ERROR,()=>report('error'));
</script></body></html>""".replace('__TAG__',tag).replace('__SRC__',src)
        self.page.setHtml(html,QUrl('https://pulse-player.local/'));self.sync_volume()
    def command(self,name,value=None):
        if self.browser and self.mode=='soundcloud':self.page.runJavaScript('window.pulseCommand&&window.pulseCommand('+json.dumps(name)+','+json.dumps(value)+')')
    def receive(self,event):
        if not isValid(self):return
        if event.get('host_error') and self.mode=='soundcloud':event={'tag':self.tag,'type':'error'}
        if self.mode!='soundcloud' or event.get('tag')!=self.tag:return
        kind=event['type']
        if kind=='ready':
            self._ready=True;self._duration=max(0,int(event.get('duration',0)));self.durationChanged.emit(self._duration)
            self._status=QMediaPlayer.MediaStatus.LoadedMedia;self.mediaStatusChanged.emit(self._status);self.sync_volume()
            if self._position:self.command('seek',self._position)
            if self._wanted:self.command('play')
        elif kind in ('progress','seek'):
            self._position=max(0,int(event.get('position',0)));self.positionChanged.emit(self._position)
        elif kind in ('play','pause'):
            self._state=QMediaPlayer.PlaybackState.PlayingState if kind=='play' else QMediaPlayer.PlaybackState.PausedState;self.playbackStateChanged.emit(self._state)
        elif kind=='finish':
            self._wanted=False;self._state=QMediaPlayer.PlaybackState.StoppedState;self.playbackStateChanged.emit(self._state);self._status=QMediaPlayer.MediaStatus.EndOfMedia;self.mediaStatusChanged.emit(self._status)
        elif kind=='error':
            self._wanted=False;self._error=QMediaPlayer.Error.NetworkError;self._error_text='SoundCloud Widget could not play this recording';self.errorOccurred.emit(self._error,self._error_text)
    def sync_volume(self):
        if self.audio:self.command('volume',0 if self.audio.isMuted() else round(self.audio.volume()*100))
    def play(self):
        if self.mode=='native':self.native.play();return
        self._wanted=True;self.command('play')
    def pause(self):
        if self.mode=='native':self.native.pause();return
        self._wanted=False;self.command('pause')
    def stop(self):
        if self.mode=='native':self.native.stop();return
        self._wanted=False;self.command('stop');self._state=QMediaPlayer.PlaybackState.StoppedState;self.playbackStateChanged.emit(self._state)
    def setPosition(self,value):
        if self.mode=='native':self.native.setPosition(value);return
        self._position=max(0,int(value));self.command('seek',self._position)
    def position(self):return self.native.position() if self.mode=='native' else self._position
    def duration(self):return self.native.duration() if self.mode=='native' else self._duration
    def playbackState(self):return self.native.playbackState() if self.mode=='native' else self._state
    def mediaStatus(self):return self.native.mediaStatus() if self.mode=='native' else self._status
    def source(self):return self.native.source() if self.mode=='native' else self._source
    def error(self):return self.native.error() if self.mode=='native' else self._error
    def errorString(self):return self.native.errorString() if self.mode=='native' else self._error_text

    def shutdown(self):
        self.stop();self.tag=''
        if isinstance(self.browser,EdgeBrowser):self.browser.shutdown()
