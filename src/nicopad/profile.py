"""Perfil: sons + configuração em um único .zip, para levar de uma máquina a outra.

O .zip leva a configuração (som, tecla, volumes) e os arquivos de som. Na volta,
os sons são descompactados na pasta escolhida e a configuração passa a apontar
para essas cópias, então o perfil não depende de onde os originais estavam.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import asdict
from pathlib import Path

from nicopad import config as cfg, library

MANIFEST = cfg.FILENAME
SOUNDS = "sons"


def export(settings, target) -> tuple:
    """Grava a configuração e os arquivos de som em um .zip.

    Devolve (sons gravados, nomes que não existem mais no disco).
    """
    payload = asdict(settings)
    missing = []
    kept = []
    used = set()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry, binding in zip(payload["bindings"], settings.bindings):
            source = Path(binding.path)
            if not source.is_file():
                missing.append(binding.name or source.name)
                continue
            name = _free_name(used, source.name)
            used.add(name.casefold())
            archive.write(source, f"{SOUNDS}/{name}")
            entry["profile_path"] = name
            kept.append(entry)
        payload["bindings"] = kept
        archive.writestr(MANIFEST, json.dumps(payload, indent=2, ensure_ascii=False))
    return len(kept), missing


def load(source, folder) -> tuple:
    """Descompacta os sons do perfil em `folder`.

    Devolve (configuração pronta para usar, sons carregados, nomes que faltaram).
    """
    with zipfile.ZipFile(source) as archive:
        payload = json.loads(archive.read(MANIFEST).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("o perfil não tem configuração")
        found = _extract_sounds(archive, Path(folder))
    bindings = []
    missing = []
    for entry in payload.get("bindings") or []:
        if not isinstance(entry, dict):
            continue
        name = Path(str(entry.get("profile_path") or entry.get("path") or "")).name
        local = found.get(name)
        if local is None:
            missing.append(name)
            continue
        entry = dict(entry, path=str(local))
        entry.pop("profile_path", None)
        bindings.append(entry)
    payload["bindings"] = bindings
    settings, _warning = _settings(payload)
    settings.geometry = ""  # o tamanho da janela é de quem importa, não do perfil
    return settings, len(bindings), missing


def _settings(payload) -> tuple:
    """Reaproveita a leitura tolerante do config gravando o manifesto num temporário."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / MANIFEST
        path.write_text(json.dumps(payload), encoding="utf-8")
        return cfg.load(path)


def _extract_sounds(archive, folder: Path) -> dict:
    """Descompacta só a pasta de sons, recusando caminhos que escapem dela."""
    folder.mkdir(parents=True, exist_ok=True)
    root = folder.resolve()
    found = {}
    for info in archive.infolist():
        if info.is_dir() or not info.filename.startswith(SOUNDS + "/"):
            continue
        name = Path(info.filename).name
        target = (folder / name).resolve()
        if not name or target.parent != root:
            raise ValueError(f"o perfil tem um caminho suspeito: {info.filename}")
        if target.exists() and target.stat().st_size != info.file_size:
            target = library.free_name(folder, name)  # nunca sobrescreve outro arquivo
        with archive.open(info) as packed, open(target, "wb") as unpacked:
            shutil.copyfileobj(packed, unpacked)
        found[name] = target
    return found


def _free_name(used: set, name: str) -> str:
    """Nome livre dentro do .zip: dois sons podem ter o mesmo nome em pastas diferentes."""
    candidate = Path(name).name
    counter = 1
    while candidate.casefold() in used:
        counter += 1
        candidate = f"{Path(name).stem} ({counter}){Path(name).suffix}"
    return candidate
