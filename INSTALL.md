# Установка и распаковка

Инструкция для тех, кто скачал проект с GitHub или из ZIP-архива.

## 1. Распаковка

1. Скачайте ZIP репозитория (**Code → Download ZIP**) или клонируйте:

   ```bash
   git clone https://github.com/ВАШ_ЛОГИН/trading-terminal.git
   cd trading-terminal
   ```

2. Убедитесь, что папка содержит файлы:
   - `web_app.py`
   - `requirements.txt`
   - папки `templates`, `static`

## 2. Python

Установите Python 3.10+ с https://www.python.org/downloads/

При установке на Windows отметьте **“Add Python to PATH”**.

Проверка:

```bash
py --version
```

## 3. Зависимости

В папке проекта:

```bash
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Если `pip` не найден:

```bash
py -m pip install -r requirements.txt
```

## 4. Запуск

```bash
py web_app.py
```

Браузер откроется на `http://127.0.0.1:5000`. Если нет — откройте ссылку вручную.

## 5. Частые проблемы

| Проблема | Решение |
|----------|---------|
| `python` не найден | Используйте `py` вместо `python` |
| Нет модуля `flask` | `pip install -r requirements.txt` |
| Долгая загрузка | Первый запрос к бирже занимает 5–15 с; повторный быстрее (кэш) |
| Нет графика | Обновите страницу Ctrl+F5, нажмите «Анализ» |
| Акции не грузятся | `pip install yfinance` |

## 6. Публикация на GitHub

```bash
git init
git add .
git commit -m "Trading terminal"
git branch -M main
git remote add origin https://github.com/USER/REPO.git
git push -u origin main
```

Не коммитьте: `.env`, `venv/`, `__pycache__/`.

## 7. Хостинг (Render)

- **Build:** `pip install -r requirements.txt`
- **Start:** `gunicorn web_app:app --bind 0.0.0.0:$PORT`

Подробнее: [DEPLOY.md](DEPLOY.md).
