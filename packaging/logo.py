"""Gera a logo do nicoPad a partir de packaging/logo.jpeg: tira o fundo e faz o .png dos dois temas e o .ico.

A arte é branca sobre preto, então o brilho de cada pixel vira transparência (o fundo sai e as
bordas continuam suaves) e o traço recebe a cor do tema. `task logo` roda este arquivo.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packaging"
SOURCE = OUT / "logo.jpeg"

SIZE = 512
MARGIN = 0.05  # respiro em volta da arte (fração do lado da imagem)
CUT = 16  # abaixo disto é o fundo preto do JPEG (que nunca sai preto exato)
SPAN = 220  # a faixa de brilho que vira transparência: o traço branco chega opaco
EDGE = 40  # acima disto já é traço (usado só para recortar a arte)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
# Token de theme.py: o traço acompanha o fundo em que a logo é desenhada.
INK = {"claro": (0x18, 0x16, 0x15), "escuro": (0xF3, 0xF2, 0xF2)}
FILES = {"claro": "nicopad.png", "escuro": "nicopad-branco.png"}


def _alpha() -> Image.Image:
    """A arte como transparência: o fundo preto do JPEG vira 0 e o traço branco vira 255."""
    table = [0 if value <= CUT else min(255, (value - CUT) * 255 // SPAN) for value in range(256)]
    with Image.open(SOURCE) as source:
        return source.convert("L").point(table)


def logo(ink: tuple) -> Image.Image:
    """A arte centralizada num quadrado transparente, colorida com a tinta e pronta para o app."""
    alpha = _alpha()
    box = alpha.point([0 if value <= EDGE else 255 for value in range(256)]).getbbox()
    if box is None:
        raise SystemExit(f"{SOURCE.name} não tem traço visível")
    art = alpha.crop(box)
    side = round(max(art.size) * (1 + 2 * MARGIN))
    canvas = Image.new("L", (side, side), 0)
    canvas.paste(art, ((side - art.width) // 2, (side - art.height) // 2))
    canvas = canvas.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    image = Image.new("RGBA", (SIZE, SIZE), (*ink, 255))
    image.putalpha(canvas)
    return image


def main() -> None:
    images = {}
    for theme, name in FILES.items():
        images[theme] = logo(INK[theme])
        images[theme].save(OUT / name)
        print(f"{name}: {SIZE}x{SIZE}, fundo transparente")
    # O .ico do .exe e do instalador usa o traço escuro (o Windows Explorer é claro por padrão).
    images["claro"].save(OUT / "nicopad.ico", sizes=[(size, size) for size in ICO_SIZES])
    print(f"nicopad.ico: {', '.join(str(size) for size in ICO_SIZES)} px")


if __name__ == "__main__":
    main()
