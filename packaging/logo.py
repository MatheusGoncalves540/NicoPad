"""Desenha a logo do nicoPad: packaging/nicopad.png e packaging/nicopad.ico.

Desenho em Python puro (sem PIL): um quadrado de cantos arredondados com três
barras de nível dentro — som. Rode `task logo` (ou `python packaging/logo.py`)
depois de mexer aqui; os dois arquivos são gravados nesta pasta e vão embutidos
no executável (ícone do .exe e logo da janela).
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent

BACK = (13, 27, 42)  # fundo escuro
BAR = (56, 189, 248)  # barras em azul
RADIUS = 0.22  # arredondamento do quadrado (fração do lado)
BAR_WIDTH = 0.14
BARS = ((0.26, 0.40), (0.50, 0.66), (0.74, 0.50))  # (centro em x, altura) de cada barra
SIZES = (16, 32, 48, 64, 128, 256)


def _rounded(u: float, v: float, x0: float, y0: float, x1: float, y1: float, radius: float) -> bool:
    """Ponto dentro de um retângulo de cantos arredondados (coordenadas de 0 a 1)."""
    if not (x0 <= u <= x1 and y0 <= v <= y1):
        return False
    near_x = min(max(u, x0 + radius), x1 - radius)
    near_y = min(max(v, y0 + radius), y1 - radius)
    return (u - near_x) ** 2 + (v - near_y) ** 2 <= radius * radius


def _in_bars(u: float, v: float) -> bool:
    half = BAR_WIDTH / 2
    for center, height in BARS:
        bottom, top = 0.5 - height / 2, 0.5 + height / 2
        if _rounded(u, v, center - half, bottom, center + half, top, half):
            return True
    return False


def _rows(size: int) -> list:
    """Linhas RGBA da logo, com superamostragem para as bordas ficarem lisas."""
    step = 4 if size <= 64 else 2
    big = size * step
    cover = [[0] * size for _ in range(size)]  # subamostras dentro do quadrado
    inside = [[0] * size for _ in range(size)]  # subamostras dentro das barras
    for source_y in range(big):
        v = (source_y + 0.5) / big
        for source_x in range(big):
            u = (source_x + 0.5) / big
            if not _rounded(u, v, 0.0, 0.0, 1.0, 1.0, RADIUS):
                continue
            x, y = source_x // step, source_y // step
            cover[y][x] += 1
            if _in_bars(u, v):
                inside[y][x] += 1
    total = step * step
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            alpha = cover[y][x]
            if not alpha:
                row += b"\x00\x00\x00\x00"
                continue
            bar = inside[y][x] / alpha
            row += bytes(
                [round(BAR[channel] * bar + BACK[channel] * (1 - bar)) for channel in range(3)]
                + [round(255 * alpha / total)]
            )
        rows.append(bytes(row))
    return rows


def png(size: int, rows: list) -> bytes:
    """PNG RGBA (8 bits por canal, sem compressão de linha extra)."""
    raw = b"".join(b"\x00" + row for row in rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def ico(images: dict) -> bytes:
    """ICO com cada tamanho guardado como PNG (o Windows aceita desde o Vista)."""
    offset = 6 + 16 * len(images)
    directory = b""
    payload = b""
    for size, data in sorted(images.items()):
        directory += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)
    return struct.pack("<HHH", 0, 1, len(images)) + directory + payload


def main() -> int:
    images = {size: png(size, _rows(size)) for size in SIZES}
    (HERE / "nicopad.png").write_bytes(images[128])
    (HERE / "nicopad.ico").write_bytes(ico(images))
    print(f"logo pronta: nicopad.png ({images[128].__len__()} bytes, 128px) e nicopad.ico em {HERE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
