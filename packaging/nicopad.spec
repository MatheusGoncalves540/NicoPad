# -*- mode: python ; coding: utf-8 -*-
"""Build do nicoPad: um único .exe, só com o que o app realmente usa."""

import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
SRC = os.path.join(ROOT, "src")

# As DLLs nativas (PortAudio e libsndfile) vivem dentro desses pacotes.
datas, binaries, hiddenimports = [], [], []
for package in ("sounddevice", "soundfile", "_sounddevice_data", "_soundfile_data", "yt_dlp"):
    try:
        collected = collect_all(package)
    except Exception:
        continue
    datas += collected[0]
    binaries += collected[1]
    hiddenimports += collected[2]

# Pacote oficial do VB-Cable, embutido sem nenhuma modificação (a licença
# permite difundir AS IS; quem instala o driver é o usuário).
datas.append((os.path.join(ROOT, "packaging", "vbcable"), "vbcable"))

# Logo: ícone do executável e imagem mostrada na janela.
datas.append((os.path.join(ROOT, "packaging", "nicopad.png"), "."))
ICON = os.path.join(ROOT, "packaging", "nicopad.ico")

EXCLUDES = [
    # bibliotecas pesadas que o app não importa
    "scipy", "matplotlib", "pandas", "cv2", "IPython",
    # ferramentas de desenvolvimento e testes
    # (NÃO excluir "distutils": no Python 3.12 ele só existe via alias do
    # setuptools, e o próprio hook do PyInstaller cuida disso; excluir na mão
    # colide com o alias e quebra o build)
    "pytest", "setuptools", "pip", "wheel", "pkg_resources",
    "unittest", "doctest", "pydoc", "test", "lib2to3",
    "numpy.f2py", "numpy.distutils", "numpy.testing",
    "tkinter.test", "tkinter.tix", "tkinter.dnd",
]

analysis = Analysis(
    [os.path.join(SRC, "nicopad", "__main__.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="nicopad",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)
