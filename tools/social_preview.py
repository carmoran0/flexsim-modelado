#!/usr/bin/env python3
"""Genera docs/social-preview.png (1280x640) para la vista previa social del repositorio.

Uso: python tools/social_preview.py   (requiere Pillow)
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
W, H, K = 1280, 640, 2  # K = factor de supersampling
FUENTES = Path("C:/Windows/Fonts")

BG, PANEL = (15, 23, 42), (30, 41, 59)
TXT, SUB, ACENTO = (241, 245, 249), (148, 163, 184), (56, 189, 248)
NARANJA, VERDE, MURO = (251, 146, 60), (74, 222, 128), (203, 213, 225)


def fuente(nombre, tam):
    for n in (nombre, "arial.ttf"):
        try:
            return ImageFont.truetype(str(FUENTES / n), tam * K)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    img = Image.new("RGB", (W * K, H * K), BG)
    d = ImageDraw.Draw(img)
    s = lambda *v: [x * K for x in v]

    # Texto
    d.text(s(72, 170), "flexsim-modelado", font=fuente("segoeuib.ttf", 60), fill=TXT)
    d.rectangle(s(72, 262, 232, 268), fill=ACENTO)
    d.text(s(72, 296), "Construye, verifica y simula modelos", font=fuente("segoeui.ttf", 36), fill=SUB)
    d.text(s(72, 342), "FlexSim con scripts FlexScript", font=fuente("segoeui.ttf", 36), fill=SUB)
    d.text(s(72, 500), "Skill de Claude  ·  plugin  ·  en español", font=fuente("segoeui.ttf", 26), fill=ACENTO)
    d.text(s(72, 540), "FlexSimPy  ·  plano 2D  ·  muros A*", font=fuente("segoeui.ttf", 22), fill=SUB)

    # Plano de nave (derecha)
    x0, y0, x1, y1 = 660, 90, 1210, 550
    d.rounded_rectangle(s(x0, y0, x1, y1), radius=18 * K, fill=PANEL)
    nx0, ny0, nx1, ny1 = 690, 120, 1180, 520
    d.rectangle(s(nx0, ny0, nx1, ny1), outline=MURO, width=6 * K)
    # puertas (huecos en el muro)
    for (a, b, c, e) in [(nx0 - 4, 200, nx0 + 4, 250), (nx0 - 4, 380, nx0 + 4, 430), (nx1 - 4, 290, nx1 + 4, 340)]:
        d.rectangle(s(a, b, c, e), fill=PANEL)
    # muro interior con puerta
    d.line(s(900, ny0, 900, 300), fill=MURO, width=4 * K)
    d.line(s(900, 350, 900, ny1), fill=MURO, width=4 * K)
    # racks
    for i in range(4):
        y = 150 + i * 42
        d.rectangle(s(930, y, 1150, y + 26), fill=(51, 65, 85), outline=ACENTO, width=2 * K)
        for j in range(1, 6):
            d.line(s(930 + j * 36.6, y, 930 + j * 36.6, y + 26), fill=ACENTO, width=1 * K)
    # cinta transportadora
    d.rectangle(s(722, 316, 878, 336), fill=(51, 65, 85), outline=NARANJA, width=2 * K)
    for i in range(7):
        d.polygon(s(732 + i * 22, 319, 748 + i * 22, 326, 732 + i * 22, 333), fill=NARANJA)
    # palés / items
    for (px, py) in [(740, 300), (800, 340), (852, 300)]:
        d.rectangle(s(px, py, px + 18, py + 14), fill=VERDE)
    # recursos móviles y trayecto A*
    d.line(s(1040, 480, 960, 480, 960, 340, 910, 325), fill=SUB, width=2 * K)
    for (cx, cy, col) in [(1040, 480, NARANJA), (770, 460, VERDE), (1100, 420, VERDE)]:
        d.ellipse(s(cx - 11, cy - 11, cx + 11, cy + 11), fill=col)

    img = img.resize((W, H), Image.LANCZOS)
    destino = RAIZ / "docs" / "social-preview.png"
    destino.parent.mkdir(exist_ok=True)
    img.save(destino, optimize=True)
    print(destino.relative_to(RAIZ), destino.stat().st_size, "bytes", img.size)


if __name__ == "__main__":
    main()
