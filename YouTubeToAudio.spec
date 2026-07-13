# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['yt_to_audio.pyw'],
    pathex=[],
    binaries=[],
    datas=[('payment-qrcode.png', '.'), ('C:\\Users\\brent\\AppData\\Local\\Python\\pythoncore-3.14-64\\tcl\\tcl8.6', 'tcl/tcl8.6'), ('C:\\Users\\brent\\AppData\\Local\\Python\\pythoncore-3.14-64\\tcl\\tk8.6', 'tcl/tk8.6'), ('ffmpeg', 'ffmpeg')],
    hiddenimports=['tkinter', 'tkinter.filedialog', 'tkinter.font', 'tkinter.messagebox', 'tkinter.scrolledtext', 'tkinter.ttk'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='YouTubeToAudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
