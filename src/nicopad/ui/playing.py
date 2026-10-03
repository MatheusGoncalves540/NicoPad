"""«Tocando agora»: janela solta (não modal) com uma linha por voz: progresso, volume ao vivo, loop e parar."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QScrollArea, QWidget

from nicopad import theme
from nicopad.ui.widgets import Box, Button, Text, hbox, vbox

LEVEL_STEP = 0.1
LEVEL_MAX = 2.0  # até 200% do volume do som; a mistura já limita os picos
COLUMNS = (136, 88, 92)  # volume · loop · parar (o nome ocupa o resto)
GAP, PAD = 12, 16


class _Header(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(31)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(0, self.height() - 1, self.width(), 1, theme.color("divider"))
        p.setFont(theme.font(11, 400, 0.88))
        p.setPen(theme.color("text", 0.60))
        fixed = sum(COLUMNS) + 3 * GAP
        p.drawText(QRectF(PAD, 0, self.width() - 2 * PAD - fixed, 30), Qt.AlignmentFlag.AlignVCenter, "SOM · TOCADO")
        p.drawText(QRectF(self.width() - PAD - fixed + GAP, 0, COLUMNS[0], 30), Qt.AlignmentFlag.AlignVCenter, "VOLUME")


class _Bar(QWidget):
    """Trilho de 4px com a fração tocada."""

    def __init__(self):
        super().__init__()
        self.fraction = 0.0
        self.setFixedHeight(4)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), theme.color("text", 0.12))
        p.fillRect(QRectF(0, 0, self.width() * min(1.0, self.fraction), 4), theme.color("accent"))


class VoiceRow(QWidget):
    def __init__(self, window, voice_id: int):
        super().__init__()
        self.owner, self.voice_id = window, voice_id
        self.loop, self.level = False, 1.0
        outer = Box(border="b1")
        line = hbox(outer, (PAD, 12, PAD, 12), GAP)
        holder = vbox(self)
        holder.addWidget(outer)

        name_column = vbox(spacing=6)
        top = hbox(spacing=8)
        self.name = Text("", 14, 600)
        self.percent = Text("", 12, 800, align=Qt.AlignmentFlag.AlignRight)
        self.percent.setFixedWidth(40)
        top.addWidget(self.name, 1)
        top.addWidget(self.percent)
        self.bar = _Bar()
        name_column.addLayout(top)
        name_column.addWidget(self.bar)
        line.addLayout(name_column, 1)

        stepper = Box(border="a1")
        stepper.setFixedSize(COLUMNS[0], 34)
        steps = hbox(stepper)
        down, up = Button(kind="icon", icon="minus", size=(34, 32), icon_size=14), Button(kind="icon", icon="plus", size=(34, 32), icon_size=14)
        down.setToolTip("Menos volume")
        up.setToolTip("Mais volume")
        self.value = Text("100%", 13, 800, align=Qt.AlignmentFlag.AlignCenter)
        left, right = Box(border="r1"), Box(border="l1")
        left.setFixedWidth(35)
        right.setFixedWidth(35)
        hbox(left).addWidget(down)
        hbox(right).addWidget(up)
        steps.addWidget(left)
        steps.addWidget(self.value, 1)
        steps.addWidget(right)
        line.addWidget(stepper)
        down.clicked.connect(lambda: self._level(-LEVEL_STEP))
        up.clicked.connect(lambda: self._level(LEVEL_STEP))

        self.loop_button = Button("Loop", "secondary", icon="repeat", icon_size=14)
        self.loop_button.setToolTip("Repetir")
        self.loop_button.setFixedSize(COLUMNS[1], 34)
        self.loop_button.clicked.connect(lambda: self._act(lambda e: e.set_loop(self.voice_id, not self.loop)))
        stop = Button("Parar", "secondary", icon="stop", icon_size=12)
        stop.setToolTip("Parar só este som")
        stop.danger = True
        stop.setFixedSize(COLUMNS[2], 34)
        stop.clicked.connect(lambda: self._act(lambda e: e.stop_voice(self.voice_id)))
        line.addWidget(self.loop_button)
        line.addWidget(stop)

    def _act(self, action) -> None:
        action(self.owner.engine)
        self.owner.refresh()

    def _level(self, step: float) -> None:
        level = max(0.0, min(LEVEL_MAX, round(self.level + step, 2)))
        self._act(lambda e: e.set_level(self.voice_id, level))

    def update_voice(self, voice) -> None:
        """Atualiza os valores no lugar (sem recriar a linha: nada de piscar)."""
        _id, name, fraction, loop, level, _path = voice
        self.loop, self.level = loop, level
        self.name.set_text(name)
        self.percent.set_text(f"{round(fraction * 100)}%")
        self.bar.fraction = fraction
        self.bar.update()
        self.value.set_text(f"{round(level * 100)}%", "accent_700" if level > 1 else "text")
        self.loop_button.active = loop
        self.loop_button.update()


class PlayingWindow(QWidget):
    visibility = Signal(bool)

    def __init__(self, win):
        super().__init__(win, Qt.WindowType.Window)
        self.win = win
        self.engine = win.engine
        self.rows = {}
        self.setWindowTitle("nicoPad · Tocando agora")
        self.setWindowIcon(win.windowIcon())
        self.setMinimumSize(560, 240)
        self.resize(600, 420)

        outer = vbox(self)
        head = Box(border="b2")
        line = hbox(head, (16, 14, 16, 14), 10)
        line.addWidget(Text("Tocando agora", 20, 800))
        self.summary = Text("", 13, 400, alpha=0.6)
        line.addWidget(self.summary, 1)
        outer.addWidget(head)
        outer.addWidget(_Header())

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self.column = vbox(body)
        self.empty = QWidget()
        empty = vbox(self.empty, (16, 28, 16, 28), 4)
        empty.addWidget(Text("Nada tocando", 15, 800))
        empty.addWidget(Text("Aperte a tecla de um som ou clique num pad. Ele aparece aqui enquanto toca.", 13, 400, alpha=0.6, wrap=True))
        self.column.addWidget(self.empty)
        self.column.addStretch(1)
        self.area.setWidget(body)
        outer.addWidget(self.area, 1)

        foot = Box(border="t2")
        row = hbox(foot, (16, 12, 16, 12), 12)
        self.stop_all = Button("Parar tudo", "primary", icon="stop", icon_size=12)
        self.stop_all.clicked.connect(win.stop_all)
        row.addWidget(self.stop_all)
        row.addWidget(Text("Janela solta: os atalhos e a janela principal continuam valendo.", 12, 400, alpha=0.6, wrap=True), 1)
        outer.addWidget(foot)

    def refresh(self) -> None:
        self.win.refresh_voices()

    def set_stop_key(self, key: str) -> None:
        self.stop_all.trailing = f"chip:{key}" if key else None
        self.stop_all.updateGeometry()
        self.stop_all.update()

    def update_voices(self, voices: list) -> None:
        by_id = {voice[0]: voice for voice in voices}
        for voice_id in [i for i in self.rows if i not in by_id]:
            row = self.rows.pop(voice_id)
            row.setParent(None)
            row.deleteLater()
        for voice_id, voice in by_id.items():
            row = self.rows.get(voice_id)
            if row is None:
                row = self.rows[voice_id] = VoiceRow(self, voice_id)
                self.column.insertWidget(self.column.count() - 1, row)
            row.update_voice(voice)
        self.empty.setVisible(not by_id)
        loops = sum(1 for voice in voices if voice[3])
        count = len(voices)
        self.summary.set_text(
            f"{count} {'som' if count == 1 else 'sons'}" + (f" · {loops} em loop" if loops else "") if count else ""
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.visibility.emit(True)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.visibility.emit(False)
