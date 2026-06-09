# SPDX-License-Identifier: AGPL-3.0-or-later
"""Генерация иконки приложения (.ico) в фирменном стиле TIS.

Бейдж с градиентом индиго→фиолет, восходящие бары и трендовая стрелка.
Запуск:  py tools/make_icon.py
Создаёт: app.ico (для PyInstaller) и static/favicon.ico.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

S = 256  # базовый размер
ACCENT_TOP = (99, 102, 241)    # #6366f1
ACCENT_BOT = (168, 85, 247)    # #a855f7


def _vertical_gradient(w: int, h: int, top, bot) -> Image.Image:
    base = Image.new("RGB", (w, h), top)
    px = base.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return base


def make() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # бейдж со скруглением + градиент
    radius = 56
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    pad = 10
    md.rounded_rectangle([pad, pad, S - pad, S - pad], radius=radius, fill=255)
    grad = _vertical_gradient(S, S, ACCENT_TOP, ACCENT_BOT).convert("RGBA")
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)

    # лёгкий верхний блик
    hi = Image.new("L", (S, S), 0)
    ImageDraw.Draw(hi).rounded_rectangle([pad, pad, S - pad, int(S * 0.5)], radius=radius, fill=40)
    img.paste(Image.new("RGBA", (S, S), (255, 255, 255, 255)), (0, 0), Image.composite(hi, Image.new("L", (S, S), 0), mask))

    white = (255, 255, 255, 235)
    light = (219, 234, 254, 255)  # #dbeafe

    # восходящие бары
    bars = [
        (78, 150, 104, 196),
        (116, 120, 142, 196),
        (154, 92, 180, 196),
    ]
    for x0, y0, x1, y1 in bars:
        d.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=white)

    # трендовая линия + стрелка
    pts = [(70, 132), (108, 104), (140, 120), (188, 74)]
    d.line(pts, fill=light, width=11, joint="curve")
    # наконечник стрелки
    d.line([(160, 74), (190, 74)], fill=light, width=11)
    d.line([(190, 74), (190, 104)], fill=light, width=11)

    return img


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icon = make()
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    out_ico = os.path.join(root, "app.ico")
    icon.save(out_ico, format="ICO", sizes=sizes)
    # бонус: favicon для веб-интерфейса
    fav = os.path.join(root, "static", "favicon.ico")
    icon.save(fav, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    # PNG-превью
    icon.save(os.path.join(root, "static", "app-icon.png"), format="PNG")
    print("OK:", out_ico, "+", fav)


if __name__ == "__main__":
    main()
