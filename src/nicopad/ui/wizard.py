"""Assistente de primeiro uso: cabo virtual, aparelhos, Discord e pronto (uma página da janela)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QStackedWidget, QWidget

from nicopad import theme
from nicopad.ui.widgets import Box, Button, Check, Icon, Select, Text, cells, hbox, vbox

STEPS = ("Cabo de áudio virtual", "Seus aparelhos", "No Discord ou no jogo", "Pronto")
TEST_SECONDS = 1.5


class LogoTile(QWidget):
    """A logo sempre sobre um quadrado branco, nos dois temas."""

    def __init__(self, size: int, logo: QPixmap | None, inset: int = 6):
        super().__init__()
        self.logo, self.inset = logo, inset
        self.setFixedSize(size, size)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), theme.LOGO_TILE)
        if self.logo is not None and not self.logo.isNull():
            inner = self.width() - 2 * self.inset
            scaled = self.logo.scaled(inner, inner, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled)


class StepRow(QWidget):
    """Uma linha da lista de passos do painel vermelho."""

    def __init__(self, number: str, label: str, last: bool):
        super().__init__()
        self.number, self.label, self.last = number, label, last
        self.state = "future"  # future | current | done
        self.setFixedHeight(46 + (2 if last else 0))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        w, h = self.width(), self.height()
        line = theme.color("bg", 0.45)
        p.fillRect(0, 0, w, 2, line)
        if self.last:
            p.fillRect(0, h - 2, w, 2, line)
        p.setOpacity(0.7 if self.state == "future" else 1.0)
        p.setFont(theme.font(15, 800 if self.state == "current" else 400))
        p.setPen(theme.color("bg"))
        body = QRectF(0, 2, w, 42)
        p.drawText(QRectF(0, 2, 40, 42), Qt.AlignmentFlag.AlignVCenter, self.number)
        p.drawText(QRectF(40, 2, w - 64, 42), Qt.AlignmentFlag.AlignVCenter, self.label)
        if self.state == "done":
            theme.draw_icon(p, "check", QRectF(w - 20, body.center().y() - 8, 16, 16), theme.color("bg"), 3.0)


class Wizard(QWidget):
    finished = Signal()

    def __init__(self, win, logo: QPixmap | None):
        super().__init__()
        self.win = win
        self.step = 1

        root = hbox(self)
        side = Box("accent")
        side.setFixedWidth(400)
        column = vbox(side, (32, 32, 32, 32), 24)
        column.addWidget(LogoTile(112, logo))
        column.addWidget(Text("Seus sons no microfone dos outros.", 38, 800, tone="bg", wrap=True, spacing=-0.76))
        column.addStretch(1)
        self.rows = []
        for number, label in enumerate(STEPS, 1):
            row = StepRow(f"{number:02d}", label, number == len(STEPS))
            self.rows.append(row)
            column.addWidget(row)
        root.addWidget(side)

        right = vbox()
        holder = QWidget()
        holder.setLayout(right)
        root.addWidget(holder, 1)
        self.stack = QStackedWidget()
        content = QWidget()
        outer = hbox(content, (48, 40, 48, 40))
        outer.addWidget(self.stack, 1)
        outer.addStretch(0)
        self.stack.setMaximumWidth(680)
        right.addWidget(content, 1)
        for build in (self._step_cable, self._step_devices, self._step_discord, self._step_ready):
            self.stack.addWidget(build())

        footer = Box(border="t2")
        line = hbox(footer, (48, 16, 48, 16), 8)
        self.back = Button("Voltar", "secondary")
        skip = Button("Pular", "ghost")
        self.next = Button("Continuar", "primary", trailing="arrow", pad_v=10)
        self.next.setMinimumWidth(180)
        self.back.clicked.connect(lambda: self.go(self.step - 1))
        skip.clicked.connect(self.finished)
        self.next.clicked.connect(self._next)
        for widget in (self.back, skip):
            line.addWidget(widget)
        line.addStretch(1)
        line.addWidget(self.next)
        right.addWidget(footer)
        self.go(1)

    # ---------------------------------------------------------------- páginas

    def _page(self, number: int, title: str):
        page = QWidget()
        layout = vbox(page, spacing=20)
        layout.addWidget(Text(f"PASSO {number} DE 4", 11, 600, tone="accent_700", spacing=0.88))
        layout.addWidget(Text(title, 32, 800, wrap=True))
        return page, layout

    def _step_cable(self) -> QWidget:
        page, layout = self._page(1, STEPS[0])
        layout.addWidget(
            Text(
                "Nenhum programa consegue «falar» direto dentro de um microfone: é preciso um cabo de áudio virtual, "
                "um dispositivo de áudio falso. Instale o VB-Cable uma vez e o nicoPad usa ele sozinho.",
                14, 400, wrap=True,
            )
        )
        self.found = Box("surface", "a2")
        found_row = hbox(self.found)
        tick = Box("text")
        tick.setFixedWidth(48)
        vbox(tick).addWidget(Icon("check", 20, tone="bg", stroke=3.0), 0, Qt.AlignmentFlag.AlignCenter)
        found_row.addWidget(tick)
        info = vbox(margins=(14, 12, 14, 12), spacing=2)
        info.addWidget(Text("Cabo encontrado", 14, 800))
        self.cable_name = Text("", 13, 400, alpha=0.7)
        info.addWidget(self.cable_name)
        found_row.addLayout(info, 1)
        layout.addWidget(self.found)

        self.missing = Box(border="a2")
        body = vbox(self.missing)
        banner = Box("accent_100")
        line = hbox(banner, (14, 10, 14, 10), 8)
        line.addWidget(Icon("alert", 18, tone="accent_800"))
        line.addWidget(Text("Nenhum cabo virtual neste PC", 14, 800, tone="accent_800"), 1)
        body.addWidget(banner)
        steps = vbox(margins=(14, 12, 14, 4), spacing=8)
        for number, text in (
            ("1", "Prepare o instalador oficial (vem dentro do app)."),
            ("2", "Execute VBCABLE_Setup_x64.exe como administrador e reinicie o PC."),
        ):
            row = hbox(spacing=10)
            number_label = Text(number, 14, 800, tone="accent")
            number_label.setFixedWidth(16)
            row.addWidget(number_label)
            row.addWidget(Text(text, 14, 400, wrap=True), 1)
            steps.addLayout(row)
        body.addLayout(steps)
        buttons = hbox(margins=(14, 8, 14, 14), spacing=8)
        prepare = Button("Preparar instalador do cabo", "primary", icon="plug")
        again = Button("Já instalei — procurar de novo", "secondary", icon="refresh")
        prepare.clicked.connect(self.win.prepare_cable)
        again.clicked.connect(self.win.reload_devices)
        buttons.addWidget(prepare)
        buttons.addWidget(again)
        buttons.addStretch(1)
        body.addLayout(buttons)
        layout.addWidget(self.missing)
        layout.addStretch(1)
        return page

    def _step_devices(self) -> QWidget:
        page, layout = self._page(2, STEPS[1])
        block = Box(border="a2")
        rows = vbox(block)
        self.output_box, self.monitor_box, self.mic_box = Select(), Select(), Select()
        self.mic_check, self.monitor_check = Check("Misturar meu microfone"), Check("Ouvir no meu fone")
        specs = (
            (Text("Tocar no mic", 14, 600), "saída — o cabo virtual", self.output_box),
            (self.mic_check, "sua voz sai junto", self.mic_box),
            (self.monitor_check, "você escuta o que toca", self.monitor_box),
        )
        for position, (title, note, select) in enumerate(specs):
            row = Box(border="b1" if position < len(specs) - 1 else "")
            line = hbox(row, (14, 14, 14, 14), 12)
            label = QWidget()
            label.setFixedWidth(200)
            stack = vbox(label, spacing=2)
            stack.addWidget(title)
            stack.addWidget(Text(note, 12, 400, alpha=0.6))
            line.addWidget(label)
            line.addWidget(select, 1)
            rows.addWidget(row)
        layout.addWidget(block)
        self.mic_warning = QWidget()
        warning = hbox(self.mic_warning, spacing=8)
        warning.addWidget(Icon("alert", 16, tone="accent_700"))
        warning.addWidget(
            Text("Sem o microfone misturado, sua voz para de sair junto com os sons.", 14, 600, tone="accent_700", wrap=True), 1
        )
        layout.addWidget(self.mic_warning)
        layout.addStretch(1)
        return page

    def _step_discord(self) -> QWidget:
        page, layout = self._page(3, STEPS[2])
        layout.addWidget(Text("Troque o microfone de entrada para:", 14, 400))
        box = Box(border="a2", tone="text")
        line = hbox(box, (16, 16, 16, 16), 12)
        line.addWidget(Icon("mic", 22))
        line.addWidget(Text("CABLE Output (VB-Audio Virtual Cable)", 22, 800, wrap=True), 1)
        layout.addWidget(box)
        layout.addWidget(Text("Toque um som de teste e confira no Discord se o indicador de voz acende.", 14, 400, wrap=True))
        self.test = Button("Tocar som de teste", "secondary", icon="play", icon_size=14)
        self.test.clicked.connect(self._test)
        self.tested = False
        row = hbox()
        row.addWidget(self.test)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _step_ready(self) -> QWidget:
        page, layout = self._page(4, STEPS[3])
        layout.addWidget(
            Text(
                "Adicione um som e dê uma tecla para ele. O atalho funciona com a janela minimizada ou atrás do jogo, "
                "e a tecla continua funcionando normalmente no jogo.",
                14, 400, wrap=True,
            )
        )
        blocks = []
        for icon, title, note in (
            ("plus", "Adicionar som", "ou baixar do YouTube"),
            ("keyboard", "Definir tecla", "aperte a tecla; Esc cancela"),
            ("stop", "Parar tudo", "tecla própria, sempre ativa"),
        ):
            block = Box("bg")
            column = vbox(block, (14, 14, 14, 14), 6)
            column.addWidget(Icon(icon, 20, tone="accent"))
            column.addWidget(Text(title, 14, 800, wrap=True))
            column.addWidget(Text(note, 12, 400, alpha=0.6, wrap=True))
            column.addStretch(1)
            blocks.append(block)
        layout.addWidget(cells(*blocks))
        layout.addStretch(1)
        return page

    # -------------------------------------------------------------- navegação

    def go(self, step: int) -> None:
        self.step = max(1, min(len(STEPS), step))
        self.stack.setCurrentIndex(self.step - 1)
        for number, row in enumerate(self.rows, 1):
            row.state = "current" if number == self.step else "done" if number < self.step else "future"
            row.update()
        self.back.setEnabled(self.step > 1)
        self.next.setText("Abrir o nicoPad" if self.step == len(STEPS) else "Continuar")
        self.next.setMinimumWidth(180)
        self.next.update()

    def _next(self) -> None:
        if self.step >= len(STEPS):
            self.finished.emit()
        else:
            self.go(self.step + 1)

    def refresh(self) -> None:
        """Mostra o passo 1 conforme o cabo existe ou não, e o aviso do passo 2."""
        cable = self.win.cable_device()
        self.found.setVisible(cable is not None)
        self.missing.setVisible(cable is None)
        if cable is not None:
            self.cable_name.set_text(cable.name)
        self.mic_warning.setVisible(not self.mic_check.isChecked())

    def _test(self) -> None:
        self.win.play_test_tone(TEST_SECONDS)
        self.tested = True
        self.test.active = True
        self.test.setText("Tocando…")
        self.test.update()
        QTimer.singleShot(int(TEST_SECONDS * 1000), self._test_done)

    def _test_done(self) -> None:
        self.test.active = False
        self.test.setText("Tocar de novo")
        self.test.update()
