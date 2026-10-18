"""Scrollable first-run authentication and explicit local sign-in."""
import hashlib,hmac,json,re,shutil,uuid
from PySide6.QtCore import Qt,QTimer,QRect,QEvent,QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget,QHBoxLayout,QLabel,QLayout

class Welcome:
    def __init__(self):
        super().__init__()
        if self.profile:self.remember_profile(self.profile)

    def build_profile(self):
        super().build_profile()
        form=self.profile_dialog.body.layout().itemAt(0).widget()
        self.profile_signout=self.button('Выйти',self.logout_profile)
        self.profile_signout.setToolTip('Выйти из профиля Pulse и открыть вход / регистрацию')
        form.layout().itemAt(0).layout().addWidget(self.profile_signout)

    def stored_profiles(self):
        try:
            path=self.data_dir/'profiles.json'
            if path.stat().st_size>2*1024*1024:return {}
            profiles=json.loads(path.read_text(encoding='utf8'))
            return {key:row for key,row in profiles.items() if isinstance(row,dict)} if isinstance(profiles,dict) else {}
        except (OSError,ValueError,TypeError):return {}

    def remember_profile(self,profile):
        if not profile.get('id'):return
        profiles=self.stored_profiles();record=dict(profile)
        record['_tour_completed']=(self.data_dir/'onboarding-v08.json').exists()
        avatar=self.data_dir/'avatar.png'
        if avatar.exists():
            key=hashlib.sha256(str(profile['id']).encode()).hexdigest()+'.png'
            folder=self.data_dir/'profile-avatars';folder.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(avatar,folder/key);record['_saved_avatar']=key
        profiles[str(profile['id'])]=record
        super().save_data('profiles.json',profiles)

    def save_data(self,name,value):
        super().save_data(name,value)
        if name=='profile.json' and isinstance(value,dict) and value.get('id'):self.remember_profile(value)

    def prepare_profile(self,record):
        """Restore profile details without inheriting another identity's password."""
        avatar=self.data_dir/'avatar.png';saved=record.get('_saved_avatar','')
        if re.fullmatch(r'[a-f0-9]{64}\.png',saved) and (self.data_dir/'profile-avatars'/saved).exists():shutil.copyfile(self.data_dir/'profile-avatars'/saved,avatar)
        else:avatar.unlink(missing_ok=True)
        if record.get('_tour_completed'):super().save_data('onboarding-v08.json',{'completed':True})
        else:(self.data_dir/'onboarding-v08.json').unlink(missing_ok=True)
        if hasattr(self,'profile_avatar'):self.profile_avatar.pixmap=None;self.profile_avatar.update();self.profile_nav.setIcon(QIcon())
        return {key:value for key,value in record.items() if not key.startswith('_')}

    def profile_for_identity(self,identity):
        profiles=self.stored_profiles()
        record=next((p for p in profiles.values() if p.get('provider')==identity['provider'] and str(p.get('provider_id'))==str(identity['provider_id'])),None)
        if record is None:record={'id':str(uuid.uuid4())}
        profile=self.prepare_profile(record)
        profile.pop('local_auth',None)
        profile.update(name=identity['name'],email=identity.get('email',''),provider=identity['provider'],provider_id=identity['provider_id'])
        return profile

    def logout_profile(self):
        if not self.profile:return
        try:
            self.remember_profile(self.profile)
            # An explicit empty active profile keeps the next launch signed out;
            # password hashes and profile details remain in the local account list.
            super().save_data('profile.json',{})
        except OSError:
            self.profile_saved.setText('Не удалось сохранить выход. Проверь доступ к папке данных.');return
        self.profile={};self.cancel_identity()
        self.choice_generation+=1;self.resolve_generation+=1;self.lyrics_version+=1
        self.choice_pending=False;self.loading_audio=False;self.restored_resume=None
        if self.sc_import_running:self.cancel_soundcloud_import()
        if self.tour:self.tour.hide();self.tour.deleteLater();self.tour=None
        self.sign_out();self.media.stop();self.media.setSource(QUrl());self.home_rows=[]
        self.seek.setRange(0,0);self.current_favorite.setChecked(False)
        self.name_edit.clear();self.bio_edit.clear();self.profile_saved.clear();self.register_name.clear();self.register_email.clear();self.register_password.clear()
        self.profile_nav.setToolTip('Вход в профиль Pulse');self.profile_nav.setIcon(QIcon())
        self.profile_avatar.pixmap=None;self.profile_avatar.update()
        self.hide_pages();self.open_registration();self.register_name.clear();self.register_email.clear()
        self.register_error.setText('Выход выполнен. Войди снова или открой «Регистрация». Музыка и настройки сохранены на этом компьютере.')
        self.fit_auth_form()

    def build_registration(self):
        super().build_registration()
        self.auth_mode='register'
        self.auth_card=self.register_button.parentWidget();box=self.auth_card.layout()
        self.auth_title=box.itemAt(0).widget();self.auth_hint=box.itemAt(1).widget()
        self.auth_name_label=box.itemAt(box.indexOf(self.register_name)-1).widget()
        self.auth_title.setWordWrap(True);self.auth_title.setContentsMargins(0,4,0,6)
        self.auth_title.setStyleSheet('font-size:28px;font-weight:800;letter-spacing:-.5px;')
        self.auth_card.setFixedWidth(480);box.setSpacing(12)
        # A real minimum size gives QScrollArea content to scroll instead of
        # compressing a tall centred form and clipping its first lines.
        box.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        outer=self.registration.body.layout();outer.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        outer.setContentsMargins(22,14,22,24)
        for index in range(outer.count()-1,-1,-1):
            if outer.itemAt(index).spacerItem():outer.takeAt(index)
        outer.setAlignment(Qt.AlignmentFlag.AlignTop);outer.addStretch(1)
        tabs=QWidget();row=QHBoxLayout(tabs);row.setContentsMargins(0,0,0,0);row.setSpacing(10)
        self.signin_tab=self.button('Вход',lambda:self.set_auth_mode('login'));self.signup_tab=self.button('Регистрация',lambda:self.set_auth_mode('register'))
        for button in (self.signin_tab,self.signup_tab):button.setCheckable(True);row.addWidget(button,1)
        box.insertWidget(2,tabs)
        self.local_auth_hint=QLabel();self.local_auth_hint.setWordWrap(True);self.local_auth_hint.setObjectName('muted');box.addWidget(self.local_auth_hint)
        self.auth_card.installEventFilter(self)
        self.set_auth_mode('login')

    def fit_auth_form(self):
        box=self.auth_card.layout();width=self.auth_card.width()-box.contentsMargins().left()-box.contentsMargins().right()
        for label in self.auth_card.findChildren(QLabel):
            if not label.wordWrap():continue
            label.ensurePolished()
            height=label.fontMetrics().boundingRect(QRect(0,0,width,10000),Qt.TextFlag.TextWordWrap,label.text()).height()+12 if label.text() else 0
            if label.minimumHeight()!=height:label.setMinimumHeight(height)
        height=box.heightForWidth(self.auth_card.width())
        if height>0 and self.auth_card.minimumHeight()!=height:self.auth_card.setMinimumHeight(height)

    def eventFilter(self,watched,event):
        if watched==getattr(self,'auth_card',None) and event.type() in (QEvent.Type.LayoutRequest,QEvent.Type.Resize):QTimer.singleShot(0,self.fit_auth_form)
        return super().eventFilter(watched,event)

    def set_auth_mode(self,mode):
        if getattr(self,'identity_flow',None):self.cancel_identity()
        self.auth_mode=mode;login=mode=='login';self.signin_tab.setChecked(login);self.signup_tab.setChecked(not login)
        self.auth_name_label.setVisible(not login);self.register_name.setVisible(not login)
        self.auth_title.setText('С возвращением' if login else 'Твоя музыка начинается здесь')
        self.auth_title.ensurePolished()
        title_height=self.auth_title.fontMetrics().boundingRect(QRect(0,0,450,1000),Qt.TextFlag.TextWordWrap,self.auth_title.text()).height()
        self.auth_title.setMinimumHeight(title_height+14)
        self.auth_hint.setText('Войди через Google или Telegram. Для локального профиля используй почту и пароль, сохранённые на этом компьютере.' if login else 'Создай профиль на этом компьютере или войди через Google / Telegram.')
        self.registration.setWindowTitle('Вход в Pulse' if login else 'Регистрация в Pulse')
        self.register_button.setText('Войти' if login else 'Создать профиль')
        self.register_password.setPlaceholderText('Пароль' if login else 'Придумай пароль · минимум 6 символов')
        self.register_password.clear();self.register_error.clear()
        self.local_auth_hint.setText('Локальный профиль не переносится между компьютерами автоматически. Любимые и настройки общие для этой копии Pulse.' if login else 'Локальная почта не проверяется. Пароль хранится в виде защищённого хеша.')
        self.fit_auth_form()
        def top():
            scroll=self.registration.body.parentWidget().parentWidget()
            if hasattr(scroll,'verticalScrollBar'):scroll.verticalScrollBar().setValue(0)
        QTimer.singleShot(0,top)

    def open_registration(self):
        super().open_registration();self.set_auth_mode('login')

    def register_local(self):
        if getattr(self,'auth_mode','register')=='login':self.login_local();return
        email=self.register_email.text().strip().casefold()
        if any(p.get('local_auth') and p.get('provider') not in ('google','telegram') and p.get('email','').casefold()==email for p in self.stored_profiles().values()):
            self.register_error.setText('Этот локальный профиль уже сохранён. Открой «Вход» и введи его пароль.');return
        valid=len(self.register_name.text().strip())>=2 and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) and len(self.register_password.text())>=6
        if valid:
            if self.profile:self.remember_profile(self.profile)
            self.profile=self.prepare_profile({})
        super().register_local()

    def login_local(self):
        try:
            profiles=self.stored_profiles()
            current=json.loads((self.data_dir/'profile.json').read_text(encoding='utf8')) if (self.data_dir/'profile.json').exists() else {}
            if current.get('id'):profiles[current['id']]=current
            email=self.register_email.text().strip().casefold()
            stored=next((p for p in profiles.values() if p.get('local_auth') and p.get('provider') not in ('google','telegram') and p.get('email','').casefold()==email),{})
            auth=stored.get('local_auth')
            if not auth:
                self.register_error.setText('На этом компьютере ещё нет локального профиля с этой почтой. Используй Google / Telegram или вкладку «Регистрация».');return
            iterations=int(auth['iterations'])
            if auth.get('algorithm')!='pbkdf2-sha256' or not 100000<=iterations<=1000000:raise ValueError()
            salt=bytes.fromhex(auth['salt']);expected=bytes.fromhex(auth['hash'])
            if len(salt)!=16 or len(expected)!=32:raise ValueError()
            actual=hashlib.pbkdf2_hmac('sha256',self.register_password.text().encode(),salt,iterations)
            valid=hmac.compare_digest(actual,expected) and hmac.compare_digest(self.register_email.text().strip().casefold().encode(),stored.get('email','').casefold().encode())
        except (OSError,ValueError,TypeError,KeyError):
            self.register_error.setText('На этом компьютере ещё нет локального профиля. Открой «Регистрация» или войди через Google / Telegram.');return
        if not valid:self.register_error.setText('Почта или пароль не совпадают. Проверь их и попробуй снова.');return
        self.profile=self.prepare_profile(stored);self.save_data('profile.json',self.profile);self.register_password.clear();self.name_edit.setText(stored.get('name',''));self.bio_edit.setText(stored.get('bio',''));self.refresh_profile()
        self.registration.accept();self.set_registration_gate(False);self.maybe_tour()
