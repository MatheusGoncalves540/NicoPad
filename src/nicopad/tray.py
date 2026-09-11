"""Ícone na bandeja do sistema (Windows e Linux).

Fechar a janela não precisa encerrar o programa: os atalhos globais e o áudio não
dependem dela. O ícone na bandeja é a porta de volta (e também o jeito de encerrar
o app). O pystray cuida do ícone em cada sistema; sem ele o app avisa na barra de
status e volta a fechar de verdade.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path


def _image(path: Path | None):
    """A imagem do ícone; sem a logo, um quadrado escuro (melhor que ícone quebrado)."""
    from PIL import Image

    if path is not None and path.is_file():
        with Image.open(path) as logo:
            return logo.copy()  # fecha o arquivo: a bandeja só precisa das amostras
    return Image.new("RGBA", (64, 64), (40, 40, 40, 255))


class Tray:
    """O ícone da bandeja, com «Abrir o nicoPad» e «Sair»."""

    def __init__(self, logo: Path | None, on_open, on_quit):
        self.error = None
        self._logo = logo
        self._on_open = on_open
        self._on_quit = on_quit
        self._icon = None

    @property
    def ok(self) -> bool:
        """True depois que o ícone apareceu de verdade: antes disso não há para onde voltar."""
        return self._icon is not None

    def start(self) -> bool:
        """Põe o ícone na bandeja; devolve False (com o motivo em `error`) se não der."""
        if sys.platform.startswith("linux"):
            # No Linux só o backend X11 convive com o laço do Tk na thread principal
            # (os de GTK exigem a thread principal só para si). Wayland atende pelo
            # XWayland; sem X11 a bandeja não existe e o app avisa.
            os.environ.setdefault("PYSTRAY_BACKEND", "xorg")
        try:
            import pystray

            icon = pystray.Icon(
                "nicopad",
                _image(self._logo),
                "nicoPad",
                pystray.Menu(
                    pystray.MenuItem("Abrir o nicoPad", self._open, default=True),
                    pystray.MenuItem("Sair", self._quit),
                ),
            )
        except Exception as exc:
            self.error = f"bandeja do sistema indisponível ({exc})"
            return False

        def loop() -> None:
            try:
                icon.run(setup=self._ready)
            except Exception as exc:  # o backend falhou depois de o app já estar aberto
                self.error = f"bandeja do sistema indisponível ({exc})"

        # Thread própria e daemon: o laço do Tk fica com a thread principal, e nada
        # aqui pode impedir o programa de fechar.
        threading.Thread(target=loop, name="nicopad-tray", daemon=True).start()
        return True

    def stop(self) -> None:
        """Tira o ícone da bandeja."""
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass  # fechando o programa: um erro aqui não pode segurar a saída

    def notify(self, message: str) -> None:
        """Recado da bandeja, quando o sistema souber mostrar (o Linux não mostra)."""
        if self._icon is None:
            return
        try:
            self._icon.notify(message)
        except Exception:
            pass

    def _ready(self, icon) -> None:
        """O backend chamou: agora sim existe ícone na bandeja."""
        self._icon = icon
        icon.visible = True  # com setup próprio, quem mostra o ícone é o setup

    def _open(self, *_args) -> None:
        self._on_open()

    def _quit(self, *_args) -> None:
        self._on_quit()
