"""Pasta própria dos sons: o app deixa de depender dos arquivos originais.

Cada som adicionado (ou trazido por um perfil) pode ganhar uma cópia nessa pasta.
Assim mover, renomear ou apagar o arquivo original não quebra mais o atalho.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path


def default_folder() -> Path:
    """Pasta dos sons de cada sistema: `.../nicoPad/sons` no Windows, `.../nicopad/sons` no Linux.

    Windows: %PROGRAMDATA% (cai para %LOCALAPPDATA% e, por fim, para a pasta do usuário).
    Linux/macOS: $XDG_DATA_HOME ou ~/.local/share.
    """
    if os.name == "nt":
        base = os.environ.get("PROGRAMDATA") or os.environ.get("LOCALAPPDATA")
        return Path(base or Path.home()) / "nicoPad" / "sons"
    base = os.environ.get("XDG_DATA_HOME")
    return Path(base or Path.home() / ".local" / "share") / "nicopad" / "sons"


def inside(path, folder) -> bool:
    """True quando o arquivo já está dentro da pasta própria."""
    path = Path(path).resolve()
    folder = Path(folder).resolve()
    return path.parent == folder or folder in path.parents


def free_name(folder, name: str) -> Path:
    """Um caminho livre em `folder`: nunca sobrescreve (nome, nome (2), nome (3)...)."""
    folder = Path(folder)
    name = Path(name).name
    target = folder / name
    counter = 1
    while target.exists():
        counter += 1
        target = folder / f"{Path(name).stem} ({counter}){Path(name).suffix}"
    return target


def same_file(first, second) -> bool:
    """Mesmo tamanho e mesmo conteúdo: evita guardar duas cópias do mesmo arquivo."""
    try:
        if Path(first).stat().st_size != Path(second).stat().st_size:
            return False
    except OSError:
        return False
    return _digest(first) == _digest(second)


def copy_in(source, folder) -> Path:
    """Copia o som para a pasta própria e devolve o caminho usado.

    Se já existir um arquivo idêntico lá, reaproveita; se existir um diferente com
    o mesmo nome, grava com outro nome (nunca sobrescreve nada).
    """
    source = Path(source)
    folder = Path(folder)
    if inside(source, folder):
        return source
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / source.name
    if target.exists():
        if same_file(source, target):
            return target
        target = free_name(folder, source.name)
    shutil.copy2(source, target)
    return target


_FORBIDDEN = '<>:"/\\|?*'


def rename_in(path, name: str) -> Path | None:
    """Renomeia o arquivo da pasta própria para o novo nome.

    Devolve o caminho novo, ou None quando não deu (nome inválido ou arquivo em uso).
    Nada é sobrescrito: nome já usado vira `nome (2).wav`.
    """
    path = Path(path)
    stem = _clean_stem(name) or path.stem
    target = path.with_name(stem + path.suffix)
    if target == path:
        return path
    if target.exists():
        target = free_name(path.parent, target.name)
    try:
        path.rename(target)
    except OSError:
        return None
    return target


def _clean_stem(name: str) -> str:
    """Tira do nome só o que o Windows recusa em arquivo; sem pontos nem espaços nas pontas."""
    clean = "".join("_" if char in _FORBIDDEN or ord(char) < 32 else char for char in name)
    return clean.strip(" .")[:80]


def reveal(folder) -> None:
    """Abre a pasta no Explorer (Windows) ou no gerenciador de arquivos (Linux/macOS)."""
    try:
        if os.name == "nt":
            os.startfile(str(Path(folder)))
        else:
            subprocess.Popen(["xdg-open", str(Path(folder))])
    except OSError:
        pass


def _digest(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
