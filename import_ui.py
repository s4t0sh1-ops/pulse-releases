from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QVBoxLayout,QLabel,QPlainTextEdit,QFileDialog,QProgressBar
from pages import InAppPage
from soundcloud_import import SoundCloudImport,urls_from_text,urls_from_file,ImportInputError

class ImportUI:
    def __init__(self):
        self.sc_import_generation=0;self.sc_import_running=False
        super().__init__()
        section=self.import_yandex.parentWidget().layout()
        self.import_yandex.setText('Импортировать лайки Яндекса')
        self.import_soundcloud=self.button('Импортировать из SoundCloud',self.open_soundcloud_import)
        section.insertWidget(section.indexOf(self.import_result)+1,self.import_soundcloud)

    def open_soundcloud_import(self):
        if hasattr(self,'sc_import_page'):self.sc_import_page.show();return
        self.sc_import_page=InAppPage(self.content_host,'Импорт из SoundCloud');box=QVBoxLayout(self.sc_import_page.body);box.setContentsMargins(24,18,24,24);box.setSpacing(14)
        hint=QLabel('Введи имя профиля SoundCloud или вставь ссылку на него. Мы найдём открытые лайки и добавим их в любимое без повторов.');hint.setWordWrap(True);box.addWidget(hint)
        self.sc_import_urls=QPlainTextEdit();self.sc_import_urls.setPlaceholderText('Имя профиля или ссылка SoundCloud');self.sc_import_urls.setMinimumHeight(64);self.sc_import_urls.setMaximumHeight(86);box.addWidget(self.sc_import_urls)
        box.addWidget(self.button('Вставить из буфера',lambda:self.sc_import_urls.setPlainText(QApplication.clipboard().text())))
        self.sc_import_start=self.button('Импортировать лайки',self.begin_soundcloud_import,primary=True);box.addWidget(self.sc_import_start)
        self.sc_import_file=self.button('Выбрать CSV / JSON / TXT со ссылками',self.choose_soundcloud_import_file);box.addWidget(self.sc_import_file)
        self.sc_import_progress=QProgressBar();self.sc_import_progress.hide();box.addWidget(self.sc_import_progress)
        self.sc_import_status=QLabel();self.sc_import_status.setWordWrap(True);box.addWidget(self.sc_import_status)
        self.sc_import_cancel=self.button('Остановить импорт',self.cancel_soundcloud_import);self.sc_import_cancel.hide();box.addWidget(self.sc_import_cancel)
        note=QLabel('SoundCloud может открыть только часть лайков или плейлиста. Pulse сообщит об этом. Для большого списка можно импортировать файл со ссылками; пароль и API-ключ не нужны. Переносятся ссылки и названия, а не аудиофайлы.');note.setObjectName('muted');note.setWordWrap(True);box.addWidget(note);box.addStretch();self.sc_import_page.show()

    def choose_soundcloud_import_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Список треков SoundCloud','','Список треков (*.csv *.json *.txt)')
        if not path:return
        try:urls=urls_from_file(path)
        except Exception as exc:self.sc_import_status.setText(str(exc) if isinstance(exc,ImportInputError) else 'Не удалось прочитать файл. Нужен CSV, JSON или TXT в UTF-8 со ссылками SoundCloud.');return
        self.begin_soundcloud_import(urls)

    def begin_soundcloud_import(self,urls=None):
        if self.sc_import_running:return
        if not isinstance(urls,list):urls=urls_from_text(self.sc_import_urls.toPlainText())
        if not urls:self.sc_import_status.setText('Введи имя профиля или ссылку на SoundCloud');return
        self.sc_import_generation+=1;generation=self.sc_import_generation;self.sc_import_running=True
        self.sc_import_start.setEnabled(False);self.sc_import_file.setEnabled(False);self.sc_import_cancel.show();self.sc_import_progress.show();self.sc_import_progress.setValue(0);self.sc_import_status.setText('Читаю доступные треки SoundCloud…')
        service=SoundCloudImport(self.soundcloud)
        def done(result):
            if generation!=self.sc_import_generation:return
            self.finish_soundcloud_import();added=0;duplicates=0
            incoming={}
            for row in result['rows']:
                if row['id'] in self.favorites:duplicates+=1
                else:incoming[row['id']]=row;added+=1
            self.favorites={**incoming,**self.favorites}
            self.save_data('favorites.json',self.favorites);self.refresh_profile()
            text=f'Добавлено: {added}. Уже были в любимых: {duplicates}.'
            if result['skipped']:text+=f' Не удалось прочитать ссылок: {result["skipped"]}.'
            if result['partial']:text+=' SoundCloud открыл только часть списка. Чтобы перенести остальное, добавь файл со ссылками на нужные треки.'
            if not result['rows']:text+=' Треки не получены: проверь публичность и правильность ссылки.'
            self.sc_import_status.setText(text);self.sc_import_progress.setValue(100)
        job=self.task(lambda signals:service.collect(urls,signals.progress.emit,lambda:generation!=self.sc_import_generation or getattr(self,'closing',False)),done)
        job.sc_import=True;job.sc_import_generation=generation;job.signals.progress.connect(lambda n:self.sc_import_progress.setValue(n) if generation==self.sc_import_generation else None)

    def finish_soundcloud_import(self):
        self.sc_import_running=False;self.sc_import_start.setEnabled(True);self.sc_import_file.setEnabled(True);self.sc_import_cancel.hide()

    def cancel_soundcloud_import(self):
        self.sc_import_generation+=1;self.finish_soundcloud_import();self.sc_import_status.setText('Импорт остановлен. Существующие любимые сохранены.')

    def job_failed(self,payload):
        _,job=payload
        if getattr(job,'sc_import',False):
            self.jobs.discard(job)
            if job.sc_import_generation==self.sc_import_generation:self.finish_soundcloud_import();self.sc_import_status.setText('Не удалось прочитать SoundCloud. Проверь ссылку и подключение, затем повтори.')
            return
        super().job_failed(payload)
