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
    from nicopad.config import is_first_run, load
    from nicopad.ui import run

    first_run = is_first_run()
    settings, warning = load()
    return run(settings, warning, first_run)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback

        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, "Falha ao iniciar:\n\n" + traceback.format_exc(), "nicoPad", 0x10)
        except Exception:
            pass  # sem Windows ou sem janela: o traceback abaixo ainda sai
        raise
