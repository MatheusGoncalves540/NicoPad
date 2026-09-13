"""Verificação automática do nicoPad, sem abrir a interface.

`task test` roda no código-fonte; `task verify` roda dentro do .exe compilado.
Sai com código 1 se algo falhar e grava o relatório em nicopad-selftest.txt.
"""

from __future__ import annotations

import json
import math
import struct
import sys
import tempfile
import time
import wave
import zipfile
from pathlib import Path

REPORT = "nicopad-selftest.txt"


def _tone(path, samplerate=44100, seconds=0.2, frequency=440.0):
    """WAV estéreo de teste, gerado na hora (não depende de arquivo externo)."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(samplerate)
        frames = bytearray()
        for index in range(int(samplerate * seconds)):
            value = int(12000 * math.sin(2 * math.pi * frequency * index / samplerate))
            frames += struct.pack("<hh", value, value)
        handle.writeframes(bytes(frames))
    return path


def _extra_checks(check, wav) -> None:
    """Verificações das partes novas: lista de aparelhos, pasta dos sons e perfis."""
    import numpy as np

    from nicopad import config as cfg, library, profile, youtube
    from nicopad.audio import Device, Mixer, Sound, load_sound, peaks, visible_devices

    folder = Path(wav).parent

    def device_filter():
        devices = [
            Device(1, "Alto-falantes (High Definition Audio Device)", "Windows WASAPI", 48000.0),
            Device(2, "Alto-falantes (High Definition ", "MME", 44100.0),
            Device(3, "Mapeador de som da Microsoft - Output", "MME", 44100.0),
            Device(4, "Output (VB-Audio Point)", "Windows WDM-KS", 48000.0),
        ]
        visible = visible_devices(devices)
        assert [device.index for device in visible] == [1], [device.name for device in visible]
        return "repetido por outra API, atalho do Windows e WDM-KS ficaram fora da lista"

    def sound_levels():
        sound = Sound("tom", "tom.wav", np.full((4000, 2), 0.5, dtype=np.float32), 44100)
        assert abs(sound.gain - 1.0) < 1e-9 and sound.monitor and abs(sound.monitor_gain - 1.0) < 1e-9
        mixer = Mixer(44100)
        mixer.trigger(sound, 0.5)
        peak = float(np.abs(mixer.render(1000)).max())
        assert abs(peak - 0.25) < 1e-6, peak
        return "volume do som individual entra na mistura"

    def sounds_folder():
        assert library.default_folder().name == "sons", library.default_folder()
        target = folder / "copia"
        first = library.copy_in(wav, target)
        assert first.is_file() and first.parent == target, first
        assert library.inside(first, target), first
        assert library.copy_in(wav, target) == first, "arquivo idêntico foi copiado de novo"
        other = folder / "outra"
        other.mkdir()
        (other / first.name).write_bytes(b"outro conteudo")
        assert library.copy_in(other / first.name, target).name != first.name, "não sobrescreveu cópia diferente"
        renamed = library.rename_in(first, "meu som:válido?")
        assert renamed is not None and renamed.name == f"meu som_válido_{first.suffix}", renamed
        assert renamed.read_bytes() == Path(wav).read_bytes(), "o conteúdo mudou ao renomear"
        assert library.rename_in(renamed, "   ") == renamed, "nome vazio deveria deixar o arquivo como está"
        return "pasta padrão, cópia reaproveitada, renomeada quando é diferente e nome novo no arquivo"

    def profile_roundtrip():
        shared = cfg.Binding(
            path=str(wav), name="tom", vk=70, key="F", gain=0.5, monitor=False, monitor_gain=0.3, start=0.05, end=0.15
        )
        settings = cfg.Settings(
            volume=0.4,
            maps=[
                cfg.KeyMap("Padrão", [shared, cfg.Binding(path=str(folder / "nao-existe.wav"), name="sumiu")]),
                cfg.KeyMap("Jogos", [cfg.Binding(path=str(wav), name="tom2", vk=71, key="G")]),
            ],
        )
        package = folder / "perfil.zip"
        count, missing = profile.export(settings, package)
        assert count == 2 and missing == ["sumiu"], (count, missing)
        with zipfile.ZipFile(package) as archive:
            sons = [n for n in archive.namelist() if n.startswith(f"{profile.SOUNDS}/")]
            assert len(sons) == 1, sons  # o mesmo arquivo nos dois mapas = uma cópia só no zip
        restored, imported, absent = profile.load(package, folder / "perfil")
        assert (imported, absent) == (2, []), (imported, absent)
        assert not restored.geometry, restored.geometry
        assert len(restored.maps) == 2, restored.maps
        first, second = restored.maps[0].bindings[0], restored.maps[1].bindings[0]
        assert first.vk == 70 and first.key == "F", first
        assert (first.gain, first.monitor, first.monitor_gain) == (0.5, False, 0.3), first
        assert (first.start, first.end) == (0.05, 0.15), first
        assert Path(first.path) == Path(second.path), "os dois mapas deveriam apontar para a mesma cópia"
        assert Path(first.path).parent == (folder / "perfil").resolve(), first.path
        assert Path(first.path).read_bytes() == Path(wav).read_bytes(), "o som do perfil saiu diferente"
        return "dois mapas, som compartilhado numa cópia só, com corte preservado"

    def keymaps():
        old = folder / "formato-antigo.json"
        old.write_text(json.dumps({"bindings": [{"path": str(wav), "name": "legado"}]}), encoding="utf-8")
        migrated, _warning = cfg.load(old)
        assert len(migrated.maps) == 1 and migrated.maps[0].name == "Padrão", migrated.maps
        assert migrated.bindings[0].name == "legado", migrated.bindings

        path = folder / "dois-mapas.json"
        settings = cfg.Settings(
            maps=[
                cfg.KeyMap("Padrão", [cfg.Binding(path=str(wav), name="a")]),
                cfg.KeyMap("Jogos", [cfg.Binding(path=str(wav), name="b")]),
            ],
            active=1,
        )
        assert not cfg.save(settings, path), "falhou ao gravar"
        loaded, warning = cfg.load(path)
        assert warning is None, warning
        assert [m.name for m in loaded.maps] == ["Padrão", "Jogos"], loaded.maps
        assert loaded.active == 1 and loaded.bindings[0].name == "b", (loaded.active, loaded.bindings)

        # active fora do intervalo cai no último mapa válido; com um mapa só, isso é o índice 0.
        raw = json.loads(old.read_text(encoding="utf-8"))
        raw["active"] = 99
        old.write_text(json.dumps(raw), encoding="utf-8")
        fixed, _warning = cfg.load(old)
        assert fixed.active == 0, fixed.active
        return "formato antigo migra para «Padrão», dois mapas vão e voltam, active fora do intervalo cai em 0"

    def trimming():
        clip = load_sound(wav, start=0.05, end=0.15)
        assert abs(len(clip.data) / clip.samplerate - 0.1) < 0.01, clip.data.shape
        whole = load_sound(wav)
        inverted = load_sound(wav, start=0.15, end=0.05)  # corte absurdo: toca inteiro
        assert len(inverted.data) == len(whole.data), (len(inverted.data), len(whole.data))
        table = peaks(whole.data, 100)
        assert table.shape == (100, 2), table.shape
        assert abs(float(table.max()) - float(whole.data.max())) < 1e-6, (table.max(), whole.data.max())
        return "corte aplicado na carga, corte inválido toca o som inteiro, peaks() bate com o pico do sinal"

    def youtube_url():
        assert youtube.check_url("file:///c:/x.mp3") is not None
        assert youtube.check_url(str(folder / "musica.mp3")) is not None
        assert youtube.check_url("") is not None
        assert youtube.check_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is None
        return "check_url recusa file:/caminho local/vazio e aceita uma URL https"

    def tray_icon():
        from nicopad import tray, ui

        icon = tray.Tray(ui._asset("nicopad.png"), lambda: None, lambda: None)
        assert icon.start(), icon.error
        deadline = time.time() + 5
        while not icon.ok and time.time() < deadline:  # o backend avisa quando o ícone existe
            time.sleep(0.05)
        assert icon.ok, icon.error or "o ícone não apareceu na bandeja"
        icon.stop()
        assert not icon.ok, "o ícone deveria sair da bandeja"
        return "ícone criado na bandeja, pronto para o clique e removido"

    check("lista de aparelhos", device_filter)
    check("volume por som", sound_levels)
    check("pasta dos sons", sounds_folder)
    check("perfil (.zip)", profile_roundtrip)
    check("mapas de teclas", keymaps)
    check("corte do som", trimming)
    check("download do youtube", youtube_url)
    check("bandeja do sistema", tray_icon)



def run() -> int:
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    from nicopad import config as cfg
    from nicopad.audio import AudioEngine, Mixer, list_devices, load_sound
    from nicopad.audio import MicBridge
    from nicopad.hotkeys import KeyboardHook, key_name

    results = []

    def check(label, action):
        try:
            results.append((True, label, str(action() or "ok")))
        except Exception as exc:
            results.append((False, label, f"{type(exc).__name__}: {exc}"))

    check("numpy", lambda: np.__version__)
    check("sounddevice", lambda: sd.__version__)
    check("soundfile", lambda: f"{sf.__version__} (libsndfile {sf.__libsndfile_version__})")
    check("dispositivos de saída", lambda: f"{len(list_devices('output'))} encontrado(s)")
    check("dispositivos de entrada", lambda: f"{len(list_devices('input'))} encontrado(s)")

    with tempfile.TemporaryDirectory() as folder:
        wav = _tone(Path(folder) / "tom.wav")

        def reading():
            sound = load_sound(wav)
            assert sound.data.shape == (8820, 2), sound.data.shape
            assert sound.samplerate == 44100, sound.samplerate
            return f"{sound.data.shape[0]} amostras estéreo a {sound.samplerate} Hz"

        def resampling():
            data = load_sound(wav).at(48000)
            expected = round(8820 * 48000 / 44100)
            assert abs(len(data) - expected) <= 1, (len(data), expected)
            return f"{data.shape[0]} amostras a 48000 Hz"

        def mixing():
            sound = load_sound(wav)
            mixer = Mixer(44100)
            assert not mixer.render(1024).any(), "não deveria tocar nada ainda"
            mixer.trigger(sound)
            block = mixer.render(1024)
            assert np.abs(block).max() > 0.1, "nada tocou depois do gatilho"
            return f"pico {float(np.abs(block).max()):.2f}"

        def mic_bridge():
            bridge = MicBridge(1.0, 8000)
            bridge.write(np.full((400, 2), 0.5, dtype=np.float32))
            assert abs(float(bridge.read(400).mean()) - 0.5) < 1e-6
            assert not bridge.read(100).any(), "leitura extra deveria ser silêncio"
            return "microfone entra na saída"

        def engine():
            devices = list_devices("output")
            if not devices:
                return "sem saída de áudio: ignorado"
            device = next((d for d in devices if d.index == sd.default.device[1]), None)
            if device is None:
                return "dispositivo padrão fora da lista: ignorado"
            sound = load_sound(wav)
            engine = AudioEngine()
            # volume 0: exercita o caminho inteiro sem fazer barulho na sala
            engine.start(device, monitor=device, volume=0.0, sounds=[sound])
            try:
                assert engine.error is None, engine.error
                assert engine._out_stream is not None, engine.error
                assert engine._out_stream.active, "o stream de saída não foi iniciado"
                assert engine._mon_stream is not None, engine.warnings
                assert engine._mon_stream.active, "o stream do monitor não foi iniciado"
                engine.trigger(sound)
                time.sleep(0.5)
                assert engine._out_mixer.rendered > 1000, "a saída não puxou áudio"
                assert engine._mon_mixer.rendered > 1000, "o monitor não puxou áudio"
            finally:
                engine.stop()
            return f"{device.name!r}: saída e monitor puxando áudio"

        def microphone_stream():
            inputs = list_devices("input")
            outputs = [d for d in list_devices("output") if d.index == sd.default.device[1]]
            if not inputs or not outputs:
                return "sem microfone ou saída: ignorado"
            engine = AudioEngine()
            engine.start(outputs[0], microphone=inputs[0], volume=0.0, sounds=[])
            try:
                assert engine.error is None, engine.error
                assert not engine.warnings, engine.warnings
                assert engine._in_stream is not None, engine.warnings
                assert engine._in_stream.active, "o stream do microfone não foi iniciado"
            finally:
                engine.stop()
            return f"passa-voz ativo em {inputs[0].name!r}"

        def hotkeys():
            seen = []
            hook = KeyboardHook(lambda vk, extended, name: seen.append(vk))
            hook.start()
            try:
                assert hook._thread_id, "thread do hook não subiu"
                assert hook._hook, hook.error or "hook não instalado"
            finally:
                hook.stop()
            sem_nome = [
                f"{vk:#x}"
                for vk, scan in ((0xA1, 0x36), (0x5B, 0x5B))
                if key_name(vk, scan, True).startswith("VK ")
            ]
            assert not sem_nome, f"teclas sem nome: {sem_nome}"
            return f"hook global instalado e removido; Shift direito = {key_name(0xA1, 0x36, True)!r}"

        def configuration():
            assert cfg.Settings().library_enabled is True, "a pasta dos sons deve vir ligada por padrão"
            old = Path(folder) / "sem-chave.json"
            old.write_text('{"volume": 0.5}', encoding="utf-8")
            antes, _ = cfg.load(old)
            assert antes.library_enabled, "configuração sem a chave deveria ligar a pasta dos sons"
            path = Path(folder) / "nicopad.json"
            settings = cfg.Settings(
                volume=0.5,
                geometry="1000x700",
                maps=[
                    cfg.KeyMap(
                        bindings=[
                            cfg.Binding(
                                path=str(wav), name="tom", vk=70, key="F", gain=0.25, monitor=False, monitor_gain=0.75
                            )
                        ]
                    )
                ],
            )
            assert not cfg.save(settings, path), "falhou ao gravar"
            loaded, warning = cfg.load(path)
            assert warning is None, warning
            assert abs(loaded.volume - 0.5) < 1e-9, loaded.volume
            assert loaded.geometry == "1000x700", loaded.geometry
            assert loaded.bindings[0].vk == 70 and loaded.bindings[0].key == "F", loaded.bindings[0]
            assert (loaded.bindings[0].gain, loaded.bindings[0].monitor) == (0.25, False), loaded.bindings[0]
            assert abs(loaded.bindings[0].monitor_gain - 0.75) < 1e-9, loaded.bindings[0]
            broken = path.with_name("quebrado.json")
            broken.write_text("{isto não é json", encoding="utf-8")
            ignored, warning = cfg.load(broken)
            assert warning and not ignored.bindings, warning
            assert broken.with_name(broken.name + ".invalido").is_file(), "faltou a cópia do arquivo ilegível"
            return "JSON gravado, relido e cópia de segurança do arquivo ilegível"

        check("carregar wav", reading)
        check("reamostar 44100 -> 48000", resampling)
        check("mistura dos sons", mixing)
        check("ponte do microfone", mic_bridge)
        check("motor de áudio", engine)

        check("microfone (passa-voz)", microphone_stream)

        def cable_package():
            import zipfile

            from nicopad import cable

            package = cable.bundled()
            assert package is not None, "o pacote oficial do VB-Cable não está embutido"
            digest = cable.sha256(package)
            assert digest == cable.SHA256, digest
            with zipfile.ZipFile(package) as archive:
                assert "VBCABLE_Setup_x64.exe" in archive.namelist(), archive.namelist()[:5]
            return f"{cable.PACKAGE} íntegro ({package.stat().st_size} bytes)"
        check("atalhos globais", hotkeys)

        check("pacote do cabo de áudio", cable_package)
        check("configuração", configuration)

        def device_matching():
            from nicopad.audio import Device, find_device

            wasapi = Device(1, "Alto-falantes (High Definition Audio Device)", "Windows WASAPI", 48000.0)
            assert find_device([wasapi], "Alto-falantes (High Definition ", "MME") is wasapi
            assert find_device([wasapi], wasapi.name, wasapi.hostapi) is wasapi
            assert find_device([wasapi], "nada a ver", "") is None
            return "acha o aparelho mesmo com o nome cortado pelo MME"

        check("reencontro de dispositivos", device_matching)

        def interface():
            import tkinter

            from nicopad import ui

            assert ui.NicoPadApp is not None, "classe da interface ausente"
            assert ui._window_size("1000x700+50+50") == "1000x700"
            assert ui._window_size("300x200") == "700x440", "tamanho salvo abaixo do mínimo"
            assert ui._window_size("") == ui.WINDOW_SIZE
            assert ui._window_size("lixo") == ui.WINDOW_SIZE
            return f"tkinter {tkinter.TkVersion} carregado; tamanho da janela saneado"

        check("módulo da interface", interface)
        _extra_checks(check, wav)

    failed = [result for result in results if not result[0]]
    lines = [
        "nicoPad - verificacao automatica",
        f"python {sys.version.split()[0]} | congelado: {bool(getattr(sys, 'frozen', False))}",
        "",
    ]
    lines += [f"[{'OK  ' if ok else 'FALHA'}] {label}: {detail}" for ok, label, detail in results]
    lines += ["", f"{len(results) - len(failed)}/{len(results)} verificacoes passaram"]
    report = "\n".join(lines)
    try:
        print(report)
    except Exception:
        pass  # no .exe sem console não existe stdout
    try:
        Path(REPORT).write_text(report + "\n", encoding="utf-8")
    except OSError:
        pass
    return 1 if failed else 0
