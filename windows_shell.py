"""Keep the same Windows identity and explicit native icons across releases."""
import ctypes
import sys
from pathlib import Path

APP_ID = 'Pulse.Desktop.Player.Clean'

def prepare_application(app):
    from PySide6.QtGui import QIcon
    asset = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'pulse.ico'
    from PySide6.QtGui import QFontDatabase,QFont
    font=asset.parent/'fonts'/'Manrope.ttf'
    if font.exists():QFontDatabase.addApplicationFont(str(font))
    ui_font=QFont('Manrope',10);ui_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias);ui_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting);app.setFont(ui_font)
    app.setWindowIcon(QIcon(str(asset)))
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass

def apply_window_icon(window):
    if sys.platform != 'win32':return
    from ctypes import wintypes
    user = ctypes.windll.user32
    user.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                               ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user.LoadImageW.restype = wintypes.HANDLE
    user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.SendMessageW.restype = ctypes.c_ssize_t
    path = str(Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'pulse.ico')
    handles = getattr(window, '_shell_icons', [])
    for kind, size in ((0, 32), (1, 64)):
        icon = user.LoadImageW(None, path, 1, size, size, 0x10)
        if icon:
            user.SendMessageW(int(window.winId()), 0x80, kind, int(icon))
            handles.append(icon)
    window._shell_icons = handles

def release_window_icons(window):
    if sys.platform == 'win32':
        destroy = ctypes.windll.user32.DestroyIcon
        destroy.argtypes = [ctypes.c_void_p]
        for icon in getattr(window, '_shell_icons', []):destroy(icon)
        window._shell_icons = []
