# SPDX-License-Identifier: AGPL-3.0-or-later
"""Экспорт промо-слайдов TikTok в PNG 1080x1920 (готовые кадры для CapCut).

Рендерит marketing/tiktok/index.html настоящим Chromium (Playwright) и сохраняет
каждый кадр .slide отдельным PNG в marketing/tiktok/frames/.

Установка (один раз):
    py -m pip install playwright
    py -m playwright install chromium

Запуск:
    py tools/export_slides.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Необязательные аргументы: путь к html и папка вывода (для RU/EN версий).
#   py tools/export_slides.py                                  → RU
#   py tools/export_slides.py marketing/tiktok/index_en.html marketing/tiktok/frames_en
HTML = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "marketing", "tiktok", "index.html")
OUT = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(ROOT, "marketing", "tiktok", "frames")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Нет Playwright. Установите:\n  py -m pip install playwright\n  py -m playwright install chromium")
        return 1

    if not os.path.exists(HTML):
        print("Не найден", HTML)
        return 1
    os.makedirs(OUT, exist_ok=True)

    url = "file:///" + HTML.replace("\\", "/")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # deviceScaleFactor=2 → кадры чётче (2160x3840), TikTok любит резкость
        page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=2)
        page.goto(url)
        page.wait_for_timeout(600)  # дать отрисоваться шрифтам/градиентам

        slides = page.query_selector_all(".slide")
        if not slides:
            print("Слайды .slide не найдены")
            browser.close()
            return 1
        for i, s in enumerate(slides, 1):
            path = os.path.join(OUT, f"slide_{i}.png")
            s.screenshot(path=path)
            print("сохранён", os.path.relpath(path, ROOT))
        browser.close()

    print(f"\nГотово: {len(slides)} кадров в {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
