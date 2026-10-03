"""Visualizações dos sons: Lista (linhas) e Pads (grade). Ambas pintadas à mão com as cores do tema."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QGridLayout, QScrollArea, QSizePolicy, QWidget

from nicopad import theme
from nicopad.ui.widgets import Box, Button, Text, vbox, wrap_lines


@dataclass
class RowState:
    """O que a tela precisa saber de um som para se pintar (montado pela janela principal)."""

    name: str
    key_label: str  # "F1", "—" ou "Aperte…"
    has_key: bool
    missing: bool
    duration: str  # "1,8 s" ou "—"
    monitor: str  # "80%" ou "—"
    monitor_on: bool
    path: str
    progress: float | None  # None = parado
    listening: bool
    selected: bool


def seconds_text(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " s"


# ------------------------------------------------------------------------------ lista

PAD_X, GAP = 16, 8
COL_KEY, COL_DUR, COL_MON, COL_ACT = 130, 70, 80, 176


def columns(width: int) -> dict:
    """Posição (x, largura) de cada coluna. Estreito: o arquivo sai primeiro, depois o «No fone»."""
    show_file, show_mon = width >= 820, width >= 700
    order = ["key", "name", "dur"] + (["mon"] if show_mon else []) + (["file"] if show_file else []) + ["act"]
    fixed = {"key": COL_KEY, "dur": COL_DUR, "mon": COL_MON, "act": COL_ACT}
    flex = {"name": 1.3, "file": 1.4}
    room = width - 2 * PAD_X - GAP * (len(order) - 1) - sum(fixed.get(name, 0) for name in order)
    share = sum(flex.get(name, 0) for name in order)
    found, x = {}, PAD_X
    for name in order:
        size = fixed.get(name) or max(40, int(room * flex[name] / share))
        found[name] = (x, size)
        x += size + GAP
    return found


class ListHeader(Box):
    HEIGHT = 38

    def __init__(self, parent=None):
        super().__init__(border="b2", parent=parent)
        self.setFixedHeight(self.HEIGHT)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setFont(theme.font(11, 400, 0.88))
        p.setPen(theme.color("text", 0.60))
        titles = {"key": "TECLA", "name": "SOM", "dur": "DURAÇÃO", "mon": "NO FONE", "file": "ARQUIVO"}
        for name, (x, width) in columns(self.width()).items():
            if name in titles:
                p.drawText(QRectF(x, 0, width, self.height() - 2), Qt.AlignmentFlag.AlignVCenter, titles[name])


class SoundRow(QWidget):
    HEIGHT = 48

    def __init__(self, view, index: int):
        super().__init__()
        self.view, self.win, self.index = view, view.win, index
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedHeight(self.HEIGHT)
        self.buttons = {}
        for name, icon, tip in (
            ("play", "play", "Ouvir"),
            ("key", "keyboard", "Definir tecla"),
            ("trim", "scissors", "Cortar"),
            ("config", "settings", "Configurar som"),
            ("remove", "trash", "Remover"),
        ):
            button = Button(kind="icon", icon=icon, icon_size=15, parent=self)
            button.setToolTip(tip)
            self.buttons[name] = button
        self.buttons["remove"].danger = True
        self.buttons["play"].clicked.connect(lambda: self.win.toggle_play(self.index))
        self.buttons["key"].clicked.connect(lambda: self.win.start_binding(self.index))
        self.buttons["trim"].clicked.connect(lambda: self.win.trim_dialog(self.index))
        self.buttons["config"].clicked.connect(lambda: self.win.sound_dialog(self.index))
        self.buttons["remove"].clicked.connect(lambda: self.win.remove(self.index))
        self.sync()

    def sync(self) -> None:
        state = self.win.row_state(self.index)
        play = self.buttons["play"]
        play.active = state.progress is not None
        play.icon_name = "stop" if play.active else "play"
        self.setToolTip(state.path)
        self.update()
        play.update()

    def resizeEvent(self, _event) -> None:
        x, width = columns(self.width())["act"]
        for position, button in enumerate(self.buttons.values()):
            button.move(x + width - 168 + position * 34, (self.height() - 32) // 2)

    def mousePressEvent(self, event) -> None:
        self.view.setFocus()
        self.win.select(self.index)

    def mouseDoubleClickEvent(self, _event) -> None:
        self.win.sound_dialog(self.index)

    def paintEvent(self, _event) -> None:
        state = self.win.row_state(self.index)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if state.listening:
            p.fillRect(self.rect(), theme.color("accent_100"))
        elif state.selected:
            p.fillRect(self.rect(), theme.color("text", 0.07))
        elif self.underMouse():
            p.fillRect(self.rect(), theme.color("text", 0.04))
        p.fillRect(0, h - 1, w, 1, theme.color("divider"))

        cols = columns(w)
        vcenter = Qt.AlignmentFlag.AlignVCenter

        # tecla: chip de 1px (cheio de accent enquanto grava)
        x, width = cols["key"]
        p.setFont(theme.font(12, 800))
        chip_w = min(width, QFontMetrics(p.font()).horizontalAdvance(state.key_label) + 16)
        chip = QRectF(x, (h - 24) / 2, chip_w, 24)
        if state.listening:
            p.fillRect(chip, theme.color("accent"))
            p.setPen(theme.color("accent"))
            p.drawRect(chip.adjusted(0.5, 0.5, -0.5, -0.5))
            p.setPen(theme.color("bg"))
        else:
            p.setPen(theme.color("divider"))
            p.drawRect(chip.adjusted(0.5, 0.5, -0.5, -0.5))
            p.setPen(theme.color("text") if state.has_key else theme.color("text", 0.60))
        p.drawText(chip, Qt.AlignmentFlag.AlignCenter, state.key_label)

        # nome (+ etiqueta quando o arquivo sumiu)
        x, width = cols["name"]
        p.setFont(theme.font(14, 600))
        p.setPen(theme.color("text"))
        tag_w = 0
        if state.missing:
            tag_font = theme.font(11, 400)
            tag_w = QFontMetrics(tag_font).horizontalAdvance("não encontrado") + 16
        name = QFontMetrics(p.font()).elidedText(state.name, Qt.TextElideMode.ElideRight, max(20, width - tag_w - 8))
        p.drawText(QRectF(x, 0, width, h), vcenter, name)
        if state.missing:
            used = QFontMetrics(p.font()).horizontalAdvance(name)
            tag = QRectF(x + used + 8, (h - 20) / 2, tag_w, 20)
            p.fillRect(tag, theme.color("accent_100"))
            p.setFont(theme.font(11, 400))
            p.setPen(theme.color("accent_800"))
            p.drawText(tag, Qt.AlignmentFlag.AlignCenter, "não encontrado")

        p.setFont(theme.font(13, 400))
        p.setPen(theme.color("text"))
        x, width = cols["dur"]
        p.drawText(QRectF(x, 0, width, h), vcenter, state.duration)
        if "mon" in cols:
            x, width = cols["mon"]
            p.setPen(theme.color("text") if state.monitor_on else theme.color("text", 0.60))
            p.drawText(QRectF(x, 0, width, h), vcenter, state.monitor)
        if "file" in cols:
            x, width = cols["file"]
            p.setFont(theme.font(12, 400))
            p.setPen(theme.color("text", 0.60))
            path = QFontMetrics(p.font()).elidedText(state.path, Qt.TextElideMode.ElideMiddle, width)
            p.drawText(QRectF(x, 0, width, h), vcenter, path)

        if state.progress is not None:
            p.fillRect(QRectF(0, h - 3, w * min(1.0, state.progress), 3), theme.color("accent"))


class _Keys:
    """Teclado comum às duas visualizações: setas movem a seleção, Enter ouve, Delete remove."""

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.win.preview_selected()
        elif key == Qt.Key.Key_Delete:
            self.win.remove_selected()
        elif key in self.NEXT:
            self.win.move_selection(1)
        elif key in self.PREVIOUS:
            self.win.move_selection(-1)
        else:
            super().keyPressEvent(event)


class ListView(_Keys, QWidget):
    NEXT, PREVIOUS = (Qt.Key.Key_Down,), (Qt.Key.Key_Up,)

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.rows = {}
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.header = ListHeader()
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.column = vbox(self.body)
        self.column.addStretch(1)
        self.area.setWidget(self.body)
        layout = vbox(self)
        layout.addWidget(self.header)
        layout.addWidget(self.area, 1)
        self.empty = QWidget(self.body)
        empty = vbox(self.empty, (16, 28, 16, 28), 4)
        self.empty_title, self.empty_note = Text("", 15, 800), Text("", 13, 400, alpha=0.6, wrap=True)
        empty.addWidget(self.empty_title)
        empty.addWidget(self.empty_note)
        self.column.insertWidget(0, self.empty)
        # a barra de rolagem come largura das linhas: o cabeçalho acompanha para as colunas alinharem
        self.area.viewport().installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.area.viewport() and event.type() == QEvent.Type.Resize:
            self.header.setFixedWidth(event.size().width())
        return False

    def refresh(self, indices: list) -> None:
        query = self.win.query.strip()
        self.empty.setVisible(not indices)
        self.empty_title.set_text(f"Nenhum som encontrado para «{query}»" if query else "Nenhum som neste mapa")
        self.empty_note.set_text("" if query else "Clique em «Adicionar som» ou baixe um áudio do YouTube.")
        for row in self.rows.values():
            row.setParent(None)
            row.deleteLater()
        self.rows = {}
        for position, index in enumerate(indices):
            row = SoundRow(self, index)
            self.column.insertWidget(position + 1, row)
            self.rows[index] = row

    def sync(self, indices=None) -> None:
        for index, row in self.rows.items():
            if indices is None or index in indices:
                row.sync()

    def reveal(self, index: int) -> None:
        row = self.rows.get(index)
        if row is not None:
            self.area.ensureWidgetVisible(row, 0, 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # a barra de rolagem come largura das linhas: o cabeçalho acompanha para as colunas alinharem
        self.header.setFixedWidth(self.area.viewport().width())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.header.setFixedWidth(self.area.viewport().width())


# ------------------------------------------------------------------------------- pads


class PadCell(QWidget):
    MIN_HEIGHT = 140

    def __init__(self, view, index: int):
        super().__init__()
        self.view, self.win, self.index = view, view.win, index
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.key_button = Button(kind="icon", icon="keyboard", size=28, icon_size=15, parent=self)
        self.key_button.setToolTip("Definir tecla")
        self.config_button = Button(kind="icon", icon="settings", size=28, icon_size=15, parent=self)
        self.config_button.setToolTip("Configurar som")
        for button in (self.key_button, self.config_button):
            button.alpha = 0.75
        self.key_button.clicked.connect(lambda: self.win.start_binding(self.index))
        self.config_button.clicked.connect(lambda: self.win.sound_dialog(self.index))
        self.sync()

    def sync(self) -> None:
        state = self.win.row_state(self.index)
        self.setToolTip(state.path)
        for button in (self.key_button, self.config_button):  # ícones seguem a cor do estado do pad
            button.fg = "bg" if state.progress is not None else "accent_800" if state.listening else None
            button.update()
        self.update()

    def resizeEvent(self, _event) -> None:
        self.config_button.move(self.width() - 12 - 28, 10)
        self.key_button.move(self.width() - 12 - 28 * 2 - 2, 10)

    def mousePressEvent(self, event) -> None:
        self.view.setFocus()
        self.win.select(self.index)
        self.win.toggle_play(self.index)

    def mouseDoubleClickEvent(self, _event) -> None:
        self.win.sound_dialog(self.index)

    def paintEvent(self, _event) -> None:
        state = self.win.row_state(self.index)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        playing = state.progress is not None
        if playing:
            fill, ink, quiet = "accent", "bg", "bg"
        elif state.listening:
            fill, ink, quiet = "accent_100", "accent_800", "accent_800"
        else:
            fill, ink, quiet = "bg", "text", None
        p.fillRect(self.rect(), theme.color(fill))
        if self.underMouse() and not playing and not state.listening:
            p.fillRect(self.rect(), theme.color("text", 0.04))
        muted = theme.color(quiet) if quiet else theme.color("text", 0.60)

        # tecla grande no topo; sem tecla, «—» apagado
        p.setFont(theme.font(28, 800, -0.56))
        p.setPen(theme.color(ink) if state.has_key or state.listening else muted)
        key_room = w - 28 - 66
        key = QFontMetrics(p.font()).elidedText(state.key_label, Qt.TextElideMode.ElideRight, key_room)
        p.drawText(QRectF(14, 12, key_room, 34), Qt.AlignmentFlag.AlignVCenter, key)

        # base: nome (até 2 linhas) e metadado
        name_font, meta_font = theme.font(15, 600), theme.font(12, 400)
        meta_h = QFontMetrics(meta_font).height()
        if state.missing:
            meta, meta_color = "arquivo não encontrado", theme.color("accent_700") if not playing else theme.color("bg")
        else:
            meta = state.duration + ("  ·  fone " + state.monitor if state.monitor_on else "  ·  só no mic")
            meta_color = muted
        p.setFont(meta_font)
        p.setPen(meta_color)
        meta_y = h - 16 - meta_h
        p.drawText(QRectF(14, meta_y, w - 28, meta_h), Qt.AlignmentFlag.AlignVCenter, meta)
        lines = wrap_lines(state.name, name_font, w - 28, 2)
        line_h = QFontMetrics(name_font).lineSpacing()
        p.setFont(name_font)
        p.setPen(theme.color(ink))
        top = meta_y - 6 - line_h * len(lines)
        for position, line in enumerate(lines):
            p.drawText(QRectF(14, top + position * line_h, w - 28, line_h), Qt.AlignmentFlag.AlignVCenter, line)

        if playing:
            p.fillRect(QRectF(0, h - 4, w * min(1.0, state.progress), 4), theme.color("bg"))
        outline = "accent" if state.listening else "text" if state.selected else None
        if outline:
            ring = theme.color(outline)
            p.fillRect(0, 0, w, 2, ring)
            p.fillRect(0, h - 2, w, 2, ring)
            p.fillRect(0, 0, 2, h, ring)
            p.fillRect(w - 2, 0, 2, h, ring)


class AddCell(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setMinimumHeight(PadCell.MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def mousePressEvent(self, _event) -> None:
        self.win.add_sounds()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), theme.color("bg"))
        if self.underMouse():
            p.fillRect(self.rect(), theme.color("accent", 0.08))
        accent = theme.color("accent")
        sub_font, title_font = theme.font(12, 400), theme.font(15, 800)
        sub_h, title_h = QFontMetrics(sub_font).height(), QFontMetrics(title_font).height()
        sub_y = h - 16 - sub_h
        title_y = sub_y - 4 - title_h
        theme.draw_icon(p, "plus", QRectF(14, title_y - 6 - 26, 26, 26), accent, 2.5)
        p.setFont(title_font)
        p.setPen(accent)
        p.drawText(QRectF(14, title_y, w - 28, title_h), Qt.AlignmentFlag.AlignVCenter, "Adicionar som")
        p.setFont(sub_font)
        p.setPen(theme.color("text", 0.60))
        p.drawText(QRectF(14, sub_y, w - 28, sub_h), Qt.AlignmentFlag.AlignVCenter, "wav, mp3, ogg, opus, flac, aiff")


class PadView(_Keys, QScrollArea):
    NEXT, PREVIOUS = (Qt.Key.Key_Right, Qt.Key.Key_Down), (Qt.Key.Key_Left, Qt.Key.Key_Up)
    COLUMNS = 3

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.cells = {}
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        outer = vbox(self.body)
        # o fundo na cor da régua + espaço de 2px entre as células desenha a grade
        self.grid_box = Box("divider")
        self.grid = QGridLayout(self.grid_box)
        self.grid.setContentsMargins(0, 0, 0, 2)
        self.grid.setSpacing(2)
        for column in range(self.COLUMNS):
            self.grid.setColumnStretch(column, 1)
        outer.addWidget(self.grid_box)
        outer.addStretch(1)
        self.setWidget(self.body)

    def refresh(self, indices: list) -> None:
        while self.grid.count():
            widget = self.grid.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.cells = {}
        widgets = []
        for index in indices:
            cell = PadCell(self, index)
            self.cells[index] = cell
            widgets.append(cell)
        widgets.append(AddCell(self.win))
        while len(widgets) % self.COLUMNS:  # nunca deixar buraco na cor da régua
            widgets.append(Box("bg"))
        for position, widget in enumerate(widgets):
            self.grid.addWidget(widget, position // self.COLUMNS, position % self.COLUMNS)
        for row in range(len(widgets) // self.COLUMNS):
            self.grid.setRowMinimumHeight(row, PadCell.MIN_HEIGHT)

    def sync(self, indices=None) -> None:
        for index, cell in self.cells.items():
            if indices is None or index in indices:
                cell.sync()

    def reveal(self, index: int) -> None:
        cell = self.cells.get(index)
        if cell is not None:
            self.ensureWidgetVisible(cell, 0, 0)
