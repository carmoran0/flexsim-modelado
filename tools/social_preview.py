#!/usr/bin/env python3
"""Genera docs/social-preview.png (1280x640), la imagen de vista previa social del repositorio.

Uso:
    python tools/social_preview.py [salida.png]

Requiere Pillow. Dibuja a 3x y reduce al final para suavizar los bordes.
La escena es una línea de producción isométrica: fuente, cinta, procesador,
cinta y rack, con una ruta de AMR en el suelo.
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, SS = 1280, 640, 3
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "docs" / "social-preview.png"

# --- Paleta --------------------------------------------------------------
BG0 = (10, 16, 26)
BG1 = (19, 33, 51)
INK = (241, 245, 249)
MUTED = (148, 163, 184)
AMBER = (251, 176, 64)
TEAL = (45, 190, 200)
STEEL = (86, 112, 150)
SLATE = (58, 74, 98)
FLOOR = (30, 46, 67)

# --- Proyección isométrica -----------------------------------------------
S = 36.0                      # píxeles por unidad
C30, S30 = math.cos(math.radians(30)), 0.5
OX, OY = 854.0, 150.0         # esquina trasera del suelo
FLOOR_X, FLOOR_Y = 12, 7      # tamaño del suelo en unidades


def iso(x, y, z=0.0):
    return ((OX + (x - y) * C30 * S) * SS, (OY + (x + y) * S30 * S - z * S) * SS)


# --- Color ---------------------------------------------------------------
def mix(c, target, k):
    return tuple(round(a + (b - a) * k) for a, b in zip(c, target))


def lighter(c, k):
    return mix(c, (255, 255, 255), k)


def darker(c, k):
    return mix(c, (0, 0, 0), k)


# --- Fuentes -------------------------------------------------------------
FONT_DIRS = [
    "C:/Windows/Fonts/",
    "/usr/share/fonts/truetype/dejavu/",
    "/System/Library/Fonts/Supplemental/",
    "/Library/Fonts/",
]


def font(names, size):
    for name in names:
        for d in FONT_DIRS:
            p = Path(d) / name
            if p.exists():
                return ImageFont.truetype(str(p), round(size * SS))
    return ImageFont.load_default()


SANS_B = ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"]
SANS = ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "Arial.ttf"]
MONO = ["CascadiaMono.ttf", "consola.ttf", "DejaVuSansMono.ttf", "Menlo.ttc"]
MONO_B = ["consolab.ttf", "CascadiaMono.ttf", "DejaVuSansMono-Bold.ttf", "Menlo.ttc"]


def text(d, xy, s, f, fill, spacing=0.0, anchor="ls"):
    """Texto con interletrado opcional; xy en px de diseño (línea base a la izquierda)."""
    x, y = xy[0] * SS, xy[1] * SS
    if not spacing:
        d.text((x, y), s, font=f, fill=fill, anchor=anchor)
        return
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill, anchor=anchor)
        x += f.getlength(ch) + spacing * SS


def text_width(s, f, spacing=0.0):
    return (sum(f.getlength(ch) for ch in s) + spacing * SS * len(s)) / SS if spacing else f.getlength(s) / SS


# --- Primitivas isométricas ----------------------------------------------
def poly(d, pts, fill, outline=None):
    d.polygon(pts, fill=fill)
    if outline:
        d.line(pts + [pts[0]], fill=outline, width=SS)


def box(d, x, y, z, dx, dy, dz, col, edge=0.32):
    """Cuboide con tres caras visibles: techo, cara +y (izquierda) y cara +x (derecha)."""
    x1, y1, z1 = x + dx, y + dy, z + dz
    top = [iso(x, y, z1), iso(x1, y, z1), iso(x1, y1, z1), iso(x, y1, z1)]
    left = [iso(x, y1, z), iso(x1, y1, z), iso(x1, y1, z1), iso(x, y1, z1)]
    right = [iso(x1, y, z), iso(x1, y1, z), iso(x1, y1, z1), iso(x1, y, z1)]
    d.polygon(left, fill=darker(col, 0.20))
    d.polygon(right, fill=darker(col, 0.42))
    d.polygon(top, fill=lighter(col, 0.12))
    if edge:
        d.line(top + [top[0]], fill=lighter(col, edge), width=SS)
        d.line([iso(x1, y1, z), iso(x1, y1, z1)], fill=lighter(col, edge * 0.6), width=SS)


def line3(d, a, b, fill, width=1.0):
    d.line([iso(*a), iso(*b)], fill=fill, width=max(1, round(width * SS)))


def dashed3(d, a, b, fill, dash=0.45, gap=0.35, width=2.0):
    length = math.dist(a, b)
    t = 0.0
    while t < length:
        t2 = min(t + dash, length)
        p = [a[i] + (b[i] - a[i]) * t / length for i in range(3)]
        q = [a[i] + (b[i] - a[i]) * t2 / length for i in range(3)]
        line3(d, p, q, fill, width)
        t += dash + gap


def shadow(layer, x, y, dx, dy, h, alpha=95):
    """Sombra proyectada hacia +x: la huella desplazada en pasos, para cubrir el barrido."""
    d = ImageDraw.Draw(layer)
    steps = 8
    for i in range(steps + 1):
        k = h * 0.55 * i / steps
        pts = [iso(x + k, y + k * 0.18, 0), iso(x + dx + k, y + k * 0.18, 0),
               iso(x + dx + k, y + dy + k * 0.18, 0), iso(x + k, y + dy + k * 0.18, 0)]
        d.polygon(pts, fill=(0, 0, 0, alpha))


# --- Fondo ---------------------------------------------------------------
def background():
    size = (W * SS, H * SS)
    grad = Image.linear_gradient("L").resize(size)
    img = Image.composite(Image.new("RGB", size, BG1), Image.new("RGB", size, BG0), grad).convert("RGBA")

    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    cx, cy = iso(6.2, 3.5, 0)
    r = 330 * SS
    g.ellipse([cx - r, cy - r * 0.62, cx + r, cy + r * 0.62], fill=(60, 120, 190, 70))
    cx2, cy2 = 150 * SS, 90 * SS
    r2 = 260 * SS
    g.ellipse([cx2 - r2, cy2 - r2 * 0.6, cx2 + r2, cy2 + r2 * 0.6], fill=(251, 176, 64, 14))
    glow = glow.filter(ImageFilter.GaussianBlur(90 * SS))
    img = Image.alpha_composite(img, glow)

    dots = Image.new("RGBA", size, (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    step = 32
    for gx in range(step // 2, W, step):
        for gy in range(step // 2, H, step):
            dd.ellipse([(gx - 1.1) * SS, (gy - 1.1) * SS, (gx + 1.1) * SS, (gy + 1.1) * SS],
                       fill=(255, 255, 255, 16))
    return Image.alpha_composite(img, dots)


# --- Escena --------------------------------------------------------------
def draw_floor(img):
    d = ImageDraw.Draw(img)
    box(d, 0, 0, -0.45, FLOOR_X, FLOOR_Y, 0.45, FLOOR, edge=0.18)
    grid = lighter(FLOOR, 0.07)
    for i in range(1, FLOOR_X):
        line3(d, (i, 0, 0), (i, FLOOR_Y, 0), grid, 0.8)
    for j in range(1, FLOOR_Y):
        line3(d, (0, j, 0), (FLOOR_X, j, 0), grid, 0.8)


def draw_shadows(img, items):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    for it in items:
        shadow(layer, *it)
    layer = layer.filter(ImageFilter.GaussianBlur(5 * SS))
    return Image.alpha_composite(img, layer)


def conveyor(d, x, y, length, width=1.2):
    box(d, x, y, 0.0, length, width, 0.5, SLATE, edge=0.22)
    inset = 0.1
    box(d, x, y + inset, 0.5, length, width - 2 * inset, 0.08, lighter(SLATE, 0.18), edge=0.25)
    n = int(length / 0.42)
    for i in range(1, n):
        xx = x + i * length / n
        line3(d, (xx, y + inset, 0.58), (xx, y + width - inset, 0.58), darker(SLATE, 0.15), 1.0)


def item(d, x, y, z, size=0.62, h=0.55):
    box(d, x, y, z, size, size, h, AMBER, edge=0.45)
    # cinta de embalaje
    line3(d, (x + size / 2, y, z + h), (x + size / 2, y + size, z + h), darker(AMBER, 0.28), 1.2)


def source(d, x, y):
    box(d, x, y, 0, 1.5, 1.5, 0.9, STEEL)
    box(d, x + 0.25, y + 0.25, 0.9, 1.0, 1.0, 0.5, lighter(STEEL, 0.1))
    box(d, x + 0.45, y + 0.45, 1.4, 0.6, 0.6, 0.12, AMBER, edge=0.5)


def processor(d, x, y):
    box(d, x, y, 0, 1.8, 1.8, 1.25, TEAL)
    box(d, x + 0.2, y + 0.2, 1.25, 1.4, 1.4, 0.18, darker(TEAL, 0.3))
    box(d, x + 0.55, y + 0.55, 1.43, 0.7, 0.7, 0.55, lighter(TEAL, 0.05))
    box(d, x + 0.75, y + 0.75, 1.98, 0.3, 0.3, 0.1, AMBER, edge=0.5)


def rack(d, x, y, length=2.4, depth=1.8, levels=3):
    t = 0.14
    gap = 0.95
    height = gap * levels + 0.25
    # estructura trasera: pared del fondo y lateral izquierdo
    box(d, x, y, 0, length, t, height, darker(STEEL, 0.1), edge=0.2)
    box(d, x, y + t, 0, t, depth - t, height, darker(STEEL, 0.1), edge=0.2)
    fill = [[(0.0, 0.3), (0.85, 0.3)], [(0.45, 0.3)], [(0.0, 0.3), (0.85, 0.3)]]
    for lv in range(levels):
        z = 0.12 + lv * gap
        box(d, x + t, y + t, z, length - t, depth - t, 0.1, lighter(STEEL, 0.25), edge=0.35)
        for ox, oy in fill[lv]:
            ix = x + t + 0.25 + ox * 1.1
            iy = y + t + 0.2 + oy * 0.7
            item(d, ix, iy, z + 0.1, size=0.6, h=0.5)
    # travesaño frontal superior
    box(d, x + t, y + depth - t, height - 0.1, length - t, t, 0.1, lighter(STEEL, 0.1), edge=0.3)
    return height


def amr(d, x, y):
    box(d, x, y, 0.08, 1.1, 0.8, 0.32, lighter(TEAL, 0.2))
    box(d, x + 0.15, y + 0.12, 0.4, 0.8, 0.56, 0.12, darker(TEAL, 0.3))
    box(d, x + 0.45, y + 0.3, 0.52, 0.2, 0.2, 0.14, AMBER, edge=0.5)


def tag(img, anchor3, label, dy=-34):
    """Etiqueta flotante con línea guía hacia el objeto."""
    d = ImageDraw.Draw(img)
    ax, ay = iso(*anchor3)
    f = font(MONO, 15)
    tw = text_width(label, f)
    pad = 9
    w, h = tw + pad * 2, 26
    bx, by = ax / SS - w / 2, ay / SS + dy - h
    d.line([(ax, ay), (ax, (by + h) * SS)], fill=(*MUTED, 150), width=SS)
    d.rounded_rectangle([bx * SS, by * SS, (bx + w) * SS, (by + h) * SS], radius=8 * SS,
                        fill=(14, 24, 38, 235), outline=(*MUTED, 120), width=SS)
    text(d, (bx + pad, by + h / 2 + 5), label, f, INK)


def scene(img):
    img = draw_shadows(img, [
        # x, y, dx, dy, alto
        (0.8, 2.3, 1.5, 1.5, 1.4),
        (2.4, 2.6, 3.0, 1.2, 0.5),
        (5.4, 2.3, 1.8, 1.8, 2.0),
        (7.2, 2.6, 1.8, 1.2, 0.5),
        (9.0, 2.35, 2.4, 1.8, 3.1),
        (5.6, 5.1, 1.1, 0.8, 0.6),
    ])
    d = ImageDraw.Draw(img)

    # ruta del AMR en el suelo
    dashed3(d, (1.0, 5.5, 0.02), (11.0, 5.5, 0.02), (*AMBER, 255), width=2.2)
    for px in (1.0, 11.0):
        r = 0.16
        d.ellipse([iso(px, 5.5, 0.02)[0] - r * S * SS, iso(px, 5.5, 0.02)[1] - r * S * SS * 0.5,
                   iso(px, 5.5, 0.02)[0] + r * S * SS, iso(px, 5.5, 0.02)[1] + r * S * SS * 0.5],
                  fill=AMBER)

    # línea de producción, de atrás hacia delante
    source(d, 0.8, 2.45)
    conveyor(d, 2.3, 2.6, 3.1)
    item(d, 3.0, 2.85, 0.58)
    item(d, 4.4, 2.85, 0.58)
    processor(d, 5.4, 2.3)
    conveyor(d, 7.2, 2.6, 1.8)
    item(d, 7.9, 2.85, 0.58)
    rack(d, 9.0, 2.35)
    amr(d, 5.6, 5.1)

    tag(img, (1.55, 3.2, 1.55), "Source")
    tag(img, (6.3, 3.2, 2.15), "Processor", dy=-26)
    tag(img, (10.2, 3.25, 3.1), "Rack", dy=-24)
    return img


# --- Texto ---------------------------------------------------------------
def chip(d, x, y, label):
    f = font(MONO, 17)
    w = text_width(label, f) + 30
    h = 36
    d.rounded_rectangle([x * SS, (y - h / 2) * SS, (x + w) * SS, (y + h / 2) * SS], radius=h / 2 * SS,
                        fill=(27, 41, 61), outline=(*MUTED, 130), width=SS)
    text(d, (x + 15, y + 6), label, f, INK)
    return x + w + 12


def copy(img):
    d = ImageDraw.Draw(img)
    left = 76

    d.rectangle([left * SS, 118 * SS, (left + 28) * SS, 121 * SS], fill=AMBER)
    text(d, (left + 42, 126), "SKILL PARA CLAUDE", font(MONO_B, 17), AMBER, spacing=3.2)

    text(d, (left, 210), "flexsim-", font(SANS_B, 78), INK)
    text(d, (left, 290), "modelado", font(SANS_B, 78), INK)

    f = font(SANS, 25)
    text(d, (left, 352), "Construye modelos de FlexSim con FlexScript", f, mix(INK, MUTED, 0.35))
    text(d, (left, 386), "y verifícalos ejecutándolos en FlexSim real.", f, mix(INK, MUTED, 0.35))

    x = left
    for label in ("FlexScript", "FlexSimPy", "Plano 2D"):
        x = chip(d, x, 462, label)

    text(d, (left, 560), "github.com/carmoran0/flexsim-modelado", font(MONO, 17), MUTED)
    return img


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    img = background()
    draw_floor(img)
    img = scene(img)
    img = copy(img)
    img = img.convert("RGB").resize((W, H), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    print(f"{out} {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main()
