# -*- mode: python ; coding: utf-8 -*-
"""Build do nicoPad: pasta dist/nicopad, só com o que o app realmente usa (o instalador a empacota)."""

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

# Logo: ícone do executável e imagem mostrada na janela. Fonte Archivo (OFL): embutida, nunca cai em outra.
datas.append((os.path.join(ROOT, "packaging", "nicopad.png"), "."))
datas.append((os.path.join(ROOT, "packaging", "fonts"), "fonts"))
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
    "tkinter", "_tkinter",  # a interface é Qt (PySide6); os módulos Qt que não usamos nem entram
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

# O PyInstaller/hooks arrastam coisas que o app nunca carrega: renderizador OpenGL por
# software (20 MB), Qt Quick/Qml/Pdf/Network, plugins de rede, traduções do Qt e os
# codecs AVIF/WebP do Pillow (a bandeja só usa PNG).
UNUSED = (
    "opengl32sw", "d3dcompiler", "qt6quick", "qt6qml", "qt6pdf", "qt6network", "qt6opengl",
    "qt6virtualkeyboard", "qdirect2d", "/plugins/tls/", "networkinformation", "pyside6/translations",
    "pyside6/qml", "pil/_avif", "pil/_webp",
)


def _used(entry):
    name = entry[0].replace("\\", "/").lower()
    return not any(part in name for part in UNUSED)


analysis.binaries = [item for item in analysis.binaries if _used(item)]
analysis.datas = [item for item in analysis.datas if _used(item)]

pyz = PYZ(analysis.pure)

# Pasta (não arquivo único): o instalador comprime tudo junto e o app abre sem
# descompactar 190 MB no %TEMP% a cada execução.
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
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

coll = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="nicopad")
