"""Ponto de entrada do nicoPad."""

from __future__ import annotations

import sys


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if "--install-cable" in argv:
        from nicopad import cable

        setup, folder = cable.prepare()
        print(f"Pacote oficial do VB-Cable pronto em:\n  {folder}\n")
        print(f"1. Execute como administrador: {setup.name}")
        print("2. Reinicie o PC.")
        print("3. Volte ao nicoPad e clique em Atualizar.\n")
        print(cable.CREDIT)
        try:
            cable.reveal(setup)
        except OSError:
            pass  # a pasta pode não abrir; o caminho já foi mostrado acima
        return 0
    if "--selftest" in argv:
        from nicopad.selftest import run

        return run()
    _dpi_awareness()
    from nicopad.config import load
    from nicopad.ui import NicoPadApp

    settings, warning = load()
    NicoPadApp(settings, warning).mainloop()
    return 0


def _dpi_awareness() -> None:
    """Sem isso o Tk desenha borrado em telas com escala acima de 100%."""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback

        try:
            import tkinter
            from tkinter import messagebox

            root = tkinter.Tk()
            root.withdraw()
            messagebox.showerror("nicoPad", "Falha ao iniciar:\n\n" + traceback.format_exc())
            root.destroy()
        except Exception:
            pass
        raise
