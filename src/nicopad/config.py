"""Configuração do nicoPad: um JSON simples ao lado do executável (portátil)."""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

FILENAME = "nicopad.json"

# Nome antigo do arquivo: quem já usava o app antes do nome novo continua encontrando a
# configuração. Ela é lida de lá uma vez e regravada com o nome atual.
LEGACY = "soundpad.json"

THEMES = ("claro", "escuro")
VIEWS = ("lista", "pads")


def is_first_run() -> bool:
    """True quando ainda não existe configuração nenhuma (nem a do nome antigo)."""
    path = config_path()
    return not path.exists() and not path.with_name(LEGACY).exists()


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
    start: float = 0.0  # segundos aparados do começo
    end: float = 0.0  # segundo onde o som acaba; 0 = até o fim do arquivo


@dataclass
class KeyMap:
    name: str = "Padrão"
    bindings: list = field(default_factory=list)


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
    maps: list = field(default_factory=list)
    active: int = 0
    close_action: str = ""  # "" pergunta sempre; "hide" bandeja; "quit" encerra
    stop_vk: int = 0  # tecla global de "parar tudo"; 0 = sem tecla definida
    stop_extended: bool = False
    stop_key: str = ""
    theme: str = ""  # "claro" | "escuro"; vazio segue o tema do sistema
    view: str = "lista"  # "lista" | "pads"
    setup_done: bool = False  # o assistente de primeiro uso já foi concluído (ou pulado)

    def __post_init__(self):
        if not self.maps:
            self.maps = [KeyMap()]
        self.active = max(0, min(int(self.active or 0), len(self.maps) - 1))

    @property
    def bindings(self) -> list:  # o mapa ativo; `maps` é o que vai para o JSON
        return self.maps[self.active].bindings


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


def _seconds(value) -> float:
    """Segundos (>= 0); qualquer coisa não-finita ou negativa vira 0."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return 0.0
    return seconds if math.isfinite(seconds) and seconds >= 0 else 0.0


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
        start=_seconds(raw.get("start")),
        end=_seconds(raw.get("end")),
    )


def _keymap(raw) -> KeyMap:
    if not isinstance(raw, dict):
        return KeyMap()
    bindings = [item for item in (_binding(entry) for entry in raw.get("bindings") or []) if item]
    return KeyMap(name=str(raw.get("name") or "Padrão"), bindings=bindings)


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
    try:
        stop_vk = int(raw.get("stop_vk") or 0)
    except (TypeError, ValueError):
        stop_vk = 0
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
        close_action=raw.get("close_action") if raw.get("close_action") in ("hide", "quit") else "",
        stop_vk=stop_vk,
        stop_extended=bool(raw.get("stop_extended")),
        stop_key=str(raw.get("stop_key") or ""),
        theme=raw.get("theme") if raw.get("theme") in THEMES else "",
        view=raw.get("view") if raw.get("view") in VIEWS else "lista",
        setup_done=bool(raw.get("setup_done")),
    )
    raw_maps = raw.get("maps")
    if isinstance(raw_maps, list) and raw_maps:
        settings.maps = [_keymap(entry) for entry in raw_maps]
    elif isinstance(raw.get("bindings"), list) and raw["bindings"]:
        migrated = [item for item in (_binding(entry) for entry in raw["bindings"]) if item]
        settings.maps = [KeyMap("Padrão", migrated)]
    else:
        settings.maps = [KeyMap()]
    settings.active = max(0, min(int(raw.get("active") or 0), len(settings.maps) - 1))
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
