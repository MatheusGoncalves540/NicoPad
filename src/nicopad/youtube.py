"""Download de áudio do YouTube: lógica fora da tela, no mesmo espírito de cable.py."""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlparse


def has_ffmpeg() -> str | None:
    """Caminho do ffmpeg, ou None quando não está instalado (o yt-dlp precisa dele para o mp3)."""
    return shutil.which("ffmpeg")


def check_url(url: str) -> str | None:
    """Motivo da recusa, ou None quando a URL é aceita.

    Limite de confiança: só http(s). O yt-dlp aceitaria um caminho do disco (file:// ou um
    caminho local) e viraria "download" de um arquivo que já está na máquina.
    """
    url = (url or "").strip()
    if not url:
        return "Cole a URL do vídeo."
    if urlparse(url).scheme.lower() not in ("http", "https"):
        return "Só URLs http:// ou https:// são aceitas."
    return None


def download(url: str, folder, on_progress=None) -> Path:
    """Baixa o áudio do vídeo como mp3 em `folder`. Devolve o caminho do arquivo.

    Erro de rede ou vídeo indisponível sobe como exceção; nada é engolido aqui, quem
    chama mostra a mensagem.
    """
    import yt_dlp  # importado aqui: o app abre sem a dependência instalada

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    def hook(status):
        if not on_progress:
            return
        if status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            done = status.get("downloaded_bytes") or 0
            on_progress(done / total if total else 0.0, "Baixando…")
        elif status.get("status") == "finished":
            on_progress(1.0, "Convertendo para mp3…")

    options = {
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        "paths": {"home": str(folder)},
        "outtmpl": "%(title).80s.%(ext)s",
        "noplaylist": True,
        "progress_hooks": [hook],
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
    # PONYTAIL: o caminho final (já .mp3) sai de requested_downloads[0]["filepath"]; o
    # info["filepath"] de nível raiz não existe nesta versão do yt-dlp. Testado de ponta a
    # ponta contra um vídeo real; se uma versão futura mudar isso, ajustar aqui.
    requested = (info.get("requested_downloads") or [{}])[0] if isinstance(info, dict) else {}
    path = requested.get("filepath") or (info.get("filepath") if isinstance(info, dict) else None)
    if not path or not Path(path).is_file():
        raise ValueError("o download terminou mas o arquivo final não foi encontrado")
    return Path(path)
