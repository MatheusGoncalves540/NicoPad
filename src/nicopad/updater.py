"""Atualização automática: confere a última release no GitHub e troca o .exe.

Sem instalador: baixa o novo nicopad.exe e um `.bat` descartável faz a troca
depois que este processo fecha (o Windows não deixa sobrescrever o próprio
.exe rodando).
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from nicopad import __version__

REPO = "MatheusGoncalves540/NicoPad"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
_API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
_ASSET_NAME = "nicopad.exe"


def _parse(version: str) -> tuple:
    parts = "".join(char if char.isdigit() else " " for char in version).split()
    return tuple(int(part) for part in parts) or (0,)


def check(timeout: float = 8.0):
    """(versão nova, URL do .exe) quando existe uma release mais nova; None senão."""
    request = urllib.request.Request(_API_URL, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL fixa e https
        release = json.loads(response.read())
    latest = str(release.get("tag_name") or "").strip()
    if not latest or _parse(latest) <= _parse(__version__):
        return None
    for asset in release.get("assets") or []:
        if asset.get("name") == _ASSET_NAME:
            return latest, asset["browser_download_url"]
    return None


def download(url: str) -> Path:
    """Baixa o novo .exe ao lado do atual, como `nicopad.exe.novo`."""
    target = Path(sys.executable).resolve().with_name("nicopad.exe.novo")
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - URL da própria release do GitHub
        target.write_bytes(response.read())
    if target.stat().st_size < 1_000_000:  # um .exe de verdade não cabe em menos de 1 MB
        target.unlink(missing_ok=True)
        raise ValueError("o arquivo baixado parece incompleto")
    return target


def apply_and_restart(new_exe: Path) -> None:
    """Troca o .exe atual pelo novo e reabre; este processo termina em seguida.

    A troca roda num `.bat` à parte: tenta mover até o arquivo antigo ser
    liberado (o que acontece assim que este processo sai) e se autodestrói.
    """
    current = Path(sys.executable).resolve()
    script = current.with_name("nicopad_update.bat")
    script.write_text(
        "@echo off\r\n"
        ":retry\r\n"
        f'move /y "{new_exe}" "{current}" >nul 2>&1\r\n'
        "if errorlevel 1 (timeout /t 1 /nobreak >nul & goto retry)\r\n"
        f'start "" "{current}"\r\n'
        'del "%~f0"\r\n',
        encoding="mbcs",
    )
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(0)
