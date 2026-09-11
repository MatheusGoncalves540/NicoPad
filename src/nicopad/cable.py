"""Pacote oficial do VB-Cable: entrega AS IS, sem instalar o driver por você.

A licença do VB-Cable permite copiar e difundir o pacote sem nenhuma
modificação, mas proíbe integrá-lo ao processo de instalação de outro programa.
Por isso o nicoPad só copia e descompacta o pacote original na sua pasta e abre
ela: quem executa o VBCABLE_Setup_x64.exe é você, como manda a licença.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PACKAGE = "VBCABLE_Driver_Pack45.zip"
SHA256 = "b950e39f01af1d04ea623c8f6d8eb9b6ea5c477c637295fabf20631c85116bfb"
URL = "https://download.vb-audio.com/Download_CABLE/" + PACKAGE
SITE = "https://vb-audio.com/Cable/"

# A própria licença pede para citar a origem e o modelo donationware.
CREDIT = (
    "VB-Cable é donationware de Vincent Burel (www.vb-cable.com).\n"
    "O pacote é entregue sem nenhuma modificação e a instalação do driver é feita por você.\n"
    "Se ele for útil, considere participar do projeto."
)


def default_folder() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "nicoPad" / "cabo-de-audio"


def bundled() -> Path | None:
    """Pacote embutido no executável — ou no projeto, rodando do código-fonte."""
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / "vbcable" / PACKAGE)
    candidates.append(Path(__file__).resolve().parents[2] / "packaging" / "vbcable" / PACKAGE)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(target) -> Path:
    """Baixa o pacote original quando o embutido não existe (rodando do fonte)."""
    target = Path(target)
    partial = target.with_name(target.name + ".parcial")
    with urllib.request.urlopen(URL, timeout=120) as response:  # noqa: S310 - URL fixa e https
        partial.write_bytes(response.read())
    digest = sha256(partial)
    if digest != SHA256:
        partial.unlink(missing_ok=True)
        raise ValueError(f"o pacote baixado não confere (sha256 {digest})")
    partial.replace(target)
    return target


def _extract(package: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    with zipfile.ZipFile(package) as archive:
        for member in archive.namelist():
            if not str((target / member).resolve()).startswith(str(root)):
                raise ValueError(f"pacote suspeito: {member}")
        archive.extractall(target)


def prepare(destination=None) -> tuple:
    """Copia o pacote original e descompacta (o fluxo que a VB-Audio recomenda).

    Devolve (caminho do setup a executar, pasta aberta para o usuário).
    """
    folder = Path(destination) if destination else default_folder()
    package = folder / PACKAGE
    source = bundled()
    if source is not None:
        if sha256(source) != SHA256:
            raise ValueError("o pacote embutido foi alterado (sha256 diferente)")
        if not package.is_file() or sha256(package) != SHA256:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, package)
    elif not (package.is_file() and sha256(package) == SHA256):
        download(package)
    unpacked = folder / Path(PACKAGE).stem
    _extract(package, unpacked)
    setup = unpacked / "VBCABLE_Setup_x64.exe"
    if not setup.is_file():
        setup = unpacked / "VBCABLE_Setup.exe"
    if not setup.is_file():
        raise ValueError("o pacote não trouxe o programa de instalação")
    return setup, folder


def reveal(path) -> None:
    """Abre a pasta no Explorer já com o arquivo selecionado."""
    try:
        subprocess.Popen(["explorer", "/select,", str(path)])
    except OSError:
        os.startfile(str(Path(path).parent))
