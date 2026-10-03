"""Diálogos do nicoPad: estrutura comum (cabeçalho, corpo, ações) e cada janela do design."""

from __future__ import annotations

import threading
import time
import webbrowser

import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QGridLayout,
    QGraphicsOpacityEffect,
    QLineEdit,
    QProgressBar,
    QSlider,
    QWidget,
)

from nicopad import theme, youtube
from nicopad.audio import peaks
from nicopad.ui.lists import seconds_text
from nicopad.ui.widgets import Box, Button, Check, Chip, Icon, Text, cells, hbox, vbox

CABLE_URL = "https://vb-audio.com/Cable/"
FFMPEG_URL = "https://ffmpeg.org/download.html"


class Dialog(QDialog):
    """Cabeçalho (título 20px/800) · corpo · ações, separados por réguas de 2px. Esc fecha."""

    def __init__(self, parent, title: str, width: int = 520, resizable: bool = False, body_margins=(16, 16, 16, 16)):
        super().__init__(parent)
        self.setWindowTitle("nicoPad")
        self.setModal(True)
        if resizable:
            self.setMinimumWidth(width)
        else:
            self.setFixedWidth(width)
        outer = vbox(self)
        header = Box("surface", "b2")
        hbox(header, (16, 14, 16, 14)).addWidget(Text(title, 20, 800))
        outer.addWidget(header)
        self.body = vbox(margins=body_margins, spacing=16)
        holder = QWidget()
        holder.setLayout(self.body)
        outer.addWidget(holder, 1)
        footer = Box("surface", "t2")
        self.actions = hbox(footer, (16, 12, 16, 12), 8)
        outer.addWidget(footer)

    def add_actions(self, *items) -> None:
        for item in items:
            if item is None:
                self.actions.addStretch(1)
            else:
                self.actions.addWidget(item)


def _field(text: str = "", placeholder: str = "") -> QLineEdit:
    field = QLineEdit(text)
    field.setPlaceholderText(placeholder)
    field.setProperty("inDialog", True)
    return field


def confirm(parent, text: str, ok: str = "Sim", cancel: str = "Não", default_cancel: bool = False) -> bool:
    dialog = Dialog(parent, "nicoPad", 460)
    dialog.body.addWidget(Text(text, 14, 400, wrap=True))
    accept, reject = Button(ok, "primary"), Button(cancel, "secondary")
    accept.clicked.connect(dialog.accept)
    reject.clicked.connect(dialog.reject)
    dialog.add_actions(None, reject, accept)
    (reject if default_cancel else accept).setFocus()
    return dialog.exec() == QDialog.DialogCode.Accepted


def notify(parent, text: str, title: str = "nicoPad") -> None:
    dialog = Dialog(parent, title, 460)
    dialog.body.addWidget(Text(text, 14, 400, wrap=True))
    close = Button("OK", "primary")
    close.clicked.connect(dialog.accept)
    dialog.add_actions(None, close)
    close.setFocus()
    dialog.exec()


def ask_text(parent, title: str, label: str, initial: str = "") -> str | None:
    dialog = Dialog(parent, title, 440)
    dialog.body.addWidget(Text(label, 12, 400, alpha=0.7))
    field = _field(initial)
    field.returnPressed.connect(dialog.accept)
    dialog.body.addWidget(field)
    accept, reject = Button("OK", "primary"), Button("Cancelar", "secondary")
    accept.clicked.connect(dialog.accept)
    reject.clicked.connect(dialog.reject)
    dialog.add_actions(None, reject, accept)
    field.setFocus()
    field.selectAll()
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return field.text()


def ask_close_action(parent):
    """(«hide» | «quit» | None, lembrar?). None = cancelou."""
    dialog = Dialog(parent, "Fechar a janela", 540)  # três botões com texto: 460px cortava «Encerrar o programa»
    dialog.body.setSpacing(14)
    dialog.body.addWidget(Text("Fechar o nicoPad ou deixá-lo na bandeja?", 15, 400, wrap=True))
    dialog.body.addWidget(
        Text("Na bandeja, os atalhos continuam funcionando e os sons saem normalmente.", 13, 400, alpha=0.7, wrap=True)
    )
    remember = Check("Lembrar minha escolha")
    dialog.body.addWidget(remember)
    choice = {"value": None}

    def pick(value: str) -> None:
        choice["value"] = value
        dialog.accept()

    tray, quit_, cancel = Button("Deixar na bandeja", "primary"), Button("Encerrar o programa", "secondary"), Button("Cancelar", "ghost")
    tray.clicked.connect(lambda: pick("hide"))
    quit_.clicked.connect(lambda: pick("quit"))
    cancel.clicked.connect(dialog.reject)
    dialog.add_actions(tray, quit_, None, cancel)
    tray.setFocus()
    dialog.exec()
    return choice["value"], remember.isChecked()


class ProgressDialog(Dialog):
    """«Baixando atualização…»: sem botão de fechar, a troca já começou."""

    def __init__(self, parent, text: str):
        super().__init__(parent, "Atualizando", 420)
        self.body.addWidget(Text(text, 14, 400))
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        self.body.addWidget(bar)

    def reject(self) -> None:
        pass  # não dá para cancelar

    def closeEvent(self, event) -> None:
        event.ignore()


def _slider(value: float) -> QSlider:
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(round(value * 100))
    return slider


# ------------------------------------------------------------------- configurar som


class SoundDialog(Dialog):
    """Volume no microfone e no fone, tecla e nome do som. Os sliders valem para os próximos toques."""

    def __init__(self, win, index: int):
        super().__init__(win, "Configurar som", 520)
        self.win, self.index = win, index
        self.binding = win.settings.bindings[index]
        self.sound = win.sounds[win.sound_key(self.binding.path)]
        binding, sound = self.binding, self.sound

        name = vbox(spacing=4)
        name.addWidget(Text("Nome", 12, 400, alpha=0.7))
        self.name_field = _field(binding.name)
        self.name_field.returnPressed.connect(self.accept)
        name.addWidget(self.name_field)
        name.addSpacing(2)
        name.addWidget(Text(binding.path, 12, 400, alpha=0.6))
        self.body.addLayout(name)

        # NO MICROFONE
        self.mic_value = Text(f"{round(binding.gain * 100)}%", 32, 800)
        self.mic_slider = _slider(binding.gain)
        self.mic_slider.valueChanged.connect(self._mic_changed)
        mic_cell = self._cell("mic", "NO MICROFONE", self.mic_value, self.mic_slider, "O que os outros escutam")

        # NO MEU FONE
        self.monitor_check = Check()
        self.monitor_check.setChecked(bool(binding.monitor))
        self.monitor_value = Text("", 32, 800)
        self.monitor_slider = _slider(binding.monitor_gain)
        self.monitor_slider.valueChanged.connect(self._monitor_changed)
        self.monitor_check.toggled.connect(self._monitor_toggled)
        monitor_cell = self._cell(
            "headphones", "NO MEU FONE", self.monitor_value, self.monitor_slider, "Tocar também no meu fone", self.monitor_check
        )
        self.monitor_inner = monitor_cell.findChild(QWidget, "inner")
        self._monitor_toggled(self.monitor_check.isChecked())
        self.body.addWidget(cells(mic_cell, monitor_cell))

        # tecla
        row = Box("bg", "a1")
        line = hbox(row, (12, 10, 12, 10), 8)
        line.addWidget(Icon("keyboard", 15))
        line.addWidget(Text("Tecla", 14, 600))
        self.key_chip = Chip(binding.key or "—")
        line.addWidget(self.key_chip)
        line.addStretch(1)
        change = Button("Trocar", "ghost")
        change.clicked.connect(self._change_key)
        line.addWidget(change)
        self.body.addWidget(row)

        listen = Button("Ouvir", "secondary", icon="play", icon_size=14)
        trim = Button("Cortar", "secondary", icon="scissors")
        done = Button("Pronto", "primary")
        listen.clicked.connect(lambda: win.preview_sound(self.index))
        trim.clicked.connect(self._trim)
        done.clicked.connect(self.accept)
        self.add_actions(listen, trim, None, done)

    def _cell(self, icon: str, title: str, value: Text, slider: QSlider, note: str, check: Check | None = None) -> Box:
        cell = Box("bg")
        outer = vbox(cell)
        inner = QWidget()
        inner.setObjectName("inner")
        layout = vbox(inner, (16, 14, 16, 16), 8)
        head = hbox(spacing=6)
        head.addWidget(Icon(icon, 14, alpha=0.6))
        head.addWidget(Text(title, 11, 400, alpha=0.6, spacing=0.88), 1)
        if check is not None:
            head.addWidget(check)
        layout.addLayout(head)
        layout.addWidget(value)
        layout.addWidget(slider)
        layout.addWidget(Text(note, 12, 400, alpha=0.6))
        outer.addWidget(inner)
        return cell

    def _mic_changed(self, value: int) -> None:
        self.binding.gain = self.sound.gain = value / 100
        self.mic_value.set_text(f"{value}%")
        self.win.save_later()

    def _monitor_changed(self, value: int) -> None:
        self.binding.monitor_gain = self.sound.monitor_gain = value / 100
        self.monitor_value.set_text(f"{value}%" if self.monitor_check.isChecked() else "—")
        self.win.save_later()

    def _monitor_toggled(self, on: bool) -> None:
        self.binding.monitor = self.sound.monitor = bool(on)
        self.monitor_slider.setEnabled(on)
        self.monitor_value.set_text(f"{self.monitor_slider.value()}%" if on else "—")
        effect = QGraphicsOpacityEffect(self.monitor_inner)
        effect.setOpacity(1.0 if on else 0.55)
        self.monitor_inner.setGraphicsEffect(effect)
        self.win.save_later()

    def _change_key(self) -> None:
        self.done_action = "key"
        self.accept()

    def _trim(self) -> None:
        self.done_action = "trim"
        self.accept()

    done_action = ""

    def done(self, result: int) -> None:
        self.win.rename_sound(self.binding, self.name_field.text())
        super().done(result)


# ---------------------------------------------------------------------------- cortar


class Waveform(QWidget):
    """Forma de onda com duas alças arrastáveis (início e fim do trecho)."""

    changed = Signal()
    BARS, GAP, HANDLE = 96, 2, 3

    def __init__(self, table: np.ndarray, duration: float, start: float, end: float):
        super().__init__()
        top = np.abs(table).max(axis=1)
        self.heights = top / top.max() if top.max() > 0 else top
        self.duration, self.start, self.end = duration, start, end
        self.playhead = None  # segundo que está tocando agora (None = parado)
        self._drag = None
        self.setFixedHeight(150)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def _x(self, seconds: float) -> float:
        inner = self.width() - 4
        return 2 + (seconds / self.duration * inner if self.duration else 0)

    def _seconds(self, x: float) -> float:
        inner = max(1, self.width() - 4)
        return max(0.0, min(self.duration, (x - 2) / inner * self.duration))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), theme.color("bg"))
        inner = w - 4
        bar_w = (inner - (self.BARS - 1) * self.GAP) / self.BARS
        on, off = theme.color("accent"), theme.color("text", 0.35)
        for index, height in enumerate(self.heights):
            x = 2 + index * (bar_w + self.GAP)
            centre = (index + 0.5) / self.BARS * self.duration
            tall = max(4.0, float(height) * (h - 24))
            p.fillRect(QRectF(x, (h - tall) / 2, bar_w, tall), on if self.start <= centre <= self.end else off)
        xs, xe = self._x(self.start), self._x(self.end)
        veil = theme.color("bg", 0.55)
        p.fillRect(QRectF(2, 2, max(0.0, xs - 2), h - 4), veil)
        p.fillRect(QRectF(xe, 2, max(0.0, w - 2 - xe), h - 4), veil)
        accent = theme.color("accent")
        p.fillRect(QRectF(xs - 1.5, 2, self.HANDLE, h - 4), accent)
        p.fillRect(QRectF(xe - 1.5, 2, self.HANDLE, h - 4), accent)
        p.fillRect(QRectF(xs + 1.5, 2, 14, 18), accent)  # bandeira do início: topo, à direita da linha
        p.fillRect(QRectF(xe - 1.5 - 14, h - 2 - 18, 14, 18), accent)  # bandeira do fim: base, à esquerda
        if self.playhead is not None:  # cabeça de reprodução: linha text com halo de bg para aparecer sobre as barras
            xp = self._x(self.playhead)
            p.fillRect(QRectF(xp - 2.5, 2, 5, h - 4), theme.color("bg"))
            p.fillRect(QRectF(xp - 1, 2, 2, h - 4), theme.color("text"))
        line = theme.color("divider")
        for rect in (QRectF(0, 0, w, 2), QRectF(0, h - 2, w, 2), QRectF(0, 0, 2, h), QRectF(w - 2, 0, 2, h)):
            p.fillRect(rect, line)

    def _move(self, x: float) -> None:
        seconds = self._seconds(x)
        gap = self.duration * 0.03
        if self._drag == "start":
            self.start = max(0.0, min(seconds, self.end - gap))
        else:
            self.end = min(self.duration, max(seconds, self.start + gap))
        self.update()
        self.changed.emit()

    def mousePressEvent(self, event) -> None:
        x = event.position().x()
        self._drag = "start" if abs(x - self._x(self.start)) <= abs(x - self._x(self.end)) else "end"
        self._move(x)

    def mouseMoveEvent(self, event) -> None:
        if self._drag:
            self._move(event.position().x())

    def mouseReleaseEvent(self, _event) -> None:
        self._drag = None

    def reset(self) -> None:
        self.start, self.end = 0.0, self.duration
        self.update()
        self.changed.emit()


class TrimDialog(Dialog):
    """Corte não destrutivo: só grava `start`/`end` em segundos."""

    def __init__(self, win, binding, full):
        super().__init__(win, "Cortar som", 720, resizable=True)
        self.win, self.binding = win, binding
        duration = len(full.data) / full.samplerate if full.samplerate else 0.0
        end = binding.end if 0 < binding.end <= duration else duration
        self.wave = Waveform(peaks(full.data, Waveform.BARS), duration, min(binding.start, duration), end)
        self.duration = duration

        self.body.addWidget(
            Text(f"Arraste as alças para marcar onde «{binding.name}» começa e termina. O arquivo original não é alterado.", 13, 400, alpha=0.7, wrap=True)
        )
        self.body.addWidget(self.wave)
        self.values = []
        blocks = []
        for title in ("INÍCIO", "FIM", "TRECHO", "TOCANDO"):
            block = Box("bg")
            layout = vbox(block, (16, 12, 16, 12), 4)
            layout.addWidget(Text(title, 11, 400, alpha=0.6, spacing=0.88))
            value = Text("", 20, 800, tone="accent_700" if title == "TRECHO" else "text")
            layout.addWidget(value)
            self.values.append(value)
            blocks.append(block)
        self.body.addWidget(cells(*blocks))
        self.wave.changed.connect(self._refresh)
        self._refresh()
        self.values[3].set_text("—")
        self._clock = QTimer(self, interval=30)
        self._clock.timeout.connect(self._advance)
        self._started = self._length = 0.0

        listen = Button("Ouvir trecho", "secondary", icon="play", icon_size=14)
        everything = Button("Tudo", "ghost")
        save = Button("Salvar corte", "primary")
        listen.clicked.connect(self._listen)
        everything.clicked.connect(self.wave.reset)
        save.clicked.connect(self.accept)
        self.add_actions(listen, everything, None, save)

    def _refresh(self) -> None:
        start, end = self.wave.start, self.wave.end
        for value, seconds in zip(self.values, (start, end, end - start)):
            value.set_text(seconds_text(seconds))

    def _listen(self) -> None:
        """Toca o trecho do começo e acompanha a posição na forma de onda."""
        start = self.wave.start
        length = self.win.preview_clip(self.binding, start, self.wave.end)
        if length is None:
            self._stop_clock()
            return
        self._started, self._length, self._from = time.monotonic(), length, start
        self._clock.start()
        self._advance()

    def _advance(self) -> None:
        elapsed = time.monotonic() - self._started
        if elapsed >= self._length:
            self._stop_clock()
            return
        self.wave.playhead = self._from + elapsed
        self.values[3].set_text(seconds_text(self.wave.playhead))
        self.wave.update()

    def _stop_clock(self) -> None:
        self._clock.stop()
        self.wave.playhead = None
        self.values[3].set_text("—")
        self.wave.update()

    def done(self, result: int) -> None:
        self._clock.stop()
        self.win.stop_clip()  # fechar a janela cala a prévia
        super().done(result)

    @property
    def edges(self) -> tuple:
        return self.wave.start, self.wave.end, self.duration


# --------------------------------------------------------------------------- youtube


class YoutubeDialog(Dialog):
    progress = Signal(float, str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, win, folder: str):
        super().__init__(win, "Baixar do YouTube", 520)
        self.win, self.folder = win, folder
        self.busy = False
        self.path = None

        if youtube.has_ffmpeg() is None:
            warning = Box("accent_100")
            hbox(warning, (14, 12, 14, 12), 8).addWidget(
                Text("O download precisa do ffmpeg instalado, e ele não foi encontrado neste PC.", 14, 800, tone="accent_800", wrap=True)
            )
            self.body.addWidget(warning)
            site, close = Button("Abrir site do ffmpeg", "primary"), Button("Fechar", "secondary")
            site.clicked.connect(lambda: webbrowser.open(FFMPEG_URL))
            close.clicked.connect(self.reject)
            self.add_actions(site, None, close)
            self.field = None
            return

        label = vbox(spacing=4)
        label.addWidget(Text("URL do vídeo", 12, 400, alpha=0.7))
        row = hbox(spacing=8)
        self.field = _field(placeholder="https://www.youtube.com/watch?v=…")
        self.field.returnPressed.connect(self._start)
        self.button = Button("Baixar", "primary", icon="download")
        self.button.clicked.connect(self._start)
        row.addWidget(self.field, 1)
        row.addWidget(self.button)
        label.addLayout(row)
        self.body.addLayout(label)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.body.addWidget(self.bar)
        self.status = Text("", 13, 400, alpha=0.7, wrap=True)
        self.status.setMinimumHeight(19)
        self.body.addWidget(self.status)
        self.body.addWidget(
            Text("O áudio vai direto para a pasta dos sons e aparece na lista pronto para receber uma tecla.", 12, 400, alpha=0.6, wrap=True)
        )
        close = Button("Fechar", "secondary")
        close.clicked.connect(self.reject)
        self.add_actions(None, close)
        self.progress.connect(self._on_progress)
        self.finished_ok.connect(self._on_done)
        self.failed.connect(self._on_failed)
        self.field.setFocus()

    def _start(self) -> None:
        if self.busy:
            return
        url = self.field.text().strip()
        reason = youtube.check_url(url)
        if reason:
            self.status.set_text(reason)
            return
        self.busy = True
        self.field.setEnabled(False)
        self.button.setEnabled(False)
        self.status.set_text("Baixando…")

        def work() -> None:
            try:
                path = youtube.download(url, self.folder, lambda fraction, text: self.progress.emit(fraction, text))
                self.finished_ok.emit(str(path))
            except Exception as exc:
                self.failed.emit(str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, fraction: float, text: str) -> None:
        self.bar.setValue(round(fraction * 100))
        self.status.set_text(f"{text} {round(fraction * 100)}%" if text == "Baixando…" else text)

    def _on_done(self, path: str) -> None:
        self.busy = False
        self.path = path
        self.accept()

    def _on_failed(self, message: str) -> None:
        self.busy = False
        self.status.set_text(f"Erro: {message}")
        self.field.setEnabled(True)
        self.button.setEnabled(True)

    def reject(self) -> None:
        if self.busy and not confirm(
            self, "O download continua em segundo plano, mas o som não vai entrar na lista.\n\nFechar mesmo assim?"
        ):
            return
        self.busy = False
        super().reject()


# ------------------------------------------------------------------------------ guia

GUIDE_STEPS = (
    "Clique em «Preparar instalador do cabo». O nicoPad coloca o pacote oficial do VB-Cable na sua pasta e abre ela com o instalador já selecionado.",
    "Clique com o botão direito em VBCABLE_Setup_x64.exe e escolha «Executar como administrador». Depois reinicie o PC.",
    "Volte aqui, abra «Configurar áudio» e escolha CABLE Input (VB-Audio Virtual Cable).",
    "Marque «Misturar meu microfone» e escolha seu microfone de verdade, senão sua voz deixa de sair junto com os sons.",
    "No Discord/jogo, troque o microfone de entrada para CABLE Output (VB-Audio Virtual Cable).",
)
GUIDE_NOTE = (
    "O nicoPad não instala o driver sozinho: a licença do VB-Cable permite difundir o pacote original, mas não integrá-lo ao "
    "instalador de outro programa. VB-Cable é donationware de Vincent Burel (www.vb-cable.com). Se for útil para você, "
    "considere participar do projeto."
)


class GuideDialog(Dialog):
    def __init__(self, win):
        super().__init__(win, "Como configurar o cabo", 660, body_margins=(0, 0, 0, 0))
        self.open_wizard = False
        self.body.setSpacing(0)
        intro = Box(border="b2")
        hbox(intro, (16, 14, 16, 14)).addWidget(
            Text("O microfone dos outros jogadores precisa de um cabo de áudio virtual (driver VB-Cable).", 14, 400, wrap=True)
        )
        self.body.addWidget(intro)
        for number, step in enumerate(GUIDE_STEPS, 1):
            row = Box(border="b1")
            line = hbox(row, (16, 12, 16, 12), 0)
            line.addWidget(Text(str(number), 24, 800, tone="accent"))
            line.itemAt(0).widget().setFixedWidth(40)
            line.addWidget(Text(step, 14, 400, wrap=True), 1)
            self.body.addWidget(row)
        note = QWidget()
        hbox(note, (16, 12, 16, 14)).addWidget(Text(GUIDE_NOTE, 12, 400, alpha=0.6, wrap=True))
        self.body.addWidget(note)

        prepare = Button("Preparar instalador do cabo", "primary", icon="plug")
        site = Button("Abrir site do VB-Cable", "secondary")
        wizard = Button("Abrir assistente", "ghost")
        prepare.clicked.connect(win.prepare_cable)
        site.clicked.connect(lambda: webbrowser.open(CABLE_URL))
        wizard.clicked.connect(self._wizard)
        self.add_actions(prepare, site, None, wizard)

    def _wizard(self) -> None:
        self.open_wizard = True
        self.accept()


# ------------------------------------------------------------------- cor de destaque


class Swatch(QAbstractButton):
    """Um quadradinho da matriz de cores; o selecionado ganha contorno de 2px na cor do texto."""

    def __init__(self, value: str):
        super().__init__()
        self.value = value
        self.setFixedSize(36, 36)
        self.setCheckable(True)
        self.setToolTip(value)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(self.value))
        if self.isChecked():
            ring = theme.color("text")
            for rect in (QRectF(0, 0, 36, 2), QRectF(0, 34, 36, 2), QRectF(0, 0, 2, 36), QRectF(34, 0, 2, 36)):
                p.fillRect(rect, ring)


class AccentDialog(Dialog):
    """Escolhe a cor de destaque numa matriz; o app inteiro muda na hora."""

    def __init__(self, win):
        super().__init__(win, "Cor de destaque", 520)
        self.win = win
        self.body.addWidget(
            Text("Escolha a cor. Os tons mais claros e escuros e o tema escuro são calculados a partir dela.", 13, 400, alpha=0.7, wrap=True)
        )
        self.swatches = []
        grid = QGridLayout()
        grid.setSpacing(6)
        for row, colors in enumerate(theme.swatches()):
            for column, value in enumerate(colors):
                swatch = Swatch(value)
                swatch.clicked.connect(lambda _checked=False, v=value: self._pick(v))
                grid.addWidget(swatch, row, column)
                self.swatches.append(swatch)
        self.body.addLayout(grid)
        reset, done = Button("Vermelho original", "secondary"), Button("Pronto", "primary")
        reset.clicked.connect(lambda: self._pick(""))
        done.clicked.connect(self.accept)
        self.add_actions(reset, None, done)
        self._mark()

    def _pick(self, value: str) -> None:
        self.win.set_accent("" if value.lower() == theme.REFERENCE_ACCENT else value)
        self._mark()

    def _mark(self) -> None:
        current = (theme.accent() or theme.REFERENCE_ACCENT).lower()
        for swatch in self.swatches:
            swatch.setChecked(swatch.value.lower() == current)
