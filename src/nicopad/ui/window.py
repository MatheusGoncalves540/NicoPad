"""Janela principal do nicoPad (direção 1a «Painel»): barra lateral, lista/pads, status e assistente."""

from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLineEdit,
    QMainWindow,
    QMenu,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QWidget,
)

from nicopad import __version__, cable, config as cfg, library, profile, theme, tray, updater
from nicopad.audio import (
    AudioEngine,
    Sound,
    find_device,
    guess_cable,
    is_virtual_cable,
    list_devices,
    load_sound,
    visible_devices,
)
from nicopad.hotkeys import KeyboardHook, key_name
from nicopad.ui import dialogs
from nicopad.ui.lists import ListView, PadView, RowState, seconds_text
from nicopad.ui.playing import PlayingWindow
from nicopad.ui.widgets import Box, Button, Icon, Text, hbox, vbox
from nicopad.ui.wizard import LogoTile, Wizard

AUDIO_FILTER = "Áudio (*.wav *.mp3 *.ogg *.oga *.opus *.flac *.aiff *.aif);;Todos os arquivos (*.*)"
CABLE_URL = "https://vb-audio.com/Cable/"
ESC = 0x1B
WINDOW_SIZE = (1180, 728)
WINDOW_MIN = (900, 600)
TICK_MS = 33  # ~30 fps, só enquanto algum som toca


def _asset(name: str) -> Path | None:
    """Arte e fonte do app: embutidas no .exe ou na pasta packaging, rodando do fonte."""
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / name)
    candidates.append(Path(__file__).resolve().parents[3] / "packaging" / name)
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _window_size(saved: str) -> tuple:
    """Tamanho salvo da janela (área do cliente). A posição fica a cargo do Windows."""
    width, separator, height = (saved or "").lower().partition("+")[0].partition("x")
    if separator and width.isdigit() and height.isdigit():
        return max(WINDOW_MIN[0], int(width)), max(WINDOW_MIN[1], int(height))
    return WINDOW_SIZE


def _shorten(text, limit: int = 52) -> str:
    text = str(text)
    if len(text) <= limit:
        return text
    half = max(8, limit // 2 - 1)
    return f"{text[:half]}…{text[-half:]}"


def _default(devices: list, index: int):
    return next((device for device in devices if device.index == index), None)


def _device_dict(device) -> dict:
    return {"name": device.name, "hostapi": device.hostapi} if device else {}


class Bus(QObject):
    """Leva trabalho de outras threads (atalhos, bandeja, downloads) para a thread da interface."""

    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run)  # método de QObject: a chamada cai na thread que criou o Bus

    @Slot(object)
    def _run(self, function) -> None:
        function()


class SearchField(QLineEdit):
    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
        else:
            super().keyPressEvent(event)


class NicoPadApp(QMainWindow):
    def __init__(self, settings, warning: str | None = None, first_run: bool = False, services: bool = True):
        super().__init__()
        self.settings = settings
        self.bus = Bus()
        self.engine = AudioEngine()
        self.hook = KeyboardHook(self._on_hotkey)
        self.sounds = {}
        self.outputs, self.inputs, self.cables, self.output_choices = [], [], [], []
        self.keymap = {}
        self.pending = None  # índice do som (ou "stop") esperando a próxima tecla
        self.selected = None
        self.message = None
        self.query = ""
        self.voices = []  # o que o motor está tocando agora (engine.active()), sem os testes
        self.progress = {}  # caminho -> fração tocada: o progresso dos pads e linhas
        self.playing_window = None
        self.ready = False
        self.closing = False
        self.load_warning = warning
        self.save_error = None
        self.last_folder = ""
        self.typing = False  # campo de texto em foco: as teclas não tocam sons
        self.view_mode = settings.view
        self.logo = self._load_logo()

        self._save_timer = QTimer(self, singleShot=True, interval=400)
        self._save_timer.timeout.connect(self._save)
        self._flash_timer = QTimer(self, singleShot=True)
        self._flash_timer.timeout.connect(self._clear_message)
        self._tick_timer = QTimer(self, interval=TICK_MS)
        self._tick_timer.timeout.connect(self._tick)
        QApplication.instance().focusChanged.connect(lambda _old, new: setattr(self, "typing", isinstance(new, QLineEdit)))

        # A bandeja é a porta de volta quando a janela fecha: sem ela, fechar fecha mesmo.
        self.tray = tray.Tray(
            _asset("nicopad.png"),
            lambda: self.bus.call.emit(self._show),
            lambda: self.bus.call.emit(self._quit),
        )

        self.setWindowTitle("nicoPad")
        if self.logo is not None:
            self.setWindowIcon(QIcon(self.logo))
        self.setMinimumSize(*WINDOW_MIN)
        self.resize(*_window_size(settings.geometry))
        self._build()
        self.sync_maps()
        self.reload_devices()
        self._load_bindings()
        self._restore_devices()
        self._sync_toggles()
        self._apply_view()
        self._sync_theme_button()
        self._sync_stop_key()
        if services:
            self.hook.start()
        self.ready = True
        self.restart_engine()
        if services:
            self.tray.start()
            if getattr(sys, "frozen", False):  # rodando do fonte não tem .exe para trocar
                QTimer.singleShot(3000, self._check_updates)
        if first_run or (not settings.setup_done and self.cable_device() is None):
            self.show_wizard(1)

    # ---------------------------------------------------------------- interface

    @staticmethod
    def _load_logo() -> QPixmap | None:
        path = _asset("nicopad.png")
        if path is None:
            return None
        pixmap = QPixmap()
        return pixmap if pixmap.loadFromData(path.read_bytes()) else None  # lido dos bytes: o caminho pode ter acentos

    def _build(self) -> None:
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        page = QWidget()
        outer = vbox(page)
        outer.addWidget(self._build_header())
        body = hbox()
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_main(), 1)
        holder = QWidget()
        holder.setLayout(body)
        outer.addWidget(holder, 1)
        self.stack.addWidget(page)
        self.wizard = Wizard(self, self.logo)
        self.stack.addWidget(self.wizard)
        self.wizard.finished.connect(self.finish_wizard)
        self.wizard.output_box.activated.connect(lambda _i: self.restart_engine())
        self.wizard.monitor_box.activated.connect(lambda _i: self.restart_engine())
        self.wizard.mic_box.activated.connect(lambda _i: self.restart_engine())
        self.wizard.monitor_check.setChecked(bool(self.settings.monitor_enabled))
        self.wizard.mic_check.setChecked(bool(self.settings.mic_enabled))
        self.wizard.monitor_check.toggled.connect(lambda _on: self._sync_toggles())
        self.wizard.mic_check.toggled.connect(lambda _on: self._sync_toggles())

    def _build_header(self) -> QWidget:
        header = Box(border="b2")
        line = hbox(header, (16, 12, 16, 12), 16)
        line.addWidget(LogoTile(36, self.logo, inset=2))
        line.addWidget(Text("nicoPad", 20, 800, spacing=-0.3))
        line.addStretch(1)
        self.pill = Button("", "pill", icon="check", icon_size=14)
        self.pill.clicked.connect(self.guide_dialog)
        line.addWidget(self.pill)
        group = hbox(spacing=4)
        profiles = Button("Perfis", "text", trailing="chevron")
        profiles.clicked.connect(lambda: profiles.popup(self._profiles_menu()))
        options = Button("Configurações", "text", trailing="chevron")
        options.clicked.connect(lambda: options.popup(self._settings_menu()))
        self.theme_button = Button(kind="icon", icon="moon", size=36, icon_size=18)
        self.theme_button.setToolTip("Trocar o tema")
        self.theme_button.clicked.connect(self.toggle_theme)
        help_button = Button(kind="icon", icon="help", size=36, icon_size=18)
        help_button.setToolTip("Como configurar o cabo")
        help_button.clicked.connect(self.guide_dialog)
        for widget in (profiles, options, self.theme_button, help_button):
            group.addWidget(widget)
        line.addLayout(group)
        return header

    def _build_sidebar(self) -> QWidget:
        side = Box(border="r2")
        side.setFixedWidth(248)
        column = vbox(side)

        def section(text: str, top: int = 16) -> QWidget:
            holder = QWidget()
            hbox(holder, (16, top, 16, 8)).addWidget(Text(text, 11, 400, alpha=0.6, upper=True, spacing=0.88))
            return holder

        column.addWidget(section("MAPAS"))
        self.maps_area = QScrollArea()
        self.maps_area.setWidgetResizable(True)
        self.maps_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.maps_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.maps_body = QWidget()
        self.maps_column = vbox(self.maps_body)
        self.maps_area.setWidget(self.maps_body)
        column.addWidget(self.maps_area, 1)
        new_map = Button("Novo mapa", "ghost", icon="plus")
        new_map.clicked.connect(self.new_map)
        column.addWidget(new_map)
        spacer = Box("divider")
        spacer.setFixedHeight(2)
        column.addSpacing(12)
        column.addWidget(spacer)
        column.addWidget(section("ÁUDIO"))

        routes = vbox(margins=(16, 0, 16, 0), spacing=10)
        self.routes = {}
        for key, icon, label in (("out", "check", "Tocar no mic"), ("mic", "mic", "Sua voz"), ("mon", "headphones", "Seu fone")):
            row = hbox(spacing=8)
            glyph = Icon(icon, 14, alpha=0.8)
            title, value = Text(label, 12, 400, alpha=0.6), Text("", 13, 600)
            texts = vbox()
            texts.addWidget(title)
            texts.addWidget(value)
            row.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
            row.addLayout(texts, 1)
            routes.addLayout(row)
            self.routes[key] = (glyph, title, value)
        column.addLayout(routes)
        column.addSpacing(12)
        wrap = QWidget()
        configure = Button("Configurar áudio", "secondary", trailing="arrow")
        configure.clicked.connect(lambda: self.show_wizard(1))
        hbox(wrap, (16, 0, 16, 16)).addWidget(configure)
        column.addWidget(wrap)

        footer = Box(border="t2")
        inner = vbox(footer, (16, 14, 16, 14), 10)
        head = hbox()
        head.addWidget(Text("VOLUME GERAL", 11, 400, alpha=0.6, spacing=0.88))
        self.volume_label = Text(f"{round(self.settings.volume * 100)}%", 14, 800, align=Qt.AlignmentFlag.AlignRight)
        head.addWidget(self.volume_label, 1)
        inner.addLayout(head)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(round(self.settings.volume * 100))
        self.volume.valueChanged.connect(self._on_volume)
        inner.addWidget(self.volume)
        self.stop_button = Button("Parar tudo", "primary", icon="stop", icon_size=12, pad_v=10)
        self.stop_button.clicked.connect(self.stop_all)
        self.stop_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.stop_button.customContextMenuRequested.connect(self._stop_menu)
        inner.addWidget(self.stop_button)
        column.addWidget(footer)
        return side

    def _build_main(self) -> QWidget:
        area = QWidget()
        column = vbox(area)

        toolbar = Box(border="b2")
        line = hbox(toolbar, (16, 12, 16, 12), 8)
        search = Box("surface", "a1")
        search.setFixedHeight(36)
        search.setMaximumWidth(340)
        inside = hbox(search, (10, 0, 10, 0), 8)
        inside.addWidget(Icon("search", 16, alpha=0.6))
        self.search_field = SearchField()
        self.search_field.setProperty("bare", True)
        self.search_field.setPlaceholderText("Buscar sons, teclas ou arquivos")
        self.search_field.textChanged.connect(self._on_search)
        inside.addWidget(self.search_field, 1)
        line.addWidget(search, 100)  # cresce até 340px; o que sobrar fica no espaço depois

        segmented = Box(border="a1")
        seg = hbox(segmented)
        self.seg_pads = Button("Pads", "seg", icon="grid", icon_size=14)
        self.seg_list = Button("Lista", "seg", icon="list", icon_size=14)
        divider = Box("divider")
        divider.setFixedWidth(1)
        for widget in (self.seg_pads, divider, self.seg_list):
            seg.addWidget(widget)
        self.seg_pads.clicked.connect(lambda: self.set_view("pads"))
        self.seg_list.clicked.connect(lambda: self.set_view("lista"))
        line.addWidget(segmented)
        line.addStretch(1)
        self.active_button = Button("Tocando agora", "secondary", icon="volume", icon_size=14, trailing="count:0")
        self.active_button.setToolTip("Tocando agora")
        self.active_button.clicked.connect(self.toggle_playing_window)
        self.youtube_button = youtube = Button("YouTube", "secondary", icon="download")
        youtube.setToolTip("Baixar do YouTube")
        youtube.clicked.connect(self.youtube_dialog)
        add = Button("Adicionar som", "primary", icon="plus")
        add.clicked.connect(self.add_sounds)
        line.addWidget(self.active_button)
        line.addWidget(youtube)
        line.addWidget(add)
        column.addWidget(toolbar)

        self.views = QStackedWidget()
        self.list_view, self.pad_view = ListView(self), PadView(self)
        self.views.addWidget(self.list_view)
        self.views.addWidget(self.pad_view)
        column.addWidget(self.views, 1)

        status = Box(border="t2")
        status.setMinimumHeight(38)
        row = hbox(status, (16, 8, 16, 8), 16)
        left = hbox(spacing=8)
        self.status_icon = Icon("volume", 14, alpha=0.6)
        self.status_text = Text("", 13)
        left.addWidget(self.status_icon)
        left.addWidget(self.status_text, 1)
        row.addLayout(left, 1)
        self.warning_row = hbox(spacing=16)
        row.addLayout(self.warning_row)
        column.addWidget(status)
        return area

    # --------------------------------------------------------------- tema e vista

    def toggle_theme(self) -> None:
        self.apply_theme("claro" if theme.name() == "escuro" else "escuro")
        self.settings.theme = theme.name()
        self._save()

    def apply_theme(self, name: str) -> None:
        theme.apply(QApplication.instance(), name)
        self._sync_theme_button()
        for widget in self.findChildren(QWidget):
            widget.update()

    def _sync_theme_button(self) -> None:
        self.theme_button.icon_name = "sun" if theme.name() == "escuro" else "moon"
        self.theme_button.update()

    def set_view(self, mode: str) -> None:
        self.view_mode = mode
        self.settings.view = mode
        self._apply_view()
        self.save_later()

    def _apply_view(self) -> None:
        pads = self.view_mode == "pads"
        self.seg_pads.setChecked(pads)
        self.seg_list.setChecked(not pads)
        self.views.setCurrentWidget(self.pad_view if pads else self.list_view)
        self._fill()

    def _view(self):
        return self.pad_view if self.view_mode == "pads" else self.list_view

    # ---------------------------------------------------------------- aparelhos

    def cable_device(self):
        """O cabo virtual disponível (o escolhido, ou o primeiro encontrado)."""
        chosen = self._device_from(self.wizard.output_box, self.output_choices)
        return chosen if is_virtual_cable(chosen) else (self.cables[0] if self.cables else None)

    def reload_devices(self) -> None:
        wizard = self.wizard
        self.outputs = visible_devices(list_devices("output"))
        self.inputs = visible_devices(list_devices("input"))
        # Para os outros escutarem, a saída tem de ser um cabo virtual. Com um cabo instalado só
        # cabos aparecem na lista; sem nenhum, aparecem todos, senão você não conseguiria testar nada.
        self.cables = [device for device in self.outputs if is_virtual_cable(device)]
        self.output_choices = self.cables or self.outputs
        for box, devices in ((wizard.output_box, self.output_choices), (wizard.monitor_box, self.outputs), (wizard.mic_box, self.inputs)):
            keep = box.currentText()
            box.clear()
            box.addItems([device.label for device in devices])
            box.setCurrentIndex(box.findText(keep) if keep else -1)
        default_input, default_output = sd.default.device[0], sd.default.device[1]
        if wizard.output_box.currentIndex() < 0 and self.output_choices:
            preferred = guess_cable(self.output_choices) or _default(self.output_choices, default_output)
            wizard.output_box.setCurrentText((preferred or self.output_choices[0]).label)
        if wizard.monitor_box.currentIndex() < 0:
            fallback = _default(self.outputs, default_output)
            if fallback is not None:
                wizard.monitor_box.setCurrentText(fallback.label)
        if wizard.mic_box.currentIndex() < 0:
            fallback = _default(self.inputs, default_input)
            if fallback is not None:
                wizard.mic_box.setCurrentText(fallback.label)
        self.restart_engine()
        wizard.refresh()

    def _restore_devices(self) -> None:
        wizard = self.wizard
        for box, devices, saved in (
            (wizard.output_box, self.output_choices, self.settings.output),
            (wizard.monitor_box, self.outputs, self.settings.monitor),
            (wizard.mic_box, self.inputs, self.settings.microphone),
        ):
            saved = saved or {}
            device = find_device(devices, saved.get("name", ""), saved.get("hostapi", ""))
            if device is not None:
                box.setCurrentText(device.label)

    def _sync_toggles(self) -> None:
        self.wizard.monitor_box.setEnabled(self.wizard.monitor_check.isChecked())
        self.wizard.mic_box.setEnabled(self.wizard.mic_check.isChecked())
        self.restart_engine()

    @staticmethod
    def _device_from(box, devices):
        label = box.currentText().strip()
        return next((device for device in devices if device.label == label), None)

    def restart_engine(self) -> None:
        """Reabre os streams com o que está marcado na tela e salva a configuração."""
        if not self.ready:
            return
        wizard = self.wizard
        self.message = None
        output = self._device_from(wizard.output_box, self.output_choices)
        monitor_device = self._device_from(wizard.monitor_box, self.outputs)
        mic_device = self._device_from(wizard.mic_box, self.inputs)
        monitor = monitor_device if wizard.monitor_check.isChecked() else None
        microphone = mic_device if wizard.mic_check.isChecked() else None
        self.settings.output = _device_dict(output)
        self.settings.monitor = _device_dict(monitor_device)
        self.settings.monitor_enabled = wizard.monitor_check.isChecked()
        self.settings.microphone = _device_dict(mic_device)
        self.settings.mic_enabled = wizard.mic_check.isChecked()
        self.engine.start(output, monitor=monitor, microphone=microphone, volume=self.settings.volume, sounds=self.sounds.values())
        wizard.refresh()
        self.update_status()
        self.save_later()

    def _on_volume(self, value: int) -> None:
        volume = value / 100
        self.settings.volume = volume
        self.volume_label.set_text(f"{value}%")
        self.engine.set_volume(volume)
        self.save_later()

    def play_test_tone(self, seconds: float) -> None:
        """Som de teste do assistente: vai para o cabo (como um atalho), não só para o seu fone."""
        rate = 48000
        t = np.arange(int(rate * seconds)) / rate
        envelope = np.minimum(1.0, np.minimum(t, seconds - t) * 20)
        tone = (0.5 * np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 660 * t)) * envelope * 0.6
        data = np.repeat(tone[:, None], 2, axis=1).astype(np.float32)
        self.engine.trigger(Sound("teste", "", data, rate))

    # --------------------------------------------------------------------- mapas

    def sync_maps(self) -> None:
        while self.maps_column.count():
            widget = self.maps_column.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)  # some já: o deleteLater só roda quando o laço de eventos voltar
                widget.deleteLater()
        for index, keymap in enumerate(self.settings.maps):
            button = Button(keymap.name, "map", trailing=f"text:{len(keymap.bindings)}")
            button.setChecked(index == self.settings.active)
            button.clicked.connect(lambda _checked=False, i=index: self.switch_map(i))
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(lambda pos, i=index, b=button: self._map_menu(i, b.mapToGlobal(pos)))
            self.maps_column.addWidget(button)
        self.maps_column.addStretch(1)

    def _map_menu(self, index: int, where) -> None:
        menu = QMenu(self)
        menu.addAction("Renomear…", lambda: self.rename_map(index))
        menu.addAction("Excluir", lambda: self.delete_map(index))
        menu.exec(where)

    def switch_map(self, index: int) -> None:
        # PONYTAIL: só o mapa ativo fica na memória; trocar de mapa recarrega os arquivos do
        # disco. Carregar sob demanda no primeiro toque, se listas grandes virarem rotina.
        self.settings.active = index
        self.sync_maps()
        self.sounds = {}
        self._load_bindings()
        self._save()
        self.flash(f"Mapa «{self.settings.maps[index].name}» ativo.")

    def new_map(self) -> None:
        name = (dialogs.ask_text(self, "Novo mapa", "Nome do mapa:") or "").strip()
        if not name:
            return
        self.settings.maps.append(cfg.KeyMap(name=name))
        self.settings.active = len(self.settings.maps) - 1
        self.sync_maps()
        self.sounds = {}
        self._load_bindings()
        self._save()
        self.flash(f"Mapa «{name}» criado.")

    def rename_map(self, index: int) -> None:
        current = self.settings.maps[index]
        name = (dialogs.ask_text(self, "Renomear mapa", "Novo nome:", current.name) or "").strip()
        if not name or name == current.name:
            return
        current.name = name
        self.sync_maps()
        self._save()
        self.flash(f"Mapa renomeado para «{name}».")

    def delete_map(self, index: int) -> None:
        if len(self.settings.maps) <= 1:
            self.flash("Não é possível excluir o único mapa.")
            return
        current = self.settings.maps[index]
        if not dialogs.confirm(
            self,
            f"Excluir o mapa «{current.name}» e seus {len(current.bindings)} som(ns) da lista?\n\n"
            "Os arquivos de som não são apagados do disco.",
            "Excluir",
            "Cancelar",
            default_cancel=True,
        ):
            return
        self.settings.maps.pop(index)
        if index < self.settings.active:
            self.settings.active -= 1
        self.settings.active = max(0, min(self.settings.active, len(self.settings.maps) - 1))
        self.sync_maps()
        self.sounds = {}
        self._load_bindings()
        self._save()
        self.flash(f"Mapa «{current.name}» excluído.")

    # ---------------------------------------------------------------------- sons

    @staticmethod
    def sound_key(path) -> str:
        """Caminho normalizado, igual ao que é gravado na configuração."""
        return str(Path(path))

    def _load_bindings(self) -> None:
        self.pending = None  # troca de mapa cancela uma tecla pendente: o índice era do mapa anterior
        self.selected = None
        for binding in self.settings.bindings:
            if binding.vk and binding.key.startswith("VK "):
                # Nome gravado por uma versão antiga, quando o Windows não sabia a tecla.
                binding.key = key_name(binding.vk, 0, binding.extended)
            try:
                self.sounds[self.sound_key(binding.path)] = load_sound(
                    binding.path,
                    name=binding.name,
                    gain=binding.gain,
                    monitor=binding.monitor,
                    monitor_gain=binding.monitor_gain,
                    start=binding.start,
                    end=binding.end,
                )
            except Exception:
                pass  # a linha já aparece marcada como «arquivo não encontrado»
        self._rebuild_keymap()
        self.refresh_rows()
        self.engine.prepare(self.sounds.values())

    def _rebuild_keymap(self) -> None:
        self.keymap = {(b.vk, b.extended): b for b in self.settings.bindings if b.vk}

    def _matches(self, binding) -> bool:
        """A busca aceita várias palavras: todas precisam aparecer no som."""
        query = self.query.strip().casefold()
        if not query:
            return True
        text = f"{binding.name} {binding.key} {binding.path}".casefold()
        return all(word in text for word in query.split())

    def visible_indices(self) -> list:
        return [index for index, binding in enumerate(self.settings.bindings) if self._matches(binding)]

    def row_state(self, index: int) -> RowState:
        binding = self.settings.bindings[index]
        key = self.sound_key(binding.path)
        sound = self.sounds.get(key)
        progress = self.progress.get(key)
        listening = self.pending == index
        return RowState(
            name=binding.name,
            key_label="Aperte…" if listening else (binding.key or "—"),
            has_key=bool(binding.key),
            missing=sound is None,
            duration=seconds_text(len(sound.data) / sound.samplerate) if sound is not None else "—",
            monitor=f"{round(binding.monitor_gain * 100)}%" if binding.monitor else "—",
            monitor_on=bool(binding.monitor),
            path=binding.path,
            progress=progress,
            listening=listening,
            selected=self.selected == index,
        )

    def refresh_rows(self, select=None) -> None:
        """Refaz a lista/pads (a que está à vista) e os contadores dos mapas."""
        if select is not None:
            self.selected = select if 0 <= select < len(self.settings.bindings) else None
        elif self.selected is not None and self.selected >= len(self.settings.bindings):
            self.selected = None
        self._fill()
        self.sync_maps()
        self.update_status()

    def _fill(self) -> None:
        self._view().refresh(self.visible_indices())
        if self.selected is not None:
            self._view().reveal(self.selected)

    def sync_rows(self, indices=None) -> None:
        self._view().sync(indices)

    def select(self, index) -> None:
        self.selected = index
        self.sync_rows()
        self.update_status()

    def move_selection(self, step: int) -> None:
        shown = self.visible_indices()
        if not shown:
            return
        position = shown.index(self.selected) if self.selected in shown else (-1 if step > 0 else len(shown))
        self.select(shown[max(0, min(len(shown) - 1, position + step))])
        self._view().reveal(self.selected)

    def _on_search(self, text: str) -> None:
        self.query = text
        self.refresh_rows(select=self.selected)

    def _sounds_folder(self) -> str:
        """Reabre o diálogo onde você estava, e não em Documentos."""
        for folder in (self.last_folder, *(str(Path(b.path).parent) for b in self.settings.bindings)):
            if folder and Path(folder).is_dir():
                return folder
        return ""

    def add_sounds(self) -> None:
        paths, _filter = QFileDialog.getOpenFileNames(self, "Escolha os sons", self._sounds_folder(), AUDIO_FILTER)
        if paths:
            self.last_folder = str(Path(paths[0]).parent)
        added = sum(1 for path in paths if self._add_sound(path))
        if not added:
            return
        self.engine.prepare(self.sounds.values())
        self.refresh_rows(select=len(self.settings.bindings) - 1)
        self._save()
        self.flash(f"{added} som(ns) adicionado(s) — agora clique em «Definir tecla».")

    def _add_sound(self, path) -> bool:
        path = self.sound_key(path)
        if self._duplicate(path):
            return False
        try:
            sound = load_sound(path)
        except Exception as exc:
            dialogs.notify(self, f"Não consegui abrir «{Path(path).name}».\n\n{exc}")
            return False
        if self.settings.library_enabled:
            try:
                path = self.sound_key(library.copy_in(path, self.library_folder()))
            except OSError as exc:
                dialogs.notify(self, f"Não consegui guardar a cópia de «{Path(path).name}».\n\n{exc}")
                return False
            if self._duplicate(path):
                return False
            sound.path = path
        self.sounds[path] = sound
        self.settings.bindings.append(cfg.Binding(path=path, name=sound.name))
        return True

    def _duplicate(self, path) -> bool:
        return path in self.sounds or any(self.sound_key(binding.path) == path for binding in self.settings.bindings)

    def add_downloaded(self, path: str) -> None:
        if self._add_sound(path):
            self.engine.prepare(self.sounds.values())
            self.refresh_rows(select=len(self.settings.bindings) - 1)
            self._save()
            self.flash(f"«{Path(path).stem}» baixado e adicionado — agora clique em «Definir tecla».")

    def remove_selected(self) -> None:
        if self.selected is None:
            self.flash("Escolha um som na lista para remover.")
            return
        self.remove(self.selected)

    def remove(self, index: int) -> None:
        binding = self.settings.bindings[index]
        elsewhere = any(
            self.sound_key(b.path) == self.sound_key(binding.path)
            for keymap in self.settings.maps
            for b in keymap.bindings
            if b is not binding
        )
        own_copy = library.inside(binding.path, self.library_folder()) and not elsewhere
        if own_copy and not dialogs.confirm(
            self,
            f"Remover «{binding.name}» e apagar o arquivo da pasta dos sons?\n\n{binding.path}",
            "Remover",
            "Cancelar",
            default_cancel=True,
        ):
            return
        self.settings.bindings.pop(index)
        self.sounds.pop(self.sound_key(binding.path), None)
        self.engine.stop_sound(self.sound_key(binding.path))
        self._rebuild_keymap()
        if isinstance(self.pending, int):
            self.pending = None  # os índices mudaram: a tecla pendente era de outra linha
        self.refresh_rows(select=min(index, len(self.settings.bindings) - 1))
        self._save()
        if own_copy:
            try:
                Path(binding.path).unlink()
            except OSError as exc:
                self.flash(f"«{binding.name}» saiu da lista, mas não consegui apagar o arquivo: {exc}")
                return
        self.flash(f"«{binding.name}» saiu da lista.")

    # ---------------------------------------------------------------- tocar

    def play_sound(self, index: int) -> None:
        """Toca como o atalho tocaria (no mic e, se ligado, no fone): assim aparece em «Tocando agora»."""
        binding = self.settings.bindings[index]
        sound = self.sounds.get(self.sound_key(binding.path))
        if sound is None:
            self.flash(f"Arquivo não encontrado: {binding.path}")
            return
        self.engine.trigger(sound)
        self.kick()

    def preview_sound(self, index: int) -> None:
        """Só para você ouvir (prévia local), sem passar pelo cabo."""
        binding = self.settings.bindings[index]
        sound = self.sounds.get(self.sound_key(binding.path))
        if sound is None:
            self.flash(f"Arquivo não encontrado: {binding.path}")
            return
        self.engine.preview(sound)

    def preview_clip(self, binding, start: float, end: float) -> None:
        try:
            clip = load_sound(
                binding.path, start=start, end=end, gain=binding.gain, monitor=binding.monitor, monitor_gain=binding.monitor_gain
            )
        except Exception as exc:
            self.flash(f"Não consegui ouvir o trecho: {exc}")
            return
        self.engine.preview(clip)

    def toggle_play(self, index: int) -> None:
        """Clicar de novo enquanto toca para só aquele som."""
        key = self.sound_key(self.settings.bindings[index].path)
        if key in self.progress:
            self.engine.stop_sound(key)
            self.refresh_voices()
        else:
            self.play_sound(index)

    def preview_selected(self) -> None:
        if self.selected is None:
            self.flash("Escolha um som na lista para ouvir.")
            return
        self.toggle_play(self.selected)

    def stop_all(self) -> None:
        self.engine.stop_all()
        self.refresh_voices()
        self.flash("Sons interrompidos.")

    def kick(self) -> None:
        """Algo começou a tocar: liga o relógio de ~30 fps (ele se desliga quando tudo acaba)."""
        if not self._tick_timer.isActive():
            self._tick_timer.start()
        self.refresh_voices()

    def _tick(self) -> None:
        self.refresh_voices()

    def refresh_voices(self) -> None:
        """Lê as vozes do motor e atualiza pads, linhas, selo do botão, status e a janela Tocando agora."""
        voices = [voice for voice in self.engine.active() if voice[5]]  # sem caminho = som de teste do assistente
        old, progress = self.progress, {}
        for voice in voices:
            progress[voice[5]] = max(progress.get(voice[5], 0.0), voice[2])
        self.voices, self.progress = voices, progress
        if not voices:
            self._tick_timer.stop()
        changed = {path for path in old.keys() | progress.keys() if old.get(path) != progress.get(path)}
        if changed:
            self.sync_rows({i for i, b in enumerate(self.settings.bindings) if self.sound_key(b.path) in changed})
        if old.keys() != progress.keys():
            self.update_status()
        self.active_button.trailing = f"count:{len(voices)}"
        self.active_button.badge_on = bool(voices)
        self.active_button.updateGeometry()
        self.active_button.update()
        if self.playing_window is not None and self.playing_window.isVisible():
            self.playing_window.update_voices(voices)

    def toggle_playing_window(self) -> None:
        """Abre/fecha a janela solta Tocando agora (não modal: atalhos e janela principal seguem valendo)."""
        if self.playing_window is None:
            self.playing_window = PlayingWindow(self)
            self.playing_window.visibility.connect(self._on_playing_visibility)
            self.playing_window.set_stop_key(self.settings.stop_key)
        if self.playing_window.isVisible():
            self.playing_window.hide()
            return
        self.playing_window.show()
        self.playing_window.raise_()
        self.playing_window.activateWindow()
        self.refresh_voices()

    def _on_playing_visibility(self, visible: bool) -> None:
        self.active_button.open = visible
        self.active_button.update()

    # ----------------------------------------------------------------- teclas

    def start_binding(self, index: int) -> None:
        self.pending = index
        self.selected = index
        self.sync_rows()
        self.update_status()

    def start_stop_binding(self) -> None:
        self.pending = "stop"
        self.sync_rows()
        self.update_status()

    def _stop_menu(self, position) -> None:
        menu = QMenu(self)
        menu.addAction("Definir tecla…", self.start_stop_binding)
        menu.exec(self.stop_button.mapToGlobal(position))

    def apply_binding(self, event) -> None:
        index, self.pending = self.pending, None
        vk, extended, name = event
        if vk == ESC:
            self.sync_rows()
            self.flash("Nenhuma tecla foi definida.")
            return
        if index == "stop":
            self._apply_stop_binding(vk, extended, name)
            return
        if index is None or index >= len(self.settings.bindings):
            return
        binding = self.settings.bindings[index]
        replaced = None
        for other in self.settings.bindings:
            if other is not binding and other.vk == vk and other.extended == extended:
                other.vk, other.extended, other.key = 0, False, ""
                replaced = other.name
        if self.settings.stop_vk == vk and self.settings.stop_extended == extended:
            self.settings.stop_vk, self.settings.stop_extended, self.settings.stop_key = 0, False, ""
            replaced = "Parar tudo"
            self._sync_stop_key()
        binding.vk, binding.extended, binding.key = vk, extended, name
        self._rebuild_keymap()
        self.refresh_rows(select=index)
        self._save()
        self.flash(f"«{binding.name}» agora toca com {name}." + (f"  (a tecla saiu de «{replaced}»)" if replaced else ""))

    def _apply_stop_binding(self, vk: int, extended: bool, name: str) -> None:
        replaced = None
        for other in self.settings.bindings:
            if other.vk == vk and other.extended == extended:
                other.vk, other.extended, other.key = 0, False, ""
                replaced = other.name
        self.settings.stop_vk, self.settings.stop_extended, self.settings.stop_key = vk, extended, name
        self._sync_stop_key()
        self._rebuild_keymap()
        self.refresh_rows(select=self.selected)
        self._save()
        self.flash(f"«Parar tudo» agora atalha com {name}." + (f"  (a tecla saiu de «{replaced}»)" if replaced else ""))

    def _sync_stop_key(self) -> None:
        self.stop_button.trailing = f"chip:{self.settings.stop_key}" if self.settings.stop_key else None
        self.stop_button.updateGeometry()
        self.stop_button.update()
        if self.playing_window is not None:
            self.playing_window.set_stop_key(self.settings.stop_key)

    def _on_hotkey(self, vk: int, extended: bool, name: str) -> None:
        """Roda na thread do hook: só o essencial; o resto vai para a thread da interface."""
        if self.typing:
            return  # o usuário está digitando: a tecla é dele
        if self.pending is not None:
            self.bus.call.emit(lambda: self.apply_binding((vk, extended, name)))
            return
        if self.settings.stop_vk and (vk, extended) == (self.settings.stop_vk, self.settings.stop_extended):
            self.engine.stop_all()
            self.bus.call.emit(self._stopped)
            return
        binding = self.keymap.get((vk, extended))
        if binding is None:
            return
        sound = self.sounds.get(self.sound_key(binding.path))
        if sound is not None:
            self.engine.trigger(sound)
            self.bus.call.emit(self.kick)

    def _stopped(self) -> None:
        self.refresh_voices()
        self.flash("Sons interrompidos.")

    # ------------------------------------------------------------------ status

    def flash(self, text: str, seconds: float = 6.0) -> None:
        """Recado passageiro na barra de status: some sozinho."""
        self.message = text
        self.update_status()
        self._flash_timer.start(int(seconds * 1000))

    def _clear_message(self) -> None:
        self.message = None
        self.update_status()

    def update_status(self) -> None:
        names = list(dict.fromkeys(voice[1] for voice in self.voices))
        text, icon, tone, weight, alpha = None, "volume", "text", 400, 0.6
        output = self._device_from(self.wizard.output_box, self.output_choices)
        has_cable = is_virtual_cable(output)
        if self.pending == "stop":
            text, icon, tone, weight, alpha = "Aperte a tecla para Parar tudo  (Esc cancela)", "keyboard", "accent_700", 800, 1.0
        elif isinstance(self.pending, int) and self.pending < len(self.settings.bindings):
            name = self.settings.bindings[self.pending].name
            text, icon, tone, weight, alpha = f"Aperte a tecla que vai tocar «{name}»  (Esc cancela)", "keyboard", "accent_700", 800, 1.0
        elif self.message:
            text, tone, weight, alpha = self.message, "text", 600, 1.0
        elif names:
            text, icon, tone, weight, alpha = "Tocando: " + ", ".join(names), "play", "text", 600, 1.0
        else:
            rate = f" · {output.samplerate:.0f} Hz" if output is not None else ""
            text = (
                f"Pronto{rate} · aperte a tecla de um som, mesmo com a janela minimizada"
                if has_cable
                else "Os sons saem só no seu alto-falante"
            )
        self.status_icon.set_icon(icon, tone, alpha)
        self.status_text.set_text(text, tone, weight, alpha)

        while self.warning_row.count():
            widget = self.warning_row.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for short, full in self._warnings():
            holder = QWidget()
            holder.setToolTip(full)
            line = hbox(holder, spacing=6)
            line.addWidget(Icon("alert", 14, tone="accent_700"))
            line.addWidget(Text(short, 13, 600, tone="accent_700"))
            self.warning_row.addWidget(holder)
        self._update_pill_and_routes(output, has_cable)

    def _warnings(self) -> list:
        """Avisos que ficam na tela: só somem quando a causa some. Cada um vem curto e completo."""
        found = [
            (text, text)
            for text in (self.load_warning, self.hook.error, self.save_error, self.engine.error, self.tray.error)
            if text
        ]
        missing = sum(1 for binding in self.settings.bindings if self.sound_key(binding.path) not in self.sounds)
        if missing:
            short = "1 arquivo não encontrado" if missing == 1 else f"{missing} arquivos não encontrados"
            found.append((short, f"{missing} arquivo(s) de som não encontrado(s)."))
        found.extend((text, text) for text in self.engine.warnings)
        output = self._device_from(self.wizard.output_box, self.output_choices)
        mic_on = self.wizard.mic_check.isChecked()
        if not self.outputs:
            found.append(("Nenhuma saída de áudio", "Nenhum dispositivo de saída encontrado."))
        elif output is None:
            found.append(("Escolha a saída de áudio", "Escolha a saída de áudio em «Configurar áudio»."))
        elif not is_virtual_cable(output):
            if self.cables:
                found.append((
                    "Saída no alto-falante: os outros não escutam",
                    "A saída escolhida é seu alto-falante/fone: o som não chega no microfone dos outros. "
                    "Escolha o cabo em «Configurar áudio» ou use o botão «?» no cabeçalho.",
                ))
            else:
                found.append((
                    "Sem cabo virtual: os outros não escutam",
                    "Nenhum cabo de áudio virtual encontrado: sem ele os outros jogadores não escutam os sons. "
                    "Use o botão «?» no cabeçalho.",
                ))
        elif not mic_on:
            found.append((
                "Sua voz não sai junto",
                "Saída no cabo virtual sem o microfone misturado: sua voz não sai junto. "
                "Marque «Misturar meu microfone» em «Configurar áudio».",
            ))
        if mic_on and output is not None and output.index == sd.default.device[1]:
            found.append(("Microfonia: mic na saída padrão", "Misturar o microfone direto na saída padrão causa microfonia."))
        return found

    def _update_pill_and_routes(self, output, has_cable: bool) -> None:
        mic_on = self.wizard.mic_check.isChecked()
        good = has_cable and mic_on
        self.pill.problem = not good
        self.pill.icon_name = "check" if good else "alert"
        self.pill.setText("Microfone pronto" if good else "Sua voz não sai junto" if has_cable else "Os outros não escutam")
        self.pill.updateGeometry()
        self.pill.update()

        glyph, title, value = self.routes["out"]
        if has_cable:
            glyph.set_icon("check", "text")
            title.set_text(title.text(), "text")
            value.set_text(_shorten(output.name, 40))
        else:
            name = output.name if output is not None else "Sem saída"
            glyph.set_icon("alert", "accent_700")
            title.set_text(title.text(), "accent_700")
            value.set_text(f"{name} — sem cabo virtual")
        mic = self._device_from(self.wizard.mic_box, self.inputs)
        self.routes["mic"][2].set_text(f"{mic.name} misturado" if mic_on and mic else "Não misturada")
        monitor = self._device_from(self.wizard.monitor_box, self.outputs)
        self.routes["mon"][2].set_text(monitor.name if self.wizard.monitor_check.isChecked() and monitor else "Desligado")

    # ---------------------------------------------------------------- diálogos

    def sound_dialog(self, index=None) -> None:
        """Ajustes do som individual: nome, volume no mic e no fone, tecla."""
        index = self.selected if index is None else index
        if index is None:
            self.flash("Escolha um som na lista para configurar.")
            return
        binding = self.settings.bindings[index]
        if self.sound_key(binding.path) not in self.sounds:
            self.flash(f"Arquivo não encontrado: {binding.path}")
            return
        self.selected = index
        dialog = dialogs.SoundDialog(self, index)
        dialog.exec()
        self.refresh_rows(select=index)
        if dialog.done_action == "key":
            self.start_binding(index)
        elif dialog.done_action == "trim":
            self.trim_dialog(index)

    def rename_sound(self, binding, name: str) -> None:
        """Novo nome do som; o arquivo da pasta própria é renomeado junto."""
        name = name.strip()
        if not name or name == binding.name:
            return
        path = Path(binding.path)
        sound = self.sounds.pop(self.sound_key(path), None)
        if library.inside(path, self.library_folder()):
            target = library.rename_in(path, name)
            if target is None:
                self.sounds[self.sound_key(path)] = sound  # nada mudou: o som continua onde estava
                self.flash("Não consegui renomear o arquivo; o nome não mudou.")
                return
            binding.path = self.sound_key(target)
        binding.name = name
        if sound is not None:
            sound.path = binding.path
            sound.name = name
            self.sounds[binding.path] = sound
        self._save()
        self.flash(f"Som renomeado para «{name}».")

    def trim_dialog(self, index=None) -> None:
        """Corte não destrutivo: início/fim em segundos, aplicados na carga do som."""
        index = self.selected if index is None else index
        if index is None:
            self.flash("Escolha um som na lista para cortar.")
            return
        binding = self.settings.bindings[index]
        if not Path(binding.path).is_file():
            self.flash(f"Arquivo não encontrado: {binding.path}")
            return
        try:
            full = load_sound(binding.path)
        except Exception as exc:
            self.flash(f"Não consegui abrir «{binding.name}»: {exc}")
            return
        dialog = dialogs.TrimDialog(self, binding, full)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        start, end, duration = dialog.edges
        binding.start = start
        binding.end = 0.0 if end >= duration - 1e-6 else end
        try:
            self.sounds[self.sound_key(binding.path)] = load_sound(
                binding.path,
                name=binding.name,
                gain=binding.gain,
                monitor=binding.monitor,
                monitor_gain=binding.monitor_gain,
                start=binding.start,
                end=binding.end,
            )
        except Exception as exc:
            self.flash(f"Não consegui salvar o corte: {exc}")
            return
        self.engine.prepare(self.sounds.values())
        self.refresh_rows(select=index)
        self._save()
        self.flash(f"«{binding.name}» cortado: {seconds_text(start)} → {seconds_text(end)}.")

    def youtube_dialog(self) -> None:
        """Baixa um áudio do YouTube direto para a pasta dos sons."""
        dialog = dialogs.YoutubeDialog(self, self.library_folder())
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.path:
            self.add_downloaded(dialog.path)

    def guide_dialog(self) -> None:
        dialog = dialogs.GuideDialog(self)
        dialog.exec()
        if dialog.open_wizard:
            self.show_wizard(1)

    def prepare_cable(self) -> None:
        """Entrega o pacote oficial do cabo e abre a pasta (é o que a licença permite)."""
        try:
            setup, folder = cable.prepare()
        except Exception as exc:
            dialogs.notify(self, f"Não consegui preparar o instalador do cabo.\n\n{exc}")
            return
        try:
            cable.reveal(setup)
        except OSError:
            pass  # se a pasta não abrir, o caminho continua visível na barra de status
        self.flash(f"Execute {setup.name} como administrador e reinicie o PC.   ({folder})", seconds=20)

    # ---------------------------------------------------------------- assistente

    def show_wizard(self, step: int = 1) -> None:
        self.wizard.go(step)
        self.wizard.refresh()
        self.stack.setCurrentIndex(1)

    def finish_wizard(self) -> None:
        self.settings.setup_done = True
        self._save()
        self.stack.setCurrentIndex(0)
        self.update_status()

    # -------------------------------------------------------------------- menus

    def _tick_label(self, on: bool, text: str) -> str:
        return ("✓  " if on else "     ") + text

    def _profiles_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction("Exportar perfil…", self.export_profile)
        menu.addAction("Importar perfil…", self.import_profile)
        return menu

    def _settings_menu(self) -> QMenu:
        menu = QMenu(self)
        label = "Guardar cópia dos sons"
        if self.settings.library_enabled:
            label = f"{label} em {_shorten(self.library_folder(), 44)}"
        menu.addAction(self._tick_label(self.settings.library_enabled, label), self._toggle_library)
        menu.addAction("Escolher a pasta dos sons…", self._choose_library)
        menu.addAction("Abrir a pasta dos sons", self._open_library)
        menu.addSeparator()
        closing = menu.addMenu("Ao fechar a janela")
        for text, value in (("Perguntar sempre", ""), ("Deixar na bandeja", "hide"), ("Encerrar o programa", "quit")):
            closing.addAction(self._tick_label(self.settings.close_action == value, text), lambda v=value: self._set_close_action(v))
        menu.addSeparator()
        menu.addAction("Preparar instalador do cabo de áudio", self.prepare_cable)
        menu.addAction("Abrir site do VB-Cable", lambda: webbrowser.open(CABLE_URL))
        menu.addSeparator()
        menu.addAction("Verificar atualizações…", lambda: self._check_updates(manual=True))
        return menu

    # ------------------------------------------------------------ pasta dos sons

    def library_folder(self) -> str:
        return self.settings.library or str(library.default_folder())

    def _set_close_action(self, value: str) -> None:
        self.settings.close_action = value
        self._save()

    def _toggle_library(self) -> None:
        self.settings.library_enabled = not self.settings.library_enabled
        self._save()
        if self.settings.library_enabled:
            self._copy_into_library()
        else:
            self.flash("Sons novos não serão mais copiados; as cópias já feitas ficam onde estão.")

    def _choose_library(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pasta para guardar os sons", self.library_folder())
        if not folder:
            return
        self.settings.library = self.sound_key(folder)
        self.settings.library_enabled = True
        self._save()
        self._copy_into_library()

    def _open_library(self) -> None:
        folder = Path(self.library_folder())
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            dialogs.notify(self, f"Não consegui criar a pasta dos sons.\n\n{exc}")
            return
        library.reveal(folder)

    def _copy_into_library(self) -> None:
        """Leva para a pasta própria os sons que ainda apontam para o arquivo original."""
        folder = self.library_folder()
        pending = [b for b in self.settings.bindings if not library.inside(b.path, folder)]
        if not pending:
            self.flash(f"Todos os sons já estão em {_shorten(folder)}.")
            return
        if not dialogs.confirm(
            self,
            f"Copiar {len(pending)} som(ns) para\n{folder}?\n\n"
            "A lista passa a usar as cópias: mover ou apagar o arquivo original não quebra mais o som.",
            "Copiar",
            "Agora não",
        ):
            return
        copied = 0
        for binding in pending:
            try:
                target = self.sound_key(library.copy_in(binding.path, folder))
            except OSError:
                continue  # arquivo ausente ou pasta sem permissão: este fica como está
            sound = self.sounds.pop(self.sound_key(binding.path), None)
            binding.path = target
            if sound is not None:
                sound.path = target
                self.sounds[target] = sound
            copied += 1
        self.refresh_rows(select=self.selected)
        self._save()
        text = f"{copied} som(ns) copiado(s) para {_shorten(folder)}."
        if copied < len(pending):
            text += f"   ({len(pending) - copied} não copiado(s))"
        self.flash(text)

    # -------------------------------------------------------------------- perfis

    def export_profile(self) -> None:
        if not any(m.bindings for m in self.settings.maps):
            self.flash("Não há sons para exportar.")
            return
        path, _filter = QFileDialog.getSaveFileName(self, "Salvar perfil", "nicopad-perfil.zip", "Perfil do nicoPad (*.zip)")
        if not path:
            return
        try:
            count, missing = profile.export(self.settings, path)
        except Exception as exc:
            dialogs.notify(self, f"Não consegui salvar o perfil.\n\n{exc}")
            return
        text = f"Perfil salvo com {count} som(ns): {Path(path).name}"
        if missing:
            text += f"   ({len(missing)} arquivo(s) não encontrado(s) ficaram de fora)"
        self.flash(text, seconds=20)

    def import_profile(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Escolher perfil", "", "Perfil do nicoPad (*.zip)")
        if not path:
            return
        folder = QFileDialog.getExistingDirectory(self, "Onde guardar os sons do perfil", str(Path(path).parent))
        if not folder:
            return
        try:
            settings, count, missing = profile.load(path, folder)
        except Exception as exc:
            dialogs.notify(self, f"Não consegui ler o perfil.\n\n{exc}")
            return
        if not count:
            dialogs.notify(self, "O perfil não trouxe nenhum som.")
            return
        total = sum(len(m.bindings) for m in self.settings.maps)
        if not dialogs.confirm(
            self,
            f"Isto substitui os {total} som(ns), as teclas e as configurações (todos os mapas) "
            f"atuais pelos {count} som(ns) do perfil «{Path(path).name}».\n\nContinuar?",
            "Continuar",
            "Cancelar",
            default_cancel=True,
        ):
            return
        self._apply_settings(settings)
        text = f"Perfil «{Path(path).name}» carregado: {count} som(ns)."
        if missing:
            text += f"   ({len(missing)} não vieram no perfil)"
        self.flash(text, seconds=20)

    def _apply_settings(self, settings) -> None:
        """Troca a configuração inteira (importar perfil) e reabre o que depende dela."""
        for field in ("geometry", "close_action", "theme", "view", "setup_done"):
            setattr(settings, field, getattr(self.settings, field))  # preferências da máquina, não do perfil
        self.settings = settings
        self.sounds = {}
        self.wizard.monitor_check.setChecked(bool(settings.monitor_enabled))
        self.wizard.mic_check.setChecked(bool(settings.mic_enabled))
        self.volume.setValue(round(settings.volume * 100))
        self.sync_maps()
        self._load_bindings()
        self._restore_devices()
        self._sync_toggles()
        self._sync_stop_key()

    # ---------------------------------------------------------------- atualização

    def _check_updates(self, manual: bool = False) -> None:
        """Confere a última release no GitHub em segundo plano (não trava a janela)."""

        def work() -> None:
            try:
                result = ("ok", updater.check())
            except Exception as exc:
                result = ("error", str(exc))
            self.bus.call.emit(lambda: self._on_update_checked(manual, *result))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_checked(self, manual: bool, kind: str, payload) -> None:
        if kind == "error":
            if manual:
                dialogs.notify(self, f"Não consegui verificar atualizações.\n\n{payload}")
        elif payload is None:
            if manual:
                dialogs.notify(self, f"Você já está na versão mais recente ({__version__}).")
        else:
            self._offer_update(*payload)

    def _offer_update(self, version: str, url: str) -> None:
        if not getattr(sys, "frozen", False):
            dialogs.notify(
                self,
                f"Versão {version} disponível (você está na {__version__}).\n\n"
                f"Rodando do código-fonte não dá para atualizar sozinho: baixe em {updater.RELEASES_URL}.",
            )
            return
        if dialogs.confirm(
            self,
            f"Versão {version} disponível (você está na {__version__}).\n\n"
            "Baixar e atualizar agora? O nicoPad fecha e reabre sozinho.",
            "Atualizar",
            "Agora não",
        ):
            self._run_update(url)

    def _run_update(self, url: str) -> None:
        """Baixa o novo .exe com uma janelinha de progresso e reinicia o app nele."""
        window = dialogs.ProgressDialog(self, "Baixando atualização…")

        def work() -> None:
            try:
                result = ("ok", updater.download(url))
            except Exception as exc:
                result = ("error", str(exc))
            self.bus.call.emit(lambda: done(*result))

        def done(kind: str, payload) -> None:
            window.done(0)
            if kind == "error":
                dialogs.notify(self, f"Não consegui baixar a atualização.\n\n{payload}")
                return
            self._save()
            updater.apply_and_restart(payload)

        threading.Thread(target=work, daemon=True).start()
        window.exec()

    # ------------------------------------------------------------------- bandeja

    def closeEvent(self, event) -> None:
        if self.closing:
            event.accept()
            return
        event.ignore()
        self._on_close()

    def _on_close(self) -> None:
        """O X da janela: pergunta se é para encerrar o programa ou só ir para a bandeja."""
        if not self.tray.ok:
            self._quit()  # sem bandeja o programa não teria como voltar
        elif self.settings.close_action == "hide":
            self._hide()
        elif self.settings.close_action == "quit":
            self._quit()
        else:
            action, remember = dialogs.ask_close_action(self)
            if action is None:
                return
            if remember:
                self.settings.close_action = action
                self.save_later()
            self._hide() if action == "hide" else self._quit()

    def _hide(self) -> None:
        """Tira a janela da frente sem encerrar nada: o programa segue pelos atalhos."""
        self.hide()
        self.tray.notify("O nicoPad continua na bandeja.")

    def _show(self) -> None:
        """Traz a janela de volta (pedido da bandeja)."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self) -> None:
        self.closing = True
        self.tray.stop()
        self._save_timer.stop()
        self._flash_timer.stop()
        self._tick_timer.stop()
        self.settings.geometry = f"{self.width()}x{self.height()}"
        self._save()
        self.hook.stop()
        self.engine.stop()
        QApplication.instance().quit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # janela estreita: os botões secundários viram só ícone, para a busca não encolher demais
        narrow = self.width() < 1100
        for button, text in ((self.youtube_button, "YouTube"), (self.active_button, "Tocando agora")):
            button.setText("" if narrow else text)
            button.updateGeometry()

    # ------------------------------------------------------------------ salvar

    def _save(self) -> None:
        self._save_timer.stop()
        self.save_error = cfg.save(self.settings)
        if self.save_error:
            self.update_status()

    def save_later(self) -> None:
        self._save_timer.start()


def run(settings, warning: str | None = None, first_run: bool = False) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("nicoPad")
    app.setQuitOnLastWindowClosed(False)  # fechar vai para a bandeja; quem encerra é o `_quit`
    if not theme.load_fonts(_asset("fonts/Archivo.ttf")):
        warning = warning or "fonte Archivo não encontrada: o visual pode sair diferente do desenho"
    theme.apply(app, settings.theme or theme.system_theme())
    window = NicoPadApp(settings, warning, first_run)
    window.show()
    return app.exec()
