"""Atalhos globais: hook de teclado de baixo nível do Windows, sem dependências.

O hook é global (funciona com o app minimizado ou atrás de um jogo) e não
consome a tecla: o programa em foco continua recebendo o pressionamento.
"""

from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_KEYUP = 0x0101
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
LLKHF_EXTENDED = 0x01

_NAME_CACHE = {}


# O GetKeyNameText do Windows não nomeia algumas teclas (medido no Windows 10/11:
# Shift direito e Tecla Windows esquerda); só essas entram na mão.
_VK_NAMES = {
    0xA1: "Shift direito",
    0x5B: "Tecla Windows esquerda",
}


class _KeyboardEvent(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]



if os.name == "nt":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _PROCEDURE = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    _user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _PROCEDURE, wintypes.HINSTANCE, wintypes.DWORD]
    _user32.SetWindowsHookExW.restype = wintypes.HHOOK
    _user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    _user32.CallNextHookEx.restype = ctypes.c_ssize_t
    _user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    _user32.GetKeyNameTextW.argtypes = [wintypes.LPARAM, wintypes.LPWSTR, ctypes.c_int]
else:  # pragma: no cover - o app é Windows; o resto só não quebra na importação
    _user32 = None
    _kernel32 = None
    _PROCEDURE = None


def key_name(vk: int, scan: int, extended: bool) -> str:
    """Nome legível da tecla, no idioma do Windows (ex.: 'A', 'F1', 'Ctrl')."""
    cache_key = (vk, scan, extended)
    name = _NAME_CACHE.get(cache_key)
    if name is not None:
        return name
    name = ""
    if _user32 is not None and scan:  # sem scan o Windows não sabe dizer o nome
        buffer = ctypes.create_unicode_buffer(64)
        lparam = (scan << 16) | ((1 << 24) if extended else 0)
        if _user32.GetKeyNameTextW(lparam, buffer, 64):
            name = buffer.value.strip()
    name = name or _VK_NAMES.get(vk) or f"VK 0x{vk:02X}"
    _NAME_CACHE[cache_key] = name
    return name


class KeyboardHook:
    """Chama handler(vk, extended, nome) a cada tecla nova, em qualquer lugar."""

    def __init__(self, handler):
        self.handler = handler
        self.error = None
        self._thread = None
        self._thread_id = None
        self._hook = None
        self._procedure = None
        self._pressed = set()
        self._ready = threading.Event()

    def start(self) -> None:
        if _user32 is None:
            self.error = "atalhos globais só funcionam no Windows"
            return
        if self._thread is not None:
            return
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="nicopad-hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(3)

    def stop(self) -> None:
        if _user32 is not None and self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(2)
        self._thread = None
        self._thread_id = None

    def _run(self) -> None:
        self._thread_id = _kernel32.GetCurrentThreadId()
        self._procedure = _PROCEDURE(self._on_event)  # mantém a referência viva
        self._hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._procedure, None, 0)
        if not self._hook:
            self.error = f"não consegui instalar o hook de teclado (erro {ctypes.get_last_error()})"
        self._ready.set()
        message = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(message))
            _user32.DispatchMessageW(ctypes.byref(message))
        if self._hook:
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def _on_event(self, code, wparam, lparam):
        try:
            if code == 0:
                event = ctypes.cast(lparam, ctypes.POINTER(_KeyboardEvent)).contents
                extended = bool(event.flags & LLKHF_EXTENDED)
                key = (int(event.vkCode), extended)
                if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if key not in self._pressed:  # segurar a tecla não repete o som
                        self._pressed.add(key)
                        self.handler(key[0], extended, key_name(key[0], int(event.scanCode), extended))
                elif wparam in (WM_KEYUP, WM_SYSKEYUP):
                    self._pressed.discard(key)
        except Exception:
            pass  # o hook nunca pode derrubar o teclado do sistema
        return _user32.CallNextHookEx(None, code, wparam, lparam)
