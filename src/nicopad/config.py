"""Configuração do nicoPad: um JSON simples ao lado do executável (portátil)."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

FILENAME = "nicopad.json"

# Nome antigo do arquivo: quem já usava o app antes do nome novo continua encontrando a
# configuração. Ela é lida de lá uma vez e regravada com o nome atual.
LEGACY = "soundpad.json"


def config_path() -> Path:
    """Fica ao lado do .exe (portátil); no código-fonte, na raiz do projeto."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / FILENAME
    return Path(__file__).resolve().parents[2] / FILENAME


@dataclass
class Binding:
    """Uma tecla do teclado ligada a um arquivo de som."""

    path: str
    name: str = ""
    vk: int = 0
    extended: bool = False
    key: str = ""
    gain: float = 1.0  # volume deste som no microfone
    monitor: bool = True  # este som toca também no meu fone?
    monitor_gain: float = 1.0  # volume deste som no meu fone


@dataclass
class Settings:
    output: dict = field(default_factory=dict)
    monitor_enabled: bool = False
    monitor: dict = field(default_factory=dict)
    mic_enabled: bool = False
    microphone: dict = field(default_factory=dict)
    volume: float = 1.0
    geometry: str = ""
    library_enabled: bool = True  # guardar uma cópia dos sons em pasta própria
    library: str = ""  # pasta própria; vazio usa a pasta padrão do sistema
    bindings: list = field(default_factory=list)


def _device(raw) -> dict:
    if isinstance(raw, dict) and raw.get("name"):
        return {"name": str(raw["name"]), "hostapi": str(raw.get("hostapi") or "")}
    return {}


def _level(value, default: float = 1.0) -> float:
    """Volume entre 0 e 1; qualquer coisa estranha cai no padrão."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default



def _binding(raw):
    if not isinstance(raw, dict) or not raw.get("path"):
        return None
    try:
        vk = int(raw.get("vk") or 0)
    except (TypeError, ValueError):
        vk = 0
    return Binding(
        path=str(raw["path"]),
        name=str(raw.get("name") or Path(str(raw["path"])).stem),
        vk=vk,
        extended=bool(raw.get("extended")),
        key=str(raw.get("key") or ""),
        gain=_level(raw.get("gain")),
        monitor=bool(raw.get("monitor", True)),
        monitor_gain=_level(raw.get("monitor_gain")),
    )


def _keep_broken(path: Path) -> Path:
    """Cópia do arquivo ilegível: o app reescreve o original no primeiro salvamento."""
    broken = path.with_name(path.name + ".invalido")
    try:
        broken.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    except OSError:
        pass  # sem cópia, o aviso na tela continua valendo
    return broken


def load(path=None) -> tuple:
    """Lê a configuração. Nunca quebra: devolve (config, aviso)."""
    path = Path(path) if path else config_path()
    if path.name == FILENAME and not path.exists():
        older = path.with_name(LEGACY)
        if older.exists():
            path = older
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings(), None
    except ValueError as exc:  # JSON quebrado: guarda cópia, senão o app grava por cima
        broken = _keep_broken(path)
        return Settings(), f"configuração ilegível ({exc}); cópia em {broken.name}"
    except OSError as exc:
        return Settings(), f"configuração ignorada ({exc})"
    if not isinstance(raw, dict):
        return Settings(), f"configuração ignorada ({path})"
    volume = raw.get("volume")
    settings = Settings(
        output=_device(raw.get("output")),
        monitor_enabled=bool(raw.get("monitor_enabled")),
        monitor=_device(raw.get("monitor")),
        mic_enabled=bool(raw.get("mic_enabled")),
        microphone=_device(raw.get("microphone")),
        volume=float(volume) if isinstance(volume, (int, float)) else 1.0,
        geometry=str(raw.get("geometry") or "")[:32],
        library_enabled=bool(raw.get("library_enabled", True)),
        library=str(raw.get("library") or ""),
    )
    settings.bindings = [item for item in (_binding(entry) for entry in raw.get("bindings") or []) if item]
    return settings, None


def save(settings: Settings, path=None) -> str | None:
    """Grava a configuração (troca atômica). Devolve o erro, quando houver."""
    path = Path(path or config_path())
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        return f"não consegui salvar a configuração: {exc}"
    return None
