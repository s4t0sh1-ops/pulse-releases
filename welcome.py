"""Scrollable first-run authentication and explicit local sign-in."""
import hashlib,hmac,json
from PySide6.QtCore import Qt,QTimer,QRect,QEvent
from PySide6.QtWidgets import QWidget,QHBoxLayout,QLabel,QLayout

class Welcome:
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
        self.local_auth_hint.setText('Локальный профиль не переносится между компьютерами автоматически.' if login else 'Локальная почта не проверяется. Пароль хранится в виде защищённого хеша.')
        self.fit_auth_form()
        def top():
            scroll=self.registration.body.parentWidget().parentWidget()
            if hasattr(scroll,'verticalScrollBar'):scroll.verticalScrollBar().setValue(0)
        QTimer.singleShot(0,top)

    def open_registration(self):
        super().open_registration();self.set_auth_mode('login')

    def register_local(self):
        if getattr(self,'auth_mode','register')=='login':self.login_local();return
        super().register_local()

    def login_local(self):
        try:
            stored=json.loads((self.data_dir/'profile.json').read_text(encoding='utf8'))
            auth=stored.get('local_auth')
            if not auth:
                self.register_error.setText('Локального входа с паролем здесь нет. Используй Google / Telegram или вкладку «Регистрация».');return
            iterations=int(auth['iterations'])
            if auth.get('algorithm')!='pbkdf2-sha256' or not 100000<=iterations<=1000000:raise ValueError()
            salt=bytes.fromhex(auth['salt']);expected=bytes.fromhex(auth['hash'])
            if len(salt)!=16 or len(expected)!=32:raise ValueError()
            actual=hashlib.pbkdf2_hmac('sha256',self.register_password.text().encode(),salt,iterations)
            valid=hmac.compare_digest(actual,expected) and hmac.compare_digest(self.register_email.text().strip().casefold().encode(),stored.get('email','').casefold().encode())
        except (OSError,ValueError,TypeError,KeyError):
            self.register_error.setText('На этом компьютере ещё нет локального профиля. Открой «Регистрация» или войди через Google / Telegram.');return
        if not valid:self.register_error.setText('Почта или пароль не совпадают. Проверь их и попробуй снова.');return
        self.profile=stored;self.register_password.clear();self.name_edit.setText(stored.get('name',''));self.refresh_profile()
        self.registration.accept();self.set_registration_gate(False);self.maybe_tour()
