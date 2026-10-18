from pathlib import Path

a = Analysis(
    [str(Path(SPECPATH) / 'main.py')],
    pathex=[], binaries=[], datas=[(str(Path(SPECPATH)/'soundcloud-host'),'soundcloud-host'),(str(Path(SPECPATH)/'identity-config.json'),'.'),(str(Path(SPECPATH)/'pulse.ico'),'.'),(str(Path(SPECPATH)/'backgrounds'),'backgrounds'),(str(Path(SPECPATH)/'fonts'),'fonts')], hiddenimports=[], hookspath=[], hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngineQuick', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets'],
    noarchive=False,
)
# Qt uses Windows' ICU. A similarly named DLL from other installed tools can
# have incompatible exports; leave ICU resolution to the operating system.
a.binaries = [(dest, src, kind) for dest, src, kind in a.binaries
              if Path(dest).name.lower() != 'icuuc.dll']
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='Pulse-0.13', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=True, console=False,icon=str(Path(SPECPATH)/'pulse.ico'))
