"""Peças visuais do nicoPad: tudo plano, pintado com as cores do tema (sem raio, sem sombra)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QTextLayout, QTextOption
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from nicopad import theme


def vbox(parent=None, margins=(0, 0, 0, 0), spacing=0) -> QVBoxLayout:
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout


def hbox(parent=None, margins=(0, 0, 0, 0), spacing=0) -> QHBoxLayout:
    layout = QHBoxLayout(parent)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout


def wrap_lines(text: str, fnt, width: int, max_lines: int) -> list:
    """Quebra o texto em até `max_lines` linhas; a última termina em «…» se faltou espaço."""
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)  # caminhos sem espaço também quebram
    lines = []
    for paragraph in text.split(chr(10)):  # o QTextLayout não quebra em quebra de linha sozinho
        layout = QTextLayout(paragraph, fnt)
        layout.setTextOption(option)
        layout.beginLayout()
        found = []
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(1, width))
            found.append(paragraph[line.textStart() : line.textStart() + line.textLength()].rstrip())
        layout.endLayout()
        lines.extend(found or [""])
    if len(lines) <= max_lines:
        return lines
    tail = " ".join(lines[max_lines - 1 :])
    return lines[: max_lines - 1] + [QFontMetrics(fnt).elidedText(tail, Qt.TextElideMode.ElideRight, width)]


class Box(QWidget):
    """Um retângulo com fundo e bordas de régua: `border="b2"` = 2px embaixo, `"a1"` = 1px em volta.

    As bordas ocupam a margem do próprio widget; o espaçamento interno é do layout de quem usa.
    """

    def __init__(self, bg: str | None = None, border: str = "", tone: str = "divider", parent=None):
        super().__init__(parent)
        self._bg = bg
        self._tone = tone
        self._edges = {"t": 0, "b": 0, "l": 0, "r": 0}
        self.set_border(border)

    def set_bg(self, bg: str | None) -> None:
        self._bg = bg
        self.update()

    def set_border(self, border: str) -> None:
        self._edges = {"t": 0, "b": 0, "l": 0, "r": 0}
        for part in border.split():
            width = int(part[1:])
            for side in ("tblr" if part[0] == "a" else part[0]):
                self._edges[side] = width
        e = self._edges
        self.setContentsMargins(e["l"], e["t"], e["r"], e["b"])
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        w, h = self.width(), self.height()
        if self._bg:
            p.fillRect(self.rect(), theme.color(self._bg))
        line = theme.color(self._tone)
        e = self._edges
        if e["t"]:
            p.fillRect(0, 0, w, e["t"], line)
        if e["b"]:
            p.fillRect(0, h - e["b"], w, e["b"], line)
        if e["l"]:
            p.fillRect(0, 0, e["l"], h, line)
        if e["r"]:
            p.fillRect(w - e["r"], 0, e["r"], h, line)


class Icon(QWidget):
    """Ícone Lucide na cor de um token do tema."""

    def __init__(self, name: str, size: int = 16, tone: str = "text", alpha: float = 1.0, stroke: float = 2.0, parent=None):
        super().__init__(parent)
        self._name, self._tone, self._alpha, self._stroke = name, tone, alpha, stroke
        self.setFixedSize(size, size)

    def set_icon(self, name: str, tone: str | None = None, alpha: float | None = None) -> None:
        self._name = name
        if tone:
            self._tone = tone
        if alpha is not None:
            self._alpha = alpha
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme.draw_icon(p, self._name, QRectF(self.rect()), theme.color(self._tone, self._alpha), self._stroke)


class Text(QWidget):
    """Texto na Archivo e na cor de um token. Uma linha corta com «…»; `wrap` quebra em várias."""

    def __init__(
        self,
        text: str = "",
        px: float = 14,
        weight: int = 400,
        tone: str = "text",
        alpha: float = 1.0,
        wrap: bool = False,
        upper: bool = False,
        spacing: float = 0.0,
        align=Qt.AlignmentFlag.AlignLeft,
        parent=None,
    ):
        super().__init__(parent)
        self._text, self._tone, self._alpha = text, tone, alpha
        self._wrap, self._upper, self._align = wrap, upper, align
        self._font = theme.font(px, weight, spacing)
        if wrap:
            policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            policy.setHeightForWidth(True)
            self.setSizePolicy(policy)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def text(self) -> str:
        return self._text

    def set_text(self, text: str, tone: str | None = None, weight: int | None = None, alpha: float | None = None) -> None:
        self._text = text
        if tone:
            self._tone = tone
        if alpha is not None:
            self._alpha = alpha
        if weight is not None:
            self._font.setWeight(QFont.Weight(weight))
        self.updateGeometry()
        self.update()

    def _shown(self) -> str:
        return self._text.upper() if self._upper else self._text

    def _metrics(self) -> QFontMetrics:
        return QFontMetrics(self._font)

    def sizeHint(self) -> QSize:
        metrics = self._metrics()
        if self._wrap:
            return QSize(200, self.heightForWidth(200))
        return QSize(metrics.horizontalAdvance(self._shown()), metrics.height() + 2)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self._metrics().height() + 2)

    def hasHeightForWidth(self) -> bool:
        return self._wrap

    def heightForWidth(self, width: int) -> int:
        return len(wrap_lines(self._shown(), self._font, width, 99)) * self._metrics().lineSpacing() + 2

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setFont(self._font)
        p.setPen(theme.color(self._tone, self._alpha))
        text, metrics = self._shown(), self._metrics()
        if self._wrap:
            for index, line in enumerate(wrap_lines(text, self._font, self.width(), 99)):
                y = index * metrics.lineSpacing()
                p.drawText(QRectF(0, y, self.width(), metrics.lineSpacing()), self._align | Qt.AlignmentFlag.AlignVCenter, line)
            return
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, self.width())
        p.drawText(self.rect(), self._align | Qt.AlignmentFlag.AlignVCenter, elided)


class Button(QAbstractButton):
    """Botão plano nos quatro estilos do design: primary, secondary, ghost e icon (+ text, seg, map, pill)."""

    PAD = {"primary": 14, "secondary": 14, "ghost": 10, "text": 10, "seg": 12, "map": 16, "pill": 12, "icon": 0}

    def __init__(
        self,
        text: str = "",
        kind: str = "secondary",
        icon: str | None = None,
        trailing: str | None = None,
        size: int | tuple | None = None,
        icon_size: int = 15,
        pad_v: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.kind = kind
        self.setText(text)
        self.icon_name, self.icon_size = icon, icon_size
        self.trailing = trailing  # "arrow", "chevron", "chip:Pause" ou "text:9"
        self.fg = None  # token de cor do texto/ícone, quando o fundo de quem hospeda não é o comum
        self.active = False  # destaque forçado (som tocando) no estilo accent
        self.danger = False  # hover vermelho (remover)
        self.problem = False  # kind "pill" em alerta
        self.open = False  # janela que o botão abre está aberta: contorno text e fundo 7%
        self.badge_on = False  # selo "count:N" em accent (com conteúdo) ou apagado
        self.alpha = 1.0
        self._ring = False
        self._pad_v = pad_v if pad_v is not None else {"seg": 7, "map": 9, "pill": 7}.get(kind, 8)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        if kind == "icon":
            self.setFixedSize(*(size if isinstance(size, tuple) else (size or 32, size or 32)))
        else:  # encolhe (e corta o texto com «…») em vez de vazar quando falta espaço
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setCheckable(kind in ("seg", "map"))

    # ---- medidas e fonte
    def _font(self):
        if self.kind == "seg":
            return theme.font(13, 400)
        if self.kind == "map":
            return theme.font(14, 800 if self.isChecked() else 400)
        if self.kind == "pill":
            return theme.font(13, 600)
        return theme.font(14, 800)

    def _trailing_width(self) -> int:
        if not self.trailing:
            return 0
        if self.trailing == "chevron":
            return 6 + 14
        if self.trailing == "arrow":
            return 8 + 16
        kind, _, value = self.trailing.partition(":")
        fnt = theme.font(11 if kind == "chip" else 12, 600 if kind == "chip" else 800 if kind == "count" else 400)
        if kind == "count":
            return 8 + max(20, QFontMetrics(fnt).horizontalAdvance(value) + 12)
        return 8 + QFontMetrics(fnt).horizontalAdvance(value) + (12 if kind == "chip" else 0)

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self._font())
        pad = self.PAD[self.kind]
        width = 2 * pad
        if self.icon_name:
            width += self.icon_size + (6 if self.text() else 0)
        width += metrics.horizontalAdvance(self.text()) + self._trailing_width()
        return QSize(width, metrics.height() + 2 * self._pad_v + 2)

    def minimumSizeHint(self) -> QSize:
        return QSize(self.sizeHint().height(), self.sizeHint().height())

    # ---- cores
    def _paint_colors(self):
        kind, hover, down = self.kind, self.underMouse(), self.isDown()
        text, bg_tone = theme.color("text"), theme.color("bg")
        fill, fg, border = None, text, None
        if kind == "primary" or self.active:
            fill = theme.color("accent_700" if down else "accent_600" if hover else "accent")
            fg = bg_tone
        elif kind == "pill":
            if self.problem:
                fill, fg, border = theme.color("accent"), bg_tone, theme.color("accent")
            else:
                border = theme.color("divider")
            if hover and not self.problem:
                fill = theme.color("text", 0.07)
        elif kind == "ghost":
            fg = theme.color("accent")
            fill = theme.color("accent", 0.18 if down else 0.10) if hover or down else None
        elif kind == "seg" and self.isChecked():
            fill, fg = theme.color("accent"), bg_tone
        elif kind == "map" and self.isChecked():
            fill, fg = theme.color("accent_100"), theme.color("accent_800")
        elif self.danger and hover:
            fill, fg = theme.color("accent_100"), theme.color("accent_800")
        elif hover or down:
            fill = theme.color("text", 0.14 if down else 0.07 if kind != "icon" else 0.08)
            if kind == "map":
                fill = theme.color("text", 0.06)
        if kind == "secondary":
            border = theme.color("divider")
            if self.open:
                fill, border = theme.color("text", 0.07), theme.color("text")
        if self.fg and not self.active:
            fg = theme.color(self.fg)
        return fill, fg, border

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(theme.DISABLED_OPACITY)
        elif self.alpha < 1.0:
            p.setOpacity(self.alpha)
        fill, fg, border = self._paint_colors()
        w, h = self.width(), self.height()
        if fill is not None:
            p.fillRect(self.rect(), fill)
        if border is not None:
            p.setPen(border)
            p.drawRect(QRectF(0.5, 0.5, w - 1, h - 1))
        pad = self.PAD[self.kind]
        left, right = pad, w - pad
        fnt = self._font()
        metrics = QFontMetrics(fnt)
        icon_box = self.icon_size if self.kind != "icon" else min(18, self.icon_size + 3)

        if self.kind == "icon":
            size = self.icon_size
            theme.draw_icon(p, self.icon_name, QRectF((w - size) / 2, (h - size) / 2, size, size), fg, 2.0)
        else:
            if self.icon_name:
                theme.draw_icon(p, self.icon_name, QRectF(left, (h - icon_box) / 2, icon_box, icon_box), fg, 2.0)
                left += icon_box + (6 if self.text() else 0)
            right -= self._draw_trailing(p, fg, right, h)
            p.setFont(fnt)
            p.setPen(fg)
            room = max(0, right - left)
            shown = metrics.elidedText(self.text(), Qt.TextElideMode.ElideRight, room)
            p.drawText(QRectF(left, 0, room + 1, h), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, shown)
        if self._ring:
            p.setOpacity(1.0)
            p.setPen(theme.color("accent"))
            pen = p.pen()
            pen.setWidth(2)
            p.setPen(pen)
            p.drawRect(QRectF(3, 3, w - 6, h - 6))

    def _draw_trailing(self, p, fg, right: int, h: int) -> int:
        if not self.trailing:
            return 0
        if self.trailing in ("arrow", "chevron"):
            size = 16 if self.trailing == "arrow" else 14
            theme.draw_icon(p, self.trailing, QRectF(right - size, (h - size) / 2, size, size), fg, 2.0)
            return self._trailing_width()
        kind, _, value = self.trailing.partition(":")
        fnt = theme.font(11 if kind == "chip" else 12, 600 if kind == "chip" else 800 if kind == "count" else 400)
        width = QFontMetrics(fnt).horizontalAdvance(value)
        p.setFont(fnt)
        if kind == "count":
            box = QRectF(right - max(20, width + 12), (h - 20) / 2, max(20, width + 12), 20)
            p.fillRect(box, theme.color("accent") if self.badge_on else theme.color("text", 0.12))
            p.setPen(theme.color("bg") if self.badge_on else theme.color("text"))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, value)
        elif kind == "chip":
            box = QRectF(right - width - 12, (h - 20) / 2, width + 12, 20)
            border = theme.color("bg", 0.6)
            p.setPen(border)
            p.drawRect(box.adjusted(0.5, 0.5, -0.5, -0.5))
            p.setPen(fg)
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, value)
        else:
            tinted = theme.color("text", 0.7) if fg == theme.color("text") else fg
            p.setPen(tinted)
            p.drawText(QRectF(right - width, 0, width, h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, value)
        return self._trailing_width()

    # ---- foco por teclado: anel só quando veio do teclado
    def focusInEvent(self, event) -> None:
        self._ring = event.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        )
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._ring = False
        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
        else:
            super().keyPressEvent(event)

    def popup(self, menu) -> None:
        """Abre o menu logo abaixo do botão."""
        menu.exec(self.mapToGlobal(QPoint(0, self.height())))


class Check(QAbstractButton):
    """Caixa de seleção quadrada (accent quando marcada)."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._ring = False

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(theme.font(14, 600))
        return QSize(16 + (8 + metrics.horizontalAdvance(self.text()) if self.text() else 0), 24)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(theme.DISABLED_OPACITY)
        box = QRectF(0, (self.height() - 16) / 2, 16, 16)
        if self.isChecked():
            p.fillRect(box, theme.color("accent"))
            theme.draw_icon(p, "check", box.adjusted(2, 2, -2, -2), theme.color("bg"), 3.0)
        else:
            p.fillRect(box, theme.color("bg"))
            p.setPen(theme.color("divider"))
            p.drawRect(box.adjusted(0.5, 0.5, -0.5, -0.5))
        if self.text():
            p.setFont(theme.font(14, 600))
            p.setPen(theme.color("text"))
            p.drawText(QRectF(24, 0, self.width() - 24, self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())
        if self._ring:
            pen = p.pen()
            pen.setColor(theme.color("accent"))
            pen.setWidth(2)
            p.setPen(pen)
            p.drawRect(QRectF(-1, 1, self.width() + 1, self.height() - 2))

    def focusInEvent(self, event) -> None:
        self._ring = event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._ring = False
        super().focusOutEvent(event)


class Chip(QWidget):
    """A tecla dentro de um quadradinho de 1px (ou accent cheio, enquanto grava)."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._text, self.listening = text, False
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_text(self, text: str, listening: bool = False) -> None:
        self._text, self.listening = text, listening
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(theme.font(12, 800))
        return QSize(metrics.horizontalAdvance(self._text) + 16, metrics.height() + 6)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        box = QRectF(self.rect())
        if self.listening:
            p.fillRect(box, theme.color("accent"))
        p.setPen(theme.color("accent" if self.listening else "divider"))
        p.drawRect(box.adjusted(0.5, 0.5, -0.5, -0.5))
        p.setFont(theme.font(12, 800))
        p.setPen(theme.color("bg" if self.listening else "text", 1.0 if self._text != "—" else 0.6))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, self._text)


class Select(QComboBox):
    """Seletor do design: o QSS cuida da caixa, aqui só entra a seta e o popup largo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(12)
        self.setMaxVisibleItems(12)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(theme.DISABLED_OPACITY)
        theme.draw_icon(p, "chevron", QRectF(self.width() - 24, (self.height() - 14) / 2, 14, 14), theme.color("text"))

    def showPopup(self) -> None:
        metrics = QFontMetrics(self.font())
        widest = max((metrics.horizontalAdvance(self.itemText(i)) for i in range(self.count())), default=0)
        self.view().setMinimumWidth(max(self.width(), widest + 40))  # nome inteiro à vista, mesmo comprido
        super().showPopup()


def cells(*widgets, divider: str = "r2") -> Box:
    """Células iguais num bloco de contorno 2px, divididas por régua de 2px."""
    outer = Box(border="a2")
    layout = hbox(outer)
    for index, widget in enumerate(widgets):
        layout.addWidget(widget, 1)
        if isinstance(widget, Box):
            widget.set_border(divider if index < len(widgets) - 1 else "")
    return outer
