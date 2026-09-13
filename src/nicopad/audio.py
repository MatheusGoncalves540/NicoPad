"""Motor de áudio: dispositivos, sons na memória e mistura em tempo real.

A saída é sempre float32 estéreo na taxa nativa do dispositivo escolhido, para
não mexer nas configurações do Windows e manter a latência baixa.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

CHANNELS = 2
LATENCY = 0.03
MIC_BUFFER_SECONDS = 1.0
MAX_VOICES = 16

# Ordem de preferência das APIs de áudio do Windows (menor = melhor latência).
_HOSTAPI_RANK = {"Windows WASAPI": 0, "Windows DirectSound": 1, "MME": 2, "ASIO": 3}

# Nomes usados pelos cabos de áudio virtuais mais comuns (VB-Audio).
CABLE_HINTS = ("cable input", "voicemeeter input", "voicemeeter aux input")

# Atalhos do Windows: não são aparelhos de verdade, só nomes genéricos do sistema.
JUNK_HINTS = (
    "mapeador de som da microsoft",
    "microsoft sound mapper",
    "driver de som primário",
    "primary sound driver",
    "driver de captura de som primário",
    "primary sound capture driver",
    "mixagem estéreo",
    "stereo mix",
)

# APIs escondidas na lista: o portaudio as marca como experimentais e elas só
# repetem o mesmo aparelho com outro nome.
HIDDEN_APIS = ("Windows WDM-KS",)


@dataclass(frozen=True)
class Device:
    index: int
    name: str
    hostapi: str
    samplerate: float

    @property
    def label(self) -> str:
        return f"{self.name}  ·  {self.hostapi}"


def list_devices(kind: str) -> list:
    """Dispositivos de 'output' ou 'input', com as APIs boas primeiro."""
    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception:
        return []
    key = "max_output_channels" if kind == "output" else "max_input_channels"
    found = []
    for index, info in enumerate(devices):
        if info[key] < 1:
            continue
        hostapi = hostapis[info["hostapi"]]["name"] if info["hostapi"] < len(hostapis) else "?"
        found.append(
            Device(
                index=index,
                name=info["name"],
                hostapi=hostapi,
                samplerate=float(info["default_samplerate"]),
            )
        )
    found.sort(key=lambda device: (_HOSTAPI_RANK.get(device.hostapi, 9), device.name.lower()))
    return found


def visible_devices(devices: list) -> list:
    """A lista que o usuário vê: sem atalhos do Windows e sem o mesmo aparelho repetido.

    O mesmo aparelho aparece uma vez por API de áudio (WASAPI, DirectSound, MME...).
    Fica só o melhor, porque abrir o stream já tenta as outras APIs quando a
    primeira escolhida falha.
    """
    seen = set()
    found = []
    for device in devices:
        if device.hostapi in HIDDEN_APIS:
            continue
        name = device.name.lower()
        if any(hint in name for hint in JUNK_HINTS):
            continue
        key = device.name[:25].lower()  # o MME corta o nome em 31 letras
        if key in seen:
            continue
        seen.add(key)
        found.append(device)
    return found


def find_device(devices: list, name: str, hostapi: str = ""):
    """Reencontra um dispositivo salvo pelo nome: os índices mudam entre sessões.

    O MME corta o nome em 31 letras, então o mesmo aparelho aparece com nomes
    diferentes em cada API de áudio. A última tentativa compara pelo prefixo, e
    só aceita quando não sobra dúvida.
    """
    if not name:
        return None
    for device in devices:
        if device.name == name and device.hostapi == hostapi:
            return device
    for device in devices:
        if device.name == name:
            return device
    candidates = [device for device in devices if device.name[:25].lower() == name[:25].lower()]
    return candidates[0] if len(candidates) == 1 else None



def is_virtual_cable(device) -> bool:
    """True para cabos virtuais: o som vai para o mic sem sair no alto-falante."""
    return device is not None and any(hint in device.name.lower() for hint in CABLE_HINTS)


def guess_cable(devices: list):
    for device in devices:
        if is_virtual_cable(device):
            return device
    return None


def peaks(data: np.ndarray, columns: int) -> np.ndarray:
    """(columns, 2) com o mínimo e o máximo de cada faixa: a silhueta da onda."""
    columns = max(1, int(columns))
    out = np.zeros((columns, 2), dtype=np.float32)
    if not len(data):
        return out
    mono = data.mean(axis=1)
    for index, chunk in enumerate(np.array_split(mono, columns)):
        if len(chunk):
            out[index] = (chunk.min(), chunk.max())
    return out


def resample(data: np.ndarray, source_rate: float, target_rate: float) -> np.ndarray:
    """Ajusta a taxa por interpolação linear.

    PONYTAIL: interpolação linear é suficiente para efeitos curtos e só entra em
    ação quando a taxa do arquivo difere da taxa do dispositivo. Trocar por um
    resampler polifásico (ex.: scipy) se aparecer alias audível em músicas longas.
    """
    if not len(data) or source_rate == target_rate:
        return data
    count = max(1, int(round(len(data) * target_rate / source_rate)))
    target = np.linspace(0.0, len(data) - 1.0, count)
    source = np.arange(len(data), dtype=np.float64)
    out = np.empty((count, data.shape[1]), dtype=np.float32)
    for channel in range(data.shape[1]):
        out[:, channel] = np.interp(target, source, data[:, channel])
    return out


class Sound:
    """Um arquivo de som carregado na memória, pronto para tocar sem I/O."""

    def __init__(
        self,
        name: str,
        path: str,
        data: np.ndarray,
        samplerate: int,
        gain: float = 1.0,
        monitor: bool = True,
        monitor_gain: float = 1.0,
    ):
        self.name = name
        self.path = path
        self.data = data
        self.samplerate = samplerate
        # Ajustes do som individual, editados na janela «Configurar som».
        self.gain = float(gain)
        self.monitor = bool(monitor)
        self.monitor_gain = float(monitor_gain)
        self._cache = {}

    def at(self, samplerate: float) -> np.ndarray:
        """Amostras na taxa pedida (calculado uma vez por taxa)."""
        key = float(samplerate)
        ready = self._cache.get(key)
        if ready is None:
            ready = resample(self.data, self.samplerate, key)
            self._cache[key] = ready
        return ready


def load_sound(
    path,
    name: str | None = None,
    gain: float = 1.0,
    monitor: bool = True,
    monitor_gain: float = 1.0,
    start: float = 0.0,
    end: float = 0.0,
) -> Sound:
    """Carrega wav/mp3/ogg/flac/opus/aiff para a memória, sempre estéreo.

    `start`/`end` aparam o som em segundos (`end` 0 = até o fim do arquivo); o corte é
    aplicado antes de normalizar canais, então `Sound.data` já nasce aparado.
    """
    data, samplerate = sf.read(str(path), dtype="float32", always_2d=True)
    if not len(data):
        raise ValueError("arquivo de áudio vazio")
    first = max(0, int(start * samplerate))
    last = min(len(data), int(end * samplerate)) if end else len(data)
    if last - first < 1:  # corte inválido (arquivo trocado, JSON editado à mão): toca inteiro
        first, last = 0, len(data)
    data = data[first:last]
    if data.shape[1] > CHANNELS:
        data = data[:, :CHANNELS]
    elif data.shape[1] < CHANNELS:
        data = np.repeat(data[:, :1], CHANNELS, axis=1)
    return Sound(
        name=name or Path(path).stem,
        path=str(Path(path)),
        data=np.ascontiguousarray(data, dtype=np.float32),
        samplerate=int(samplerate),
        gain=gain,
        monitor=monitor,
        monitor_gain=monitor_gain,
    )


class MicBridge:
    """Leva o que foi capturado do microfone para dentro do stream de saída."""

    def __init__(self, seconds: float, samplerate: float):
        self._lock = threading.Lock()
        self._buffer = np.zeros((0, CHANNELS), dtype=np.float32)
        self._limit = max(1, int(seconds * samplerate))

    def write(self, data: np.ndarray) -> None:
        """Chamado pelo callback de entrada; sempre copia (o buffer é reusado)."""
        if data.shape[1] > CHANNELS:
            data = data[:, :CHANNELS]
        elif data.shape[1] < CHANNELS:
            data = np.repeat(data[:, :1], CHANNELS, axis=1)
        with self._lock:
            self._buffer = np.concatenate((self._buffer, data.astype(np.float32, copy=False)))
            if len(self._buffer) > self._limit:  # muito atrasado: descarta o passado
                self._buffer = self._buffer[-self._limit :]

    def read(self, frames: int) -> np.ndarray:
        """Chamado pelo callback de saída; completa com silêncio se faltar áudio."""
        out = np.zeros((frames, CHANNELS), dtype=np.float32)
        with self._lock:
            available = min(frames, len(self._buffer))
            if available:
                out[:available] = self._buffer[:available]
                self._buffer = self._buffer[available:]
        return out


class Mixer:
    """Mistura as vozes ativas de um stream. Um mixer por dispositivo de saída."""

    def __init__(self, samplerate: float, gain: float = 1.0, mic: MicBridge | None = None):
        self.samplerate = samplerate
        self.gain = gain
        self.mic = mic
        self._voices = []
        self._lock = threading.Lock()
        self.rendered = 0  # amostras já entregues: prova que o stream está puxando áudio

    def trigger(self, sound: Sound, gain: float = 1.0) -> None:
        """Chamado pela thread do hook: só enfileira a voz, nada de cálculo."""
        data = sound.at(self.samplerate)
        with self._lock:
            self._voices.append([data, 0, float(gain)])
            if len(self._voices) > MAX_VOICES:
                del self._voices[0]

    def stop_all(self) -> None:
        with self._lock:
            self._voices.clear()

    def render(self, frames: int) -> np.ndarray:
        block = np.zeros((frames, CHANNELS), dtype=np.float32)
        with self._lock:
            alive = []
            for voice in self._voices:
                data, position, gain = voice
                take = min(frames, len(data) - position)
                if take > 0:
                    block[:take] += data[position : position + take] * gain
                    voice[1] = position + take
                if voice[1] < len(data):
                    alive.append(voice)
            self._voices = alive
        if self.mic is not None:
            block += self.mic.read(frames)
        np.clip(block * self.gain, -1.0, 1.0, out=block)
        self.rendered += frames
        return block


class AudioEngine:
    """Toca os sons no dispositivo escolhido e, opcionalmente, no fone do usuário.

    O stream "monitor" recebe só os sons; o stream principal recebe os sons e,
    quando pedido, o áudio do microfone misturado (passa-voz).
    """

    def __init__(self):
        self.status = "parado"
        self.error = None
        self.warnings = []
        self.volume = 1.0
        self._out_mixer = None
        self._mon_mixer = None
        self._mic_bridge = None
        self._out_stream = None
        self._mon_stream = None
        self._in_stream = None

    def start(self, output, monitor=None, microphone=None, volume: float = 1.0, sounds=()) -> None:
        self.stop()
        self.volume = float(volume)
        if output is None:
            self.status = "sem saída escolhida"
            return
        try:
            self._out_mixer = Mixer(output.samplerate, gain=self.volume)
            self._out_stream = _open_output(output, self._callback(self._out_mixer))
        except Exception as exc:
            self._out_mixer = self._out_stream = None
            self.error = f"não consegui abrir «{output.name}»: {exc}"
            self.status = "parado"
            return
        if microphone is not None:
            self._open_microphone(microphone)
        if monitor is not None:
            try:
                self._mon_mixer = Mixer(monitor.samplerate, gain=self.volume)
                self._mon_stream = _open_output(monitor, self._callback(self._mon_mixer))
            except Exception as exc:
                self._mon_mixer = self._mon_stream = None
                self.warnings.append(f"monitor «{monitor.name}» indisponível: {exc}")
        self.prepare(sounds)
        details = [f"tocando em «{output.name}» ({output.samplerate:.0f} Hz)"]
        if self._mic_bridge is not None:
            details.append("microfone misturado")
        if self._mon_mixer is not None:
            details.append(f"monitor em «{monitor.name}»")
        self.status = " · ".join(details)

    def stop(self) -> None:
        for attribute in ("_in_stream", "_out_stream", "_mon_stream"):
            stream = getattr(self, attribute)
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass  # stream já fechado pelo sistema
            setattr(self, attribute, None)
        self._out_mixer = None
        self._mon_mixer = None
        self._mic_bridge = None
        self.warnings = []
        self.status = "parado"

    def trigger(self, sound: Sound) -> None:
        if self._out_mixer is not None:
            self._out_mixer.trigger(sound, sound.gain)
        if self._mon_mixer is not None and sound.monitor:
            self._mon_mixer.trigger(sound, sound.monitor_gain)

    def stop_all(self) -> None:
        for mixer in (self._out_mixer, self._mon_mixer):
            if mixer is not None:
                mixer.stop_all()
        sd.stop()  # também cala a prévia que tocou fora dos streams (sd.play)

    def preview(self, sound: Sound) -> None:
        """Ouvir localmente: usa o monitor se existir, senão o dispositivo padrão."""
        if self._mon_mixer is not None:
            self._mon_mixer.trigger(sound, sound.monitor_gain)
            return
        info = sd.query_devices(kind="output")
        rate = int(info["default_samplerate"])
        sd.play(sound.at(rate) * self.volume * sound.monitor_gain, rate)  # a prévia respeita o volume

    def set_volume(self, volume: float) -> None:
        self.volume = float(volume)
        for mixer in (self._out_mixer, self._mon_mixer):
            if mixer is not None:
                mixer.gain = self.volume

    def prepare(self, sounds) -> None:
        """Deixa as amostras prontas nas taxas dos streams ativos: nada de cálculo no hook."""
        for mixer in (self._out_mixer, self._mon_mixer):
            if mixer is None:
                continue
            for sound in sounds:
                sound.at(mixer.samplerate)

    def _callback(self, mixer: Mixer):
        def callback(outdata, frames, time_info, status):
            outdata[:] = mixer.render(frames)

        return callback

    def _open_microphone(self, device) -> None:
        target = self._out_mixer.samplerate
        bridge = MicBridge(MIC_BUFFER_SECONDS, target)
        # A taxa só é conhecida depois que o stream abre (a API usada pode ter outra).
        state = {"rate": device.samplerate, "ready": False}

        def callback(indata, frames, time_info, status):
            if not state["ready"]:
                return
            source = state["rate"]
            bridge.write(indata if source == target else resample(indata, source, target))

        try:
            stream = _open_input(device, callback)
        except Exception as exc:
            self.warnings.append(f"microfone «{device.name}» indisponível: {exc}")
            return
        state["rate"] = stream.samplerate
        state["ready"] = True
        self._mic_bridge = bridge
        self._in_stream = stream
        self._out_mixer.mic = bridge


def _output_stream(device: Device, callback):
    stream = sd.OutputStream(
        device=device.index,
        samplerate=device.samplerate,
        channels=CHANNELS,
        dtype="float32",
        latency=LATENCY,
        callback=callback,
    )
    # O sounddevice não inicia sozinho: sem o start() o callback nunca é chamado.
    stream.start()
    return stream



def _open_with_fallback(device: Device, kind: str, open_stream):
    """Abre o aparelho escolhido; se falhar, tenta o mesmo em outra API de áudio."""
    try:
        return open_stream(device)
    except Exception as first_error:
        prefix = device.name[:25].lower()  # o MME corta o nome em 31 letras
        for alternative in list_devices(kind):
            if alternative.hostapi == device.hostapi or alternative.name[:25].lower() != prefix:
                continue
            try:
                return open_stream(alternative)
            except Exception:
                continue
        raise first_error


def _open_output(device: Device, callback):
    return _open_with_fallback(device, "output", lambda chosen: _output_stream(chosen, callback))


def _open_input(device: Device, callback):
    return _open_with_fallback(device, "input", lambda chosen: _input_stream(chosen, callback))



def _input_channels(index: int) -> int:
    try:
        return int(sd.query_devices(index)["max_input_channels"])
    except Exception:
        return CHANNELS


def _input_stream(device: Device, callback):
    stream = sd.InputStream(
        device=device.index,
        samplerate=device.samplerate,
        channels=max(1, min(CHANNELS, _input_channels(device.index))),
        dtype="float32",
        latency=LATENCY,
        callback=callback,
    )
    stream.start()
    return stream
