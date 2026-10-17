#!/usr/bin/env python3
"""Gera o ícone do Limpador (PNG, ICO, ICNS e SVG) com Pillow + numpy.

Uso:  python make_icons.py
Cria a pasta ./icons/ com: icon.png (1024), icon.ico, icon.icns, icon.svg
"""
import math
import os
import numpy as np
from PIL import Image, ImageDraw

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, "icons")
S = 2048  # desenho em alta resolução, depois reduz


def gradiente(tamanho, c1, c2):
    y, x = np.mgrid[0:tamanho, 0:tamanho].astype("float32")
    t = (x + y) / (2.0 * (tamanho - 1))
    img = np.zeros((tamanho, tamanho, 4), dtype="uint8")
    for i in range(3):
        img[..., i] = (c1[i] + (c2[i] - c1[i]) * t).astype("uint8")
    img[..., 3] = 255
    return Image.fromarray(img, "RGBA")


def estrela(cx, cy, r, n_pontas=4, interior=0.22):
    pts = []
    for i in range(n_pontas * 2):
        ang = -math.pi / 2 + i * math.pi / n_pontas
        rr = r if i % 2 == 0 else r * interior
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    return pts


def desenhar():
    fundo = gradiente(S, (18, 184, 134), (25, 113, 194))

    # forma "squircle" do ícone
    mascara = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.225), fill=255)
    fundo.putalpha(mascara)

    # brilho suave no topo
    brilho = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    bd = ImageDraw.Draw(brilho)
    bd.ellipse((-S * 0.2, -S * 0.75, S * 1.2, S * 0.45), fill=(255, 255, 255, 38))
    fundo = Image.alpha_composite(fundo, Image.composite(brilho, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mascara))

    cx, cy, R = int(S * 0.47), int(S * 0.53), int(S * 0.30)
    camada = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)

    # sombra do disco
    sombra = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).ellipse((cx - R, cy - R + 40, cx + R, cy + R + 40), fill=(0, 30, 70, 90))
    from PIL import ImageFilter
    sombra = sombra.filter(ImageFilter.GaussianBlur(S * 0.012))
    fundo = Image.alpha_composite(fundo, sombra)

    # disco "ocupado" (branco) e fatia "livre" (branco translúcido)
    d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=(255, 255, 255, 255))
    d.pieslice((cx - R, cy - R, cx + R, cy + R), start=-62, end=62, fill=(255, 255, 255, 105))

    # anel e furo central
    d.ellipse((cx - R * 0.60, cy - R * 0.60, cx + R * 0.60, cy + R * 0.60), outline=(25, 113, 194, 70), width=int(S * 0.006))
    furo = R * 0.20
    camada_furo = Image.new("L", (S, S), 255)
    ImageDraw.Draw(camada_furo).ellipse((cx - furo, cy - furo, cx + furo, cy + furo), fill=0)
    a = camada.getchannel("A")
    a = Image.fromarray(np.minimum(np.array(a), np.array(camada_furo)))
    camada.putalpha(a)
    fundo = Image.alpha_composite(fundo, camada)

    # faíscas de "limpo"
    fa = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fa)
    fd.polygon(estrela(S * 0.74, S * 0.27, S * 0.15), fill=(255, 255, 255, 255))
    fd.polygon(estrela(S * 0.86, S * 0.47, S * 0.065), fill=(255, 255, 255, 235))
    fd.polygon(estrela(S * 0.62, S * 0.12, S * 0.05), fill=(255, 255, 255, 220))
    fundo = Image.alpha_composite(fundo, fa)

    # garante cantos transparentes
    fundo.putalpha(Image.fromarray(np.minimum(np.array(fundo.getchannel("A")), np.array(mascara))))
    return fundo.resize((1024, 1024), Image.LANCZOS)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#12B886"/><stop offset="1" stop-color="#1971C2"/>
    </linearGradient>
  </defs>
  <rect width="1024" height="1024" rx="230" fill="url(#g)"/>
  <clipPath id="c"><rect width="1024" height="1024" rx="230"/></clipPath>
  <ellipse cx="512" cy="-80" rx="716" ry="500" fill="#fff" opacity=".15" clip-path="url(#c)"/>
  <circle cx="481" cy="543" r="307" fill="#fff"/>
  <path d="M481 543 L 764 424 A 307 307 0 0 1 764 662 Z" fill="#fff" opacity=".4"/>
  <circle cx="481" cy="543" r="61" fill="#1D8FA6"/>
  <path d="M758 138 L 773 262 L 897 277 L 773 292 L 758 416 L 743 292 L 619 277 L 743 262 Z" fill="#fff"/>
  <path d="M880 480 L 887 513 L 920 520 L 887 527 L 880 560 L 873 527 L 840 520 L 873 513 Z" fill="#fff" opacity=".92"/>
</svg>
"""


def main():
    os.makedirs(SAIDA, exist_ok=True)
    img = desenhar()
    img.save(os.path.join(SAIDA, "icon.png"))
    img.save(os.path.join(SAIDA, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    try:
        img.save(os.path.join(SAIDA, "icon.icns"))
    except Exception as e:
        print("Aviso: não consegui criar .icns aqui (%s). Num Mac usa: iconutil -c icns" % e)
    # ícones PNG pequenos (para Linux/.desktop)
    for t in (64, 128, 256, 512):
        img.resize((t, t), Image.LANCZOS).save(os.path.join(SAIDA, "icon_%d.png" % t))
    with open(os.path.join(SAIDA, "icon.svg"), "w", encoding="utf-8") as f:
        f.write(SVG)
    print("Ícones criados em", SAIDA)


if __name__ == "__main__":
    main()
