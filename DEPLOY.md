# Куда выложить проект

Перед деплоем: полная установка с нуля — [INSTALL.md](INSTALL.md).

## 1. GitHub (код в облаке, бесплатно)

Удобно хранить код и потом подключить к хостингу.

```powershell
cd d:\Trading
git init
git add .
git commit -m "Trading assistant"
```

Создай репозиторий на https://github.com/new (без README), затем:

```powershell
git remote add origin https://github.com/ТВОЙ_ЛОГИН/trading-bot.git
git branch -M main
git push -u origin main
```

---

## 2. Render.com (сайт в интернете, бесплатный тариф)

1. Залей проект на GitHub (шаг 1).
2. Зайди на https://render.com → **New +** → **Web Service**.
3. Подключи свой GitHub-репозиторий.
4. Настройки:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn web_app:app`
   - **Instance Type:** Free
5. **Create Web Service** — через 2–5 минут получишь ссылку вида `https://trading-bot-xxxx.onrender.com`.

На бесплатном тарифе сервис «засыпает» без посещений ~15 мин — первый запрос может быть медленным.

---

## 3. Другие варианты

| Куда | Зачем |
|------|--------|
| **USB / архив** | Просто скопировать папку `Trading` |
| **Google Drive / OneDrive** | Бэкап zip-архива |
| **Railway.app** | Похоже на Render, есть бесплатные кредиты |
| **PythonAnywhere** | Python-хостинг, есть free tier |
| **Свой VPS** | Timeweb, Selectel и т.д. — полный контроль |

---

## 4. Только у себя на ПК (как сейчас)

```powershell
cd d:\Trading
pip install -r requirements.txt
py web_app.py
```

Откроется http://127.0.0.1:5000 — работает только на твоём компьютере.

---

## Важно

- API-ключи Binance **не нужны** — используются публичные данные.
- Файл `.env` в репозиторий не клади (уже в `.gitignore`).
- Это не финансовый совет — только аналитика.
