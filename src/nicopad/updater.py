"""Atualização automática: confere a última release no GitHub e roda o instalador dela.

Cada release traz o instalador completo (não um patch), então qualquer versão, por mais
antiga que seja, atualiza direto para a última: o instalador só troca os arquivos por cima.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from nicopad import __version__

REPO = "MatheusGoncalves540/NicoPad"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
_API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
_ASSET_NAME = "nicopad-setup.exe"


def _parse(version: str) -> tuple:
    parts = "".join(char if char.isdigit() else " " for char in version).split()
    return tuple(int(part) for part in parts) or (0,)


def check(timeout: float = 8.0):
    """(versão nova, URL do instalador) quando existe uma release mais nova; None senão."""
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
    """Baixa o instalador para a pasta temporária."""
    target = Path(tempfile.gettempdir()) / _ASSET_NAME
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - URL da própria release do GitHub
        target.write_bytes(response.read())
    if target.stat().st_size < 1_000_000:  # um instalador de verdade não cabe em menos de 1 MB
        target.unlink(missing_ok=True)
        raise ValueError("o arquivo baixado parece incompleto")
    return target


def apply_and_restart(installer: Path) -> None:
    """Roda o instalador em silêncio e encerra este processo para liberar os arquivos.

    O instalador fecha o que ainda estiver aberto, troca os arquivos e reabre o nicoPad.
    """
    subprocess.Popen([str(installer), "/SILENT", "/NORESTART", "/SUPPRESSMSGBOXES"], close_fds=True)
    sys.exit(0)
