"""Interface do nicoPad: lista de sons, teclas e roteamento de áudio."""

from __future__ import annotations

import base64
import queue
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import sounddevice as sd

from nicopad import cable, config as cfg, library, profile, tray
from nicopad.audio import (
    AudioEngine,
    find_device,
    guess_cable,
    is_virtual_cable,
    list_devices,
    load_sound,
    visible_devices,
)
from nicopad.hotkeys import KeyboardHook, key_name

AUDIO_TYPES = [
    ("Áudio", "*.wav *.mp3 *.ogg *.oga *.opus *.flac *.aiff *.aif"),
    ("Todos os arquivos", "*.*"),
]
CABLE_URL = "https://vb-audio.com/Cable/"
ESC = 0x1B
COMBO = "<<ComboboxSelected>>"
ESC_KEY = "<Escape>"
WINDOW_SIZE = "920x560"
WINDOW_MIN = (700, 440)


def _percent(value) -> str:
    return f"{float(value) * 100:.0f}%"


def _shorten(text, limit: int = 52) -> str:
    """Texto comprido demais para a linha: mostra o começo e o fim."""
    text = str(text)
    if len(text) <= limit:
        return text
    half = max(8, limit // 2 - 1)
    return f"{text[:half]}…{text[-half:]}"


def _asset(name: str) -> Path | None:
    """Arte do app (logo): embutida no .exe ou na pasta packaging, rodando do fonte."""
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / name)
    candidates.append(Path(__file__).resolve().parents[2] / "packaging" / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _logo(window) -> tk.PhotoImage | None:
    """A logo da janela, lida dos bytes (o caminho do projeto pode ter acentos)."""
    path = _asset("nicopad.png")
    if path is None:
        return None
    try:
        return tk.PhotoImage(master=window, data=base64.b64encode(path.read_bytes()))
    except Exception:
        return None  # sem logo o app funciona: não vale quebrar a janela por isso


def _window_size(saved: str) -> str:
    """Tamanho salvo da janela. A posição fica a cargo do Windows, que conhece a tela."""
    width, separator, height = (saved or "").lower().partition("+")[0].partition("x")
    if separator and width.isdigit() and height.isdigit():
        return f"{max(WINDOW_MIN[0], int(width))}x{max(WINDOW_MIN[1], int(height))}"
    return WINDOW_SIZE


def _center_on(window, parent) -> None:
    """Centraliza um diálogo sobre a janela principal."""
    window.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - window.winfo_width()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - window.winfo_height()) // 2
    window.geometry(f"+{max(0, x)}+{max(0, y)}")

HELP = """O microfone dos outros jogadores precisa de um cabo de áudio virtual (driver VB-Cable).

1. Clique em "Preparar instalador do cabo" (aqui embaixo, ou no menu Configurações). O nicoPad
   coloca o pacote oficial do
   VB-Cable na sua pasta e abre ela com o instalador já selecionado.

2. Clique com o botão direito em VBCABLE_Setup_x64.exe e escolha
   "Executar como administrador". Depois REINICIE o PC.

3. Volte aqui, clique em "Atualizar" e escolha
   CABLE Input (VB-Audio Virtual Cable).

4. Marque "Misturar meu microfone" e escolha seu microfone de verdade, senão
   sua voz deixa de sair junto com os sons.

5. No Discord/jogo, troque o microfone de entrada para
   CABLE Output (VB-Audio Virtual Cable).

O nicoPad não instala o driver sozinho: a licença do VB-Cable permite difundir o
pacote original, mas não integrá-lo ao instalador de outro programa.

VB-Cable é donationware de Vincent Burel (www.vb-cable.com). Se for útil para
você, considere participar do projeto."""


def _key(path) -> str:
    """Caminho normalizado, igual ao que é gravado na configuração."""
    return str(Path(path))


def _default(devices: list, index: int):
    for device in devices:
        if device.index == index:
            return device
    return None


def _device_dict(device) -> dict:
    return {"name": device.name, "hostapi": device.hostapi} if device else {}


class NicoPadApp(tk.Tk):
    def __init__(self, settings, warning: str | None = None):
        super().__init__()
        self.settings = settings
        self.engine = AudioEngine()
        self.hook = KeyboardHook(self._on_hotkey)
        self.sounds = {}
        self.outputs = []
        self.inputs = []
        self.cables = []
        self.output_choices = []
        self.keymap = {}
        self.pending = None
        self.message = None
        self.events = queue.Queue()
        self.ready = False
        self.closing = False
        self._save_job = None
        self._flash_job = None
        self.load_warning = warning
        self.save_error = None
        self.last_folder = ""
        self.search_var = tk.StringVar()
        self.typing = False  # campo de texto em foco: as teclas não tocam sons

        # A bandeja é a porta de volta quando a janela fecha: sem ela, fechar fecha mesmo.
        self.tray = tray.Tray(_asset("nicopad.png"), self._tray_open, self._tray_quit)

        self.title("nicoPad")
        self.minsize(*WINDOW_MIN)
        self.geometry(_window_size(self.settings.geometry))
        self._build()
        self._sync_library()
        self._reload_devices()
        self._load_bindings()
        self._restore_devices()
        self._sync_toggles()
        self.hook.start()
        self.ready = True
        self.restart_engine()
        self.tray.start()
        self.after(60, self._pump)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------- interface

    def _quiet_while_typing(self, entry) -> None:
        """Enquanto o usuário digita neste campo, as teclas de atalho ficam quietas."""
        entry.bind("<FocusIn>", lambda _event: setattr(self, "typing", True))
        entry.bind("<FocusOut>", lambda _event: setattr(self, "typing", False))


    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        bar = ttk.Frame(self, padding=(10, 8, 10, 0))
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(2, weight=1)
        logo = _logo(self)
        if logo is not None:
            self._logo = logo  # o Tk não mantém a imagem viva sozinho
            self._bar_logo = logo.subsample(4)  # a barra usa 32px; a arte cheia fica no ícone
            ttk.Label(bar, image=self._bar_logo).grid(row=0, column=0, padx=(0, 6))
            self.iconphoto(True, logo)
        ttk.Label(bar, text="nicoPad", font=("", 12, "bold")).grid(row=0, column=1, sticky="w")

        profiles_menu = tk.Menu(bar, tearoff=False)
        profiles_menu.add_command(label="Exportar perfil…", command=self._export_profile)
        profiles_menu.add_command(label="Importar perfil…", command=self._import_profile)
        profiles = ttk.Menubutton(bar, text="Perfis")
        profiles["menu"] = profiles_menu
        profiles.grid(row=0, column=3, padx=(6, 0))

        self.library_var = tk.BooleanVar(value=bool(self.settings.library_enabled))
        self.settings_menu = tk.Menu(bar, tearoff=False)
        self.settings_menu.add_checkbutton(
            label="Guardar cópia dos sons", variable=self.library_var, command=self._toggle_library
        )
        self.settings_menu.add_command(label="Escolher a pasta dos sons…", command=self._choose_library)
        self.settings_menu.add_command(label="Abrir a pasta dos sons", command=self._open_library)
        self.settings_menu.add_separator()
        self.settings_menu.add_command(label="Preparar instalador do cabo de áudio", command=self._prepare_cable)
        self.settings_menu.add_command(label="Abrir site do VB-Cable", command=lambda: webbrowser.open(CABLE_URL))
        options = ttk.Menubutton(bar, text="Configurações")
        options["menu"] = self.settings_menu
        options.grid(row=0, column=4, padx=(6, 0))

        ttk.Button(bar, text="?", width=3, command=self._show_help).grid(row=0, column=5, padx=(6, 0))

        audio = ttk.LabelFrame(self, text="Áudio", padding=(10, 6))
        audio.grid(row=1, column=0, sticky="ew", padx=10, pady=(6, 6))
        audio.columnconfigure(1, weight=1)

        ttk.Label(audio, text="Tocar no mic (saída)").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.output_box = ttk.Combobox(audio, state="readonly")
        self.output_box.grid(row=0, column=1, sticky="ew")
        self.output_box.bind(COMBO, lambda _event: self.restart_engine())
        ttk.Button(audio, text="Atualizar", width=10, command=self._reload_devices).grid(row=0, column=2, padx=(6, 0))

        self.monitor_var = tk.BooleanVar(value=bool(self.settings.monitor_enabled))
        ttk.Checkbutton(
            audio,
            text="Ouvir os sons também no meu fone",
            variable=self.monitor_var,
            command=self._sync_toggles,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.monitor_box = ttk.Combobox(audio, state="readonly")
        self.monitor_box.grid(row=1, column=1, sticky="ew", pady=(6, 0))
        self.monitor_box.bind(COMBO, lambda _event: self.restart_engine())

        self.mic_var = tk.BooleanVar(value=bool(self.settings.mic_enabled))
        ttk.Checkbutton(
            audio,
            text="Misturar meu microfone",
            variable=self.mic_var,
            command=self._sync_toggles,
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.mic_box = ttk.Combobox(audio, state="readonly")
        self.mic_box.grid(row=2, column=1, sticky="ew", pady=(6, 0))
        self.mic_box.bind(COMBO, lambda _event: self.restart_engine())

        volume = ttk.Frame(audio)
        volume.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        volume.columnconfigure(1, weight=1)
        ttk.Label(volume, text="Volume").grid(row=0, column=0, padx=(0, 8))
        self.volume_label = tk.StringVar(value=_percent(self.settings.volume))
        self.volume_var = tk.DoubleVar(value=float(self.settings.volume))
        ttk.Scale(volume, from_=0.0, to=1.0, variable=self.volume_var, command=self._on_volume).grid(
            row=0, column=1, sticky="ew"
        )
        ttk.Label(volume, textvariable=self.volume_label, width=5, anchor="e").grid(row=0, column=2, padx=(8, 0))

        sounds = ttk.LabelFrame(self, text="Sons", padding=(10, 6))
        sounds.grid(row=2, column=0, sticky="nsew", padx=10)
        sounds.columnconfigure(0, weight=1)
        sounds.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(sounds)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        for text, command in (
            ("Adicionar som", self._add_sounds),
            ("Configurar som", self._sound_dialog),
            ("Definir tecla", self._start_binding),
            ("Ouvir", self._preview),
            ("Parar tudo", self._stop_all),
            ("Remover", self._remove_selected),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=(0, 6))

        search = ttk.Frame(sounds)
        search.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text="Buscar").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.search_entry = ttk.Entry(search, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=1, sticky="ew")
        self._quiet_while_typing(self.search_entry)
        self.search_entry.bind(ESC_KEY, lambda _event: self.search_var.set(""))
        self.search_var.trace_add("write", self._on_search)

        self.tree = ttk.Treeview(
            sounds, columns=("key", "name", "monitor", "file"), show="headings", selectmode="browse"
        )
        for column, title, width, stretch in (
            ("key", "Tecla", 110, False),
            ("name", "Som", 210, False),
            ("monitor", "No fone", 80, False),
            ("file", "Arquivo", 360, True),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, minwidth=70, stretch=stretch, anchor="w")
        self.tree.grid(row=2, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(sounds, orient="vertical", command=self.tree.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda _event: self._sound_dialog())
        self.tree.bind("<Return>", lambda _event: self._preview())
        self.tree.bind("<Delete>", lambda _event: self._remove_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._update_status())

        status = ttk.Frame(self, padding=(10, 6, 10, 8))
        status.grid(row=3, column=0, sticky="ew")
        status.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar()
        ttk.Label(status, textvariable=self.status_var, anchor="w").grid(row=0, column=0, sticky="ew")
        self.warning_var = tk.StringVar()
        self.warning_label = ttk.Label(
            status, textvariable=self.warning_var, anchor="w", foreground="#b00020", justify="left", wraplength=880
        )
        self.warning_label.grid(row=1, column=0, sticky="ew")
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event) -> None:
        if event.widget is self:
            self.warning_label.configure(wraplength=max(240, event.width - 40))

    # ------------------------------------------------------------------ ajustes

    def _reload_devices(self) -> None:
        self.outputs = visible_devices(list_devices("output"))
        self.inputs = visible_devices(list_devices("input"))
        # Para os outros escutarem, a saída tem de ser um cabo virtual. Com um cabo
        # instalado só cabos aparecem na lista; sem nenhum, aparecem todos, senão
        # você não conseguiria testar nada.
        self.cables = [device for device in self.outputs if is_virtual_cable(device)]
        self.output_choices = self.cables or self.outputs
        self.output_box["values"] = [device.label for device in self.output_choices]
        self.monitor_box["values"] = [device.label for device in self.outputs]
        self.mic_box["values"] = [device.label for device in self.inputs]
        default_input, default_output = sd.default.device[0], sd.default.device[1]
        if not self.output_box.get() and self.output_choices:
            preferred = guess_cable(self.output_choices) or _default(self.output_choices, default_output)
            self.output_box.set((preferred or self.output_choices[0]).label)
        if not self.monitor_box.get():
            fallback = _default(self.outputs, default_output)
            if fallback is not None:
                self.monitor_box.set(fallback.label)
        if not self.mic_box.get():
            fallback = _default(self.inputs, default_input)
            if fallback is not None:
                self.mic_box.set(fallback.label)
        self.restart_engine()

    def _restore_devices(self) -> None:
        for box, devices, saved in (
            (self.output_box, self.output_choices, self.settings.output),
            (self.monitor_box, self.outputs, self.settings.monitor),
            (self.mic_box, self.inputs, self.settings.microphone),
        ):
            saved = saved or {}
            device = find_device(devices, saved.get("name", ""), saved.get("hostapi", ""))
            if device is not None:
                box.set(device.label)

    def _sync_toggles(self) -> None:
        self.monitor_box.configure(state="readonly" if self.monitor_var.get() else "disabled")
        self.mic_box.configure(state="readonly" if self.mic_var.get() else "disabled")
        self.restart_engine()

    def _device_from(self, box, devices):
        label = box.get().strip()
        for device in devices:
            if device.label == label:
                return device
        return None

    def restart_engine(self) -> None:
        """Reabre os streams com o que está marcado na tela e salva a configuração."""
        if not self.ready:
            return
        self.message = None
        output = self._device_from(self.output_box, self.output_choices)
        monitor = self._device_from(self.monitor_box, self.outputs) if self.monitor_var.get() else None
        microphone = self._device_from(self.mic_box, self.inputs) if self.mic_var.get() else None
        self.settings.output = _device_dict(output)
        self.settings.monitor = _device_dict(self._device_from(self.monitor_box, self.outputs))
        self.settings.monitor_enabled = bool(self.monitor_var.get())
        self.settings.microphone = _device_dict(self._device_from(self.mic_box, self.inputs))
        self.settings.mic_enabled = bool(self.mic_var.get())
        self.engine.start(
            output,
            monitor=monitor,
            microphone=microphone,
            volume=self.settings.volume,
            sounds=self.sounds.values(),
        )
        self._update_status()
        self._save_later()

    def _on_volume(self, value) -> None:
        volume = max(0.0, min(1.0, float(value)))
        self.settings.volume = volume
        self.volume_label.set(_percent(volume))
        self.engine.set_volume(volume)
        self._save_later()

    # --------------------------------------------------------------------- sons

    def _load_bindings(self) -> None:
        for binding in self.settings.bindings:
            if binding.vk and binding.key.startswith("VK "):
                # Nome gravado por uma versão antiga, quando o Windows não sabia a tecla.
                binding.key = key_name(binding.vk, 0, binding.extended)
            try:
                self.sounds[_key(binding.path)] = load_sound(
                    binding.path,
                    name=binding.name,
                    gain=binding.gain,
                    monitor=binding.monitor,
                    monitor_gain=binding.monitor_gain,
                )
            except Exception:
                pass  # a linha já aparece marcada como «arquivo não encontrado»
        self._rebuild_keymap()
        self._refresh_rows()

    def _sounds_folder(self) -> str:
        """Reabre o diálogo onde você estava, e não em Documentos."""
        for folder in (self.last_folder, *(str(Path(b.path).parent) for b in self.settings.bindings)):
            if folder and Path(folder).is_dir():
                return folder
        return ""

    def _add_sounds(self) -> None:
        folder = self._sounds_folder()
        options = {"initialdir": folder} if folder else {}
        paths = filedialog.askopenfilenames(title="Escolha os sons", filetypes=AUDIO_TYPES, **options)
        if paths:
            self.last_folder = str(Path(paths[0]).parent)
        added = sum(1 for path in paths if self._add_sound(path))
        if not added:
            return
        self.engine.prepare(self.sounds.values())
        self._refresh_rows(select=len(self.settings.bindings) - 1)
        self._save()
        self._flash(f"{added} som(ns) adicionado(s) — agora clique em «Definir tecla».")

    def _add_sound(self, path) -> bool:
        path = _key(path)
        if self._duplicate(path):
            return False
        try:
            sound = load_sound(path)
        except Exception as exc:
            messagebox.showerror("nicoPad", f"Não consegui abrir «{Path(path).name}».\n\n{exc}")
            return False
        if self.library_var.get():
            try:
                path = _key(library.copy_in(path, self._library_folder()))
            except OSError as exc:
                messagebox.showerror("nicoPad", f"Não consegui guardar a cópia de «{Path(path).name}».\n\n{exc}")
                return False
            if self._duplicate(path):
                return False
            sound.path = path
        self.sounds[path] = sound
        self.settings.bindings.append(cfg.Binding(path=path, name=sound.name))
        return True

    def _duplicate(self, path) -> bool:
        return path in self.sounds or any(_key(binding.path) == path for binding in self.settings.bindings)

    def _remove_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            self._flash("Escolha um som na lista para remover.")
            return
        binding = self.settings.bindings[index]
        own_copy = library.inside(binding.path, self._library_folder())
        if own_copy and not messagebox.askokcancel(
            "nicoPad",
            f"Remover «{binding.name}» e apagar o arquivo da pasta dos sons?\n\n{binding.path}",
            default=messagebox.CANCEL,
        ):
            return
        self.settings.bindings.pop(index)
        self.sounds.pop(_key(binding.path), None)
        self._rebuild_keymap()
        self._refresh_rows(select=min(index, len(self.settings.bindings) - 1))
        self._save()
        if own_copy:
            try:
                Path(binding.path).unlink()
            except OSError as exc:
                self._flash(f"«{binding.name}» saiu da lista, mas não consegui apagar o arquivo: {exc}")
                return
        self._flash(f"«{binding.name}» saiu da lista.")

    def _preview(self) -> None:
        index = self._selected_index()
        if index is None:
            self._flash("Escolha um som na lista para ouvir.")
            return
        binding = self.settings.bindings[index]
        sound = self.sounds.get(_key(binding.path))
        if sound is None:
            self._flash(f"Arquivo não encontrado: {binding.path}")
            return
        self.engine.preview(sound)

    def _stop_all(self) -> None:
        self.engine.stop_all()
        self._flash("Sons interrompidos.")

    def _start_binding(self) -> None:
        index = self._selected_index()
        if index is None:
            self._flash("Escolha um som na lista antes de definir a tecla.")
            return
        self.pending = index
        self._update_status()

    def _apply_binding(self, event) -> None:
        index, self.pending = self.pending, None
        vk, extended, name = event
        if vk == ESC:
            self._flash("Nenhuma tecla foi definida.")
            return
        binding = self.settings.bindings[index]
        replaced = None
        for other in self.settings.bindings:
            if other is not binding and other.vk == vk and other.extended == extended:
                other.vk, other.extended, other.key = 0, False, ""
                replaced = other.name
        binding.vk, binding.extended, binding.key = vk, extended, name
        self._rebuild_keymap()
        self._refresh_rows(select=index)
        self._save()
        self._flash(f"«{binding.name}» agora toca com {name}." + (f"  (a tecla saiu de «{replaced}»)" if replaced else ""))

    def _rebuild_keymap(self) -> None:
        self.keymap = {(b.vk, b.extended): b for b in self.settings.bindings if b.vk}

    def _matches(self, binding) -> bool:
        """A busca aceita várias palavras: todas precisam aparecer no som."""
        query = self.search_var.get().strip().casefold()
        if not query:
            return True
        text = f"{binding.name} {binding.key} {binding.path}".casefold()
        return all(word in text for word in query.split())

    def _refresh_rows(self, select=None) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, binding in enumerate(self.settings.bindings):
            if not self._matches(binding):
                continue
            name = binding.name
            if _key(binding.path) not in self.sounds:
                name += "   (arquivo não encontrado)"
            monitor = _percent(binding.monitor_gain) if binding.monitor else "—"
            self.tree.insert(
                "", "end", iid=str(index), values=(binding.key or "—", name, monitor, binding.path)
            )
        if select is not None and self.tree.exists(str(select)):
            self.tree.selection_set(str(select))
            self.tree.focus(str(select))

    def _selected_index(self):
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    # -------------------------------------------------------------- executado já

    def _on_hotkey(self, vk: int, extended: bool, name: str) -> None:
        """Roda na thread do hook: nada de Tk aqui, só o essencial."""
        if self.typing:
            return  # o usuário está digitando: a tecla é dele

        if self.pending is not None:
            self.events.put(("bind", (vk, extended, name)))
            return
        binding = self.keymap.get((vk, extended))
        if binding is None:
            return
        sound = self.sounds.get(_key(binding.path))
        if sound is not None:
            self.engine.trigger(sound)

    def _pump(self) -> None:
        if self.closing:
            return
        try:
            while not self.closing:
                kind, payload = self.events.get_nowait()
                if kind == "bind":
                    self._apply_binding(payload)
                elif kind == "open":
                    self._show()
                elif kind == "quit":
                    self._quit()
        except queue.Empty:
            pass
        if not self.closing:
            self.after(60, self._pump)

    # ------------------------------------------------------------------- estado

    def _flash(self, text: str, seconds: float = 6.0) -> None:
        """Recado passageiro na barra de status: some sozinho."""
        self.message = text
        self._update_status()
        if self._flash_job is not None:
            self.after_cancel(self._flash_job)
        self._flash_job = self.after(int(seconds * 1000), self._clear_message)

    def _clear_message(self) -> None:
        self._flash_job = None
        self.message = None
        self._update_status()

    def _update_status(self) -> None:
        if self.pending is not None and self.pending < len(self.settings.bindings):
            name = self.settings.bindings[self.pending].name
            self.status_var.set(f"Pressione a tecla que vai tocar «{name}»   (Esc cancela)")
        else:
            self.status_var.set(self.message or self.engine.status)
        self.warning_var.set("    ".join(self._warnings()))

    def _warnings(self) -> list:
        """Avisos que ficam na tela: só somem quando a causa some."""
        messages = [
            text
            for text in (
                self.load_warning,
                self.hook.error,
                self.save_error,
                self.engine.error,
                self.tray.error,
            )
            if text
        ]
        missing = sum(1 for binding in self.settings.bindings if _key(binding.path) not in self.sounds)
        if missing:
            messages.append(f"{missing} arquivo(s) de som não encontrado(s).")
        messages.extend(self.engine.warnings)
        output = self._device_from(self.output_box, self.output_choices)
        if not self.outputs:
            messages.append("Nenhum dispositivo de saída encontrado.")
        elif output is None:
            messages.append("Escolha a saída de áudio.")
        elif not is_virtual_cable(output):
            if self.cables:
                messages.append(
                    "A saída escolhida é seu alto-falante/fone: o som não chega no microfone dos outros. "
                    "Use o botão «?», no canto superior direito."
                )
            else:
                messages.append(
                    "Nenhum cabo de áudio virtual encontrado: sem ele os outros jogadores não "
                    "escutam os sons. Use o botão «?», no canto superior direito."
                )
        if output is not None and is_virtual_cable(output) and not self.mic_var.get():
            messages.append(
                "Saída no cabo virtual sem o microfone misturado: sua voz não sai junto. "
                "Marque «Misturar meu microfone»."
            )
        if self.mic_var.get() and output is not None and output.index == sd.default.device[1]:
            messages.append("Misturar o microfone direto na saída padrão causa microfonia.")
        return messages

    def _save(self) -> None:
        self._save_job = None
        self.save_error = cfg.save(self.settings)
        if self.save_error:
            self._update_status()

    def _save_later(self) -> None:
        if self._save_job is not None:
            self.after_cancel(self._save_job)
        self._save_job = self.after(400, self._save)

    def _show_help(self) -> None:
        window = tk.Toplevel(self)
        window.title("Como configurar")
        window.transient(self)
        window.resizable(False, False)
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=HELP, justify="left").pack(anchor="w")
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Preparar instalador do cabo", command=self._prepare_cable).pack(side="left")

        ttk.Button(buttons, text="Abrir site do VB-Cable", command=lambda: webbrowser.open(CABLE_URL)).pack(side="left")
        ttk.Button(buttons, text="Fechar", command=window.destroy).pack(side="right")
        window.bind(ESC_KEY, lambda _event: window.destroy())
        _center_on(window, self)
        window.grab_set()

    def _prepare_cable(self) -> None:
        """Entrega o pacote oficial do cabo e abre a pasta (é o que a licença permite)."""
        try:
            setup, folder = cable.prepare()
        except Exception as exc:
            messagebox.showerror("nicoPad", f"Não consegui preparar o instalador do cabo.\n\n{exc}")
            return
        try:
            cable.reveal(setup)
        except OSError:
            pass  # se a pasta não abrir, o caminho continua visível na barra de status
        self._flash(f"Execute {setup.name} como administrador e reinicie o PC.   ({folder})", seconds=20)

    # ------------------------------------------------------ configuração do som

    def _sound_dialog(self) -> None:
        """Ajustes do som individual: volume no mic, no fone e se toca no fone."""
        index = self._selected_index()
        if index is None:
            self._flash("Escolha um som na lista para configurar.")
            return
        binding = self.settings.bindings[index]
        sound = self.sounds.get(_key(binding.path))
        if sound is None:
            self._flash(f"Arquivo não encontrado: {binding.path}")
            return

        window = tk.Toplevel(self)
        window.title("Configurar som")
        window.transient(self)
        window.resizable(False, False)
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        name_var = tk.StringVar(value=binding.name)
        name_entry = ttk.Entry(frame, textvariable=name_var)
        name_entry.grid(row=0, column=0, columnspan=3, sticky="ew")
        name_entry.focus_set()
        name_entry.select_range(0, "end")
        name_entry.bind("<Return>", lambda _event: close())  # Enter confirma o nome
        self._quiet_while_typing(name_entry)
        ttk.Label(frame, text=_shorten(binding.path, 70), foreground="#555555").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(2, 10)
        )

        mic_text = tk.StringVar(value=_percent(binding.gain))
        monitor_text = tk.StringVar(value=_percent(binding.monitor_gain))
        monitor_var = tk.BooleanVar(value=bool(binding.monitor))
        monitor_scale = ttk.Scale(
            frame,
            from_=0.0,
            to=1.0,
            length=240,
            variable=tk.DoubleVar(value=binding.monitor_gain),
            command=lambda value: set_monitor(value),
        )

        def set_mic(value) -> None:
            binding.gain = max(0.0, min(1.0, float(value)))
            sound.gain = binding.gain
            mic_text.set(_percent(binding.gain))
            self._save_later()

        def set_monitor(value) -> None:
            binding.monitor_gain = max(0.0, min(1.0, float(value)))
            sound.monitor_gain = binding.monitor_gain
            monitor_text.set(_percent(binding.monitor_gain))
            self._save_later()

        def toggle_monitor() -> None:
            binding.monitor = monitor_var.get()
            sound.monitor = binding.monitor
            monitor_scale.configure(state="normal" if binding.monitor else "disabled")
            self._save_later()

        def close() -> None:
            self.typing = False  # a janela sai de foco: os atalhos voltam
            self._rename(binding, name_var.get())
            self._refresh_rows(select=index)
            window.destroy()

        def bind_key() -> None:
            close()
            self.pending = index
            self._update_status()

        ttk.Label(frame, text="Volume no microfone").grid(row=2, column=0, sticky="w", padx=(0, 8))
        ttk.Scale(
            frame,
            from_=0.0,
            to=1.0,
            length=240,
            variable=tk.DoubleVar(value=binding.gain),
            command=set_mic,
        ).grid(row=2, column=1, sticky="ew")
        ttk.Label(frame, textvariable=mic_text, width=5, anchor="e").grid(row=2, column=2, padx=(8, 0))

        ttk.Checkbutton(frame, text="Tocar também no meu fone", variable=monitor_var, command=toggle_monitor).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(10, 6)
        )
        ttk.Label(frame, text="Volume no meu fone").grid(row=4, column=0, sticky="w", padx=(0, 8))
        monitor_scale.grid(row=4, column=1, sticky="ew")
        monitor_scale.configure(state="normal" if binding.monitor else "disabled")
        ttk.Label(frame, textvariable=monitor_text, width=5, anchor="e").grid(row=4, column=2, padx=(8, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Button(buttons, text="Ouvir", command=lambda: self.engine.preview(sound)).pack(side="left")
        ttk.Button(buttons, text="Definir tecla", command=bind_key).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Fechar", command=close).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", close)
        window.bind(ESC_KEY, lambda _event: close())
        _center_on(window, self)
        window.grab_set()

    def _rename(self, binding, name: str) -> None:
        """Novo nome do som; o arquivo da pasta própria é renomeado junto."""
        name = name.strip()
        if not name or name == binding.name:
            return
        path = Path(binding.path)
        sound = self.sounds.pop(_key(path), None)
        if library.inside(path, self._library_folder()):
            target = library.rename_in(path, name)
            if target is None:
                self.sounds[_key(path)] = sound  # nada mudou: o som continua onde estava
                self._flash("Não consegui renomear o arquivo; o nome não mudou.")
                return
            binding.path = _key(target)
        binding.name = name
        if sound is not None:
            sound.path = binding.path
            sound.name = name
            self.sounds[binding.path] = sound
        self._save()
        self._flash(f"Som renomeado para «{name}».")


    # ---------------------------------------------------------- pasta dos sons

    def _library_folder(self) -> str:
        return self.settings.library or str(library.default_folder())

    def _sync_library(self) -> None:
        # O próprio item do menu diz em que pasta as cópias vão ficar.
        label = "Guardar cópia dos sons"
        if self.library_var.get():
            label = f"{label} em {_shorten(self._library_folder(), 44)}"
        self.settings_menu.entryconfigure(0, label=label)

    def _toggle_library(self) -> None:
        self.settings.library_enabled = bool(self.library_var.get())
        self._save()
        if self.settings.library_enabled:
            self._copy_into_library()
        else:
            self._flash("Sons novos não serão mais copiados; as cópias já feitas ficam onde estão.")

    def _choose_library(self) -> None:
        folder = filedialog.askdirectory(title="Pasta para guardar os sons", initialdir=self._library_folder())
        if not folder:
            return
        self.settings.library = _key(folder)
        self.settings.library_enabled = True
        self.library_var.set(True)
        self._sync_library()
        self._save()
        self._copy_into_library()

    def _open_library(self) -> None:
        folder = Path(self._library_folder())
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("nicoPad", f"Não consegui criar a pasta dos sons.\n\n{exc}")
            return
        library.reveal(folder)

    def _copy_into_library(self) -> None:
        """Leva para a pasta própria os sons que ainda apontam para o arquivo original."""
        folder = self._library_folder()
        pending = [b for b in self.settings.bindings if not library.inside(b.path, folder)]
        if not pending:
            self._flash(f"Todos os sons já estão em {_shorten(folder)}.")
            return
        if not messagebox.askyesno(
            "nicoPad",
            f"Copiar {len(pending)} som(ns) para\n{folder}?\n\n"
            "A lista passa a usar as cópias: mover ou apagar o arquivo original não quebra mais o som.",
        ):
            return
        copied = 0
        for binding in pending:
            try:
                target = _key(library.copy_in(binding.path, folder))
            except OSError:
                continue  # arquivo ausente ou pasta sem permissão: este fica como está
            sound = self.sounds.pop(_key(binding.path), None)
            binding.path = target
            if sound is not None:
                sound.path = target
                self.sounds[target] = sound
            copied += 1
        self._refresh_rows(select=self._selected_index())
        self._save()
        text = f"{copied} som(ns) copiado(s) para {_shorten(folder)}."
        if copied < len(pending):
            text += f"   ({len(pending) - copied} não copiado(s))"
        self._flash(text)

    # ------------------------------------------------------------------ perfis

    def _export_profile(self) -> None:
        if not self.settings.bindings:
            self._flash("Não há sons para exportar.")
            return
        path = filedialog.asksaveasfilename(
            title="Salvar perfil",
            defaultextension=".zip",
            initialfile="nicopad-perfil.zip",
            filetypes=[("Perfil do nicoPad", "*.zip")],
        )
        if not path:
            return
        try:
            count, missing = profile.export(self.settings, path)
        except Exception as exc:
            messagebox.showerror("nicoPad", f"Não consegui salvar o perfil.\n\n{exc}")
            return
        text = f"Perfil salvo com {count} som(ns): {Path(path).name}"
        if missing:
            text += f"   ({len(missing)} arquivo(s) não encontrado(s) ficaram de fora)"
        self._flash(text, seconds=20)

    def _import_profile(self) -> None:
        path = filedialog.askopenfilename(title="Escolher perfil", filetypes=[("Perfil do nicoPad", "*.zip")])
        if not path:
            return
        folder = filedialog.askdirectory(title="Onde guardar os sons do perfil", initialdir=str(Path(path).parent))
        if not folder:
            return
        try:
            settings, count, missing = profile.load(path, folder)
        except Exception as exc:
            messagebox.showerror("nicoPad", f"Não consegui ler o perfil.\n\n{exc}")
            return
        if not count:
            messagebox.showwarning("nicoPad", "O perfil não trouxe nenhum som.")
            return
        if not messagebox.askyesno(
            "nicoPad",
            f"Isto substitui os {len(self.settings.bindings)} som(ns), as teclas e as configurações "
            f"atuais pelos {count} som(ns) do perfil «{Path(path).name}».\n\nContinuar?",
        ):
            return
        self._apply_settings(settings)
        text = f"Perfil «{Path(path).name}» carregado: {count} som(ns)."
        if missing:
            text += f"   ({len(missing)} não vieram no perfil)"
        self._flash(text, seconds=20)

    def _apply_settings(self, settings) -> None:
        """Troca a configuração inteira (importar perfil) e reabre o que depende dela."""
        settings.geometry = self.settings.geometry  # o tamanho da janela é de quem importa
        self.settings = settings
        self.sounds = {}
        self.monitor_var.set(bool(settings.monitor_enabled))
        self.mic_var.set(bool(settings.mic_enabled))
        self.volume_var.set(float(settings.volume))
        self.library_var.set(bool(settings.library_enabled))
        self._sync_library()
        self._load_bindings()
        self._restore_devices()
        self._sync_toggles()

    # ------------------------------------------------------------------- busca

    def _on_search(self, *_args) -> None:
        self._refresh_rows(select=self._selected_index())


    # ------------------------------------------------------------------ bandeja

    def _on_close(self) -> None:
        """O X da janela: pergunta se é para encerrar o programa ou só ir para a bandeja."""
        if not self.tray.ok:
            self._quit()  # sem bandeja o programa não teria como voltar
            return
        answer = messagebox.askyesnocancel(
            "nicoPad",
            "Fechar o nicoPad ou deixá-lo na bandeja?\n\n"
            "Sim — vai para a bandeja e continua tocando os sons pelos atalhos.\n"
            "Não — o programa é encerrado.\n"
            "Cancelar — a janela continua aberta.",
        )
        if answer is None:  # Cancelar
            return
        if answer:
            self._hide()
        else:
            self._quit()

    def _hide(self) -> None:
        """Tira a janela da frente sem encerrar nada: o programa segue pelos atalhos."""
        self.withdraw()
        self.tray.notify("O nicoPad continua na bandeja.")

    def _show(self) -> None:
        """Traz a janela de volta (pedido da bandeja)."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def _tray_open(self) -> None:
        """Roda na thread da bandeja: quem mexe na janela é o Tk, no seu próprio laço."""
        self.events.put(("open", None))

    def _tray_quit(self) -> None:
        self.events.put(("quit", None))

    def _quit(self) -> None:
        self.closing = True
        self.tray.stop()
        for job in (self._save_job, self._flash_job):
            if job is not None:
                self.after_cancel(job)
        self.settings.geometry = f"{self.winfo_width()}x{self.winfo_height()}"
        self._save()
        self.hook.stop()
        self.engine.stop()
        self.destroy()
