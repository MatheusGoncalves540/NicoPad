"""Tema do nicoPad: tokens de cor, fonte Archivo, ícones Lucide e a folha de estilos (QSS).

Os widgets pintados à mão (botões, pads, linhas, forma de onda) leem as cores daqui na hora
de pintar; trocar de tema é `apply(app, nome)` e repintar. Nada de `border-radius`.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtSvg import QSvgRenderer

FAMILY = "Archivo"

THEMES = {
    "claro": {
        "bg": "#f3f2f2", "surface": "#eae9e9", "text": "#201e1d", "divider": ("#201e1d", 0.40),
        "accent": "#ec3013", "accent_100": "#fff2ef", "accent_600": "#dd2b0f",
        "accent_700": "#ae1800", "accent_800": "#7c1405", "neutral_900": "#2d2b2b",
    },
    "escuro": {
        "bg": "#181615", "surface": "#242221", "text": "#f3f2f2", "divider": ("#f3f2f2", 0.32),
        "accent": "#ff563c", "accent_100": "#4d170e", "accent_600": "#ff9783",
        "accent_700": "#ffc4b8", "accent_800": "#ffe0d9", "neutral_900": "#2d2b2b",
    },
}
LOGO_TILE = "#ffffff"  # a logo tem fundo branco: o quadrado branco vale nos dois temas
DISABLED_OPACITY = 0.45

_state = {"name": "claro"}


def name() -> str:
    return _state["name"]


def color(token: str, alpha: float | None = None) -> QColor:
    """Cor do token no tema atual; `alpha` troca a opacidade (mistura sobre o fundo)."""
    value = THEMES[_state["name"]][token]
    base, own = value if isinstance(value, tuple) else (value, 1.0)
    result = QColor(base)
    result.setAlphaF(own if alpha is None else alpha)
    return result


def css(value: QColor) -> str:
    return f"rgba({value.red()},{value.green()},{value.blue()},{value.alphaF():.3f})"


def system_theme() -> str:
    scheme = QGuiApplication.styleHints().colorScheme()
    return "escuro" if scheme == Qt.ColorScheme.Dark else "claro"


def font(px: float, weight: int = 400, spacing: float = 0.0) -> QFont:
    """Archivo no tamanho (px) e peso pedidos. `spacing` em px entre as letras."""
    result = QFont(FAMILY)
    result.setPixelSize(round(px))
    result.setWeight(QFont.Weight(weight))
    if spacing:
        result.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return result


def load_fonts(path) -> bool:
    """Embute a Archivo (variável: cobre 400/600/800). Sem ela o app avisa em vez de cair em outra."""
    return bool(path) and QFontDatabase.addApplicationFont(str(path)) >= 0


# --------------------------------------------------------------------------- ícones

# Lucide (ISC), 24x24, traço 2. Só o miolo do <svg>; play e stop são preenchidos.
_ICONS = {
    "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "stop": '<rect x="5" y="5" width="14" height="14"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "settings": '<path d="M20 7h-9"/><path d="M14 17H5"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/>',
    "scissors": '<circle cx="6" cy="6" r="3"/><path d="M8.12 8.12 12 12"/><path d="M20 4 8.12 15.88"/>'
    '<circle cx="6" cy="18" r="3"/><path d="M14.8 14.8 20 20"/>',
    "keyboard": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M6 8h.01"/><path d="M10 8h.01"/>'
    '<path d="M14 8h.01"/><path d="M18 8h.01"/><path d="M8 12h.01"/><path d="M12 12h.01"/>'
    '<path d="M16 12h.01"/><path d="M7 16h10"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>'
    '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "grid": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>'
    '<rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
    "list": '<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/><path d="M8 12h13"/>'
    '<path d="M8 18h13"/><path d="M8 6h13"/>',
    "help": '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    "mic": '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/>'
    '<path d="M12 19v3"/>',
    "headphones": '<path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1'
    'a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
    '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/>'
    '<path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/>'
    '<path d="m19.07 4.93-1.41 1.41"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
    "plug": '<path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z"/>',
    "arrow": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "refresh": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>'
    '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "repeat": '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/>'
    '<path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    "minus": '<path d="M5 12h14"/>',
    "volume": '<path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>',
}
_FILLED = {"play", "stop"}
_renderers: dict = {}


def _renderer(icon: str, tint: QColor, stroke: float) -> QSvgRenderer:
    key = (icon, tint.name(), round(tint.alphaF(), 2), stroke)
    found = _renderers.get(key)
    if found is None:
        paint = f'stroke="{tint.name()}" stroke-opacity="{tint.alphaF():.2f}"'
        fill = f'fill="{tint.name()}" fill-opacity="{tint.alphaF():.2f}"' if icon in _FILLED else 'fill="none"'
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" {fill} {paint} '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{_ICONS[icon]}</svg>'
        )
        found = _renderers[key] = QSvgRenderer(QByteArray(svg.encode()))
    return found


def draw_icon(painter, icon: str, rect: QRectF, tint: QColor, stroke: float = 2.0) -> None:
    _renderer(icon, tint, stroke).render(painter, QRectF(rect))


# ------------------------------------------------------------------------------ QSS

_QSS = """
* {{ font-family: "{family}"; font-size: 14px; color: {text}; outline: 0; }}
QMainWindow, QStackedWidget, QScrollArea {{ background: {bg}; border: 0; }}
QDialog {{ background: {surface}; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QLineEdit {{ background: {surface}; border: 1px solid {divider}; border-radius: 0; min-height: 34px;
  padding: 0 10px; selection-background-color: {accent_100}; selection-color: {accent_800}; }}
QLineEdit:focus {{ border-color: {accent}; }}
QLineEdit:disabled {{ color: {muted}; }}
QLineEdit[inDialog="true"] {{ background: {bg}; }}
QLineEdit[bare="true"] {{ background: transparent; border: 0; min-height: 0; padding: 0; }}

QComboBox {{ combobox-popup: 0; background: {surface}; border: 1px solid {divider}; border-radius: 0;
  min-height: 34px; padding: 0 34px 0 10px; }}
QComboBox:focus {{ border-color: {accent}; }}
QComboBox:disabled {{ color: {muted}; }}
QComboBox::drop-down {{ border: 0; width: 28px; }}
QComboBox::down-arrow {{ image: none; }}
QComboBox QAbstractItemView {{ background: {surface}; border: 1px solid {divider}; outline: 0;
  selection-background-color: {accent_100}; selection-color: {accent_800}; }}
QComboBox QAbstractItemView::item {{ min-height: 32px; padding-left: 10px; }}
QComboBox QAbstractItemView::item:hover {{ background: {accent_100}; color: {accent_800}; }}

QSlider {{ min-height: 20px; }}
QSlider::groove:horizontal {{ height: 4px; background: {track}; }}
QSlider::sub-page:horizontal {{ background: {accent}; }}
QSlider::handle:horizontal {{ width: 12px; height: 18px; margin: -7px 0; background: {accent}; border-radius: 0; }}
QSlider::handle:horizontal:hover {{ background: {accent_600}; }}
QSlider::sub-page:horizontal:disabled {{ background: {muted}; }}
QSlider::handle:horizontal:disabled {{ background: {muted}; }}

QProgressBar {{ border: 0; border-radius: 0; background: {track}; max-height: 6px; min-height: 6px; text-align: left; }}
QProgressBar::chunk {{ background: {accent}; }}

QMenu {{ background: {surface}; border: 1px solid {divider}; padding: 4px 0; }}
QMenu::item {{ padding: 8px 16px; background: transparent; }}
QMenu::item:selected {{ background: {accent_100}; color: {accent_800}; }}
QMenu::item:disabled {{ color: {muted}; }}
QMenu::separator {{ height: 1px; background: {divider}; margin: 4px 0; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {divider}; min-height: 32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {divider}; min-width: 32px; }}
QToolTip {{ background: {text}; color: {bg}; border: 0; padding: 6px 8px; font-size: 12px; }}
"""


def build_qss() -> str:
    text = color("text")
    values = {
        "family": FAMILY,
        "muted": css(color("text", 0.60)),
        "track": css(color("text", 0.12)),
    }
    for token in THEMES[_state["name"]]:
        values[token] = css(color(token))
    values["text"] = css(text)
    return _QSS.format(**values)


def apply(app, theme: str) -> None:
    """Põe o tema no app inteiro: estilo Fusion + paleta + QSS. Quem pinta à mão repinta sozinho."""
    _state["name"] = theme if theme in THEMES else "claro"
    app.setStyle("Fusion")
    palette = QPalette()
    for role, token in (
        (QPalette.ColorRole.Window, "bg"),
        (QPalette.ColorRole.Base, "bg"),
        (QPalette.ColorRole.Button, "bg"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.ToolTipBase, "text"),
        (QPalette.ColorRole.ToolTipText, "bg"),
        (QPalette.ColorRole.Highlight, "accent"),
        (QPalette.ColorRole.HighlightedText, "bg"),
    ):
        palette.setColor(role, color(token))
    app.setPalette(palette)
    app.setFont(font(14))
    app.setStyleSheet(build_qss())
