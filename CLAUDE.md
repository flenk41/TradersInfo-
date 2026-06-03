# CLAUDE.md — контекст проекта (хэндофф для новой сессии)

> Этот файл читается автоматически при старте. Здесь — всё, что нужно знать,
> чтобы продолжить работу после очистки контекста. Отвечать пользователю **на русском**.

## Что это
Веб-терминал торговой аналитики «Trading Info Stats (TIS)»: крипта (Binance),
акции США (Yahoo) и РФ (MOEX ISS), форекс (Yahoo). Flask (Python) + vanilla JS +
lightweight-charts. Без сборщиков. Цель — **dual licensing: открытый по AGPL-3.0 +
платная коммерческая лицензия** (см. `LICENSE`, `COMMERCIAL.md`, `NOTICE`, `CONTRIBUTING.md`),
без авторизации пользователя, в будущем — мобильные приложения (Android/iOS) + сайт на одном JSON API.
⚠️ Лицензия сменена с MIT на AGPL-3.0: новые файлы исходников снабжать SPDX-заголовком
`AGPL-3.0-or-later`; контрибьюторы — по CLA (иначе нельзя выдавать коммерческие лицензии).

## Запуск / проверка (важные нюансы!)
- Интерпретатор: **`py`** (Windows, Python 3.14). Не `python`.
- Запуск: `py web_app.py` (слушает 127.0.0.1:5000). В этой среде — через MCP `preview_start` (launch.json конфиг `trading-web`).
- Тесты: `py -m pytest -q` (сейчас 29, только `position_calculator` и `risk_manager`).
- **Шаблон `templates/index.html` → ОБЯЗАТЕЛЬНО перезапуск сервера** (Flask кэширует Jinja при `debug=False`).
- **Статика (`static/*.js`, `*.css`) → перезапуск НЕ нужен**, только **Ctrl+Shift+R** в браузере.
- Кэш-бастинг статики автоматический: `?v=<mtime>` через `_asset_version()`.
- Превью: перед стартом убивать висящие процессы на :5000 (иначе отдаёт старый кэш). `preview_screenshot` часто таймаутит — **проверять через `preview_eval`** (надёжно).
- Проверять консоль: `preview_console_logs level=error` (должно быть пусто).

## Архитектура / карта файлов
**Бэкенд оркестрация:** `engine.py::analyze_pair()` собирает весь анализ → `MarketAnalysis` (`analyzer.py`).
- `web_app.py` — Flask, ~20 эндпоинтов, декоратор `@rate_limit(n,60)`, `_asset_version`.
- `market_data.py` — единый слой данных + роутинг: crypto→Binance, `.ME`→MOEX (`_is_moex`), остальное→Yahoo. **Крипто-фолбэк: при `BinanceDataError` (блокировка/обрыв в РФ) klines/ticker/validate автоматически берутся с Yahoo через `_crypto_to_yf()` (BTCUSDT→BTC-USD). Так крипта работает без VPN, но без фандинга/OI/ликвидаций (когда фандинга нет — панель показывает пояснение `#fundingEmpty`, а не пустой график). ⚠️ Yahoo отдаёт часовой объём крипты «дырами» (нули через раз) → в `yfinance_provider.fetch_klines_yf` нулевой объём интерполируется, если нулей >20% (иначе гистограмма объёма рваная). Объём на графике: alpha 0.7, панель `scaleMargins top 0.74`.**
- Провайдеры: `data_fetcher.py` (Binance: ретраи + **перебор зеркал** `_SPOT_MIRRORS`/`_FUTURES_MIRRORS`, вкл. `data-api.binance.vision`), `yfinance_provider.py`, `moex_provider.py`.
- `net.py` — общие ретраи + обработка 429/451 (`request_with_retry`, `retry_call`).
- `data_cache.py` — `get_cached(key, loader, ttl)`, `invalidate(prefix)`.
- Индикаторы/анализ: `analyzer.py` (Wilder RSI/ATR, MACD, тренд), `market_structure.py`, `fibonacci.py`, `deep_analysis.py`, `scalping.py`, `entry_advisor.py`, `market_reasons.py`, `accuracy_estimator.py` (балл «согласованности», НЕ вероятность; **гейт селективности: `recommended_side`=long/short только если лучшая сторона `VERDICT_ENTER` (score≥72, нет блокеров) и spread≥8, иначе `wait` — режет слабые сигналы, повышает долю удачных**).
- Расчёты сделки: `position_calculator.py` — **`zone_stop_take()` (единая логика стоп/тейк для графика И позиции)**, `liquidation_price()` (с комиссией/MMR). **Стоп: за структурой + буфер ATR, с МИНИМАЛЬНОЙ дистанцией `min_stop`×ATR (high 1.2/med 0.9/low 0.7) — если уровень вплотную к входу, стоп отодвигается, чтобы не выбивало шумом; тейк у уровня с R:R≥1:2.** `risk_manager.py` (используется, но вкладка «Риск» удалена; эндпоинт `/api/risk` удалён).
- Фичи: `entry_zones.py` (зоны входа per-TF; **если обычных лонг/шорт-зон нет (напр. сильный тренд) — даёт ПРИБЛИЗИТЕЛЬНУЮ зону от объёма: `_volume_support`/`_volume_resistance` (Volume POC ниже/выше цены) → помечается `approx:True`, label «(приблизит.): объёмная поддержка/сопротивление»; на графике рисуется своим цветом + пунктиром + «~». **Цвета линий входа (лонг/шорт/приблизит.) настраиваются пользователем: кнопка «🎨 Цвета» (`#btnColors`) → модалка `#colorsOverlay`, хранится в localStorage `chart_colors`, применяется через `TradingChart.setEntryColors()`**), `imbalance.py` (FVG per-TF), `candle_patterns.py` (свечные паттерны per-TF + `next_candle_outlook`), `movers_provider.py`, `screener_provider.py` (сортируемая колонка «Балл»: берётся ПОЛНЫЙ балл из `engine.cached_analysis()` — общий кэш с `/api/analyze`, поэтому **совпадает с Обзором**; при сбое анализа фолбэк на лёгкий `_consistency()`. Пул скринера = 4 воркера, результат кэш 300с), `correlation_provider.py`, `portfolio_provider.py` (Sharpe/просадка), `fundamentals_provider.py` (yfinance .info + `fetch_dividend_info()` для калькулятора дивидендов: цена/дивиденд-на-акцию/доходность, эндпоинт `/api/dividends`), `fred_provider.py` (макро), `insider_provider.py` (**инсайдерский/«умные деньги» фактор для АКЦИЙ: US — живой SEC Form 4 через EDGAR (покупки топ-менеджмента/крупные/кластерные = бычий буст, продажи = лёгкий минус); РФ — доли инсайдеров/институционалов из yfinance `.info`; крипта/валюта — N/A. Кэш 6ч. Вклад `score_adj` (−8..+8) идёт в балл согласованности в `accuracy_estimator`. Сырьё/бэктест — автономный `insider_backtest.py` → `insider_trades.csv`**), `universe.py` (полный список Binance/MOEX для поиска).
- AI: `news_provider.py` (Google News RSS + сентимент), `ai_news.py` (**`request_chat()` — общий запросчик, OpenAI-совместимый, с авто-перебором бесплатных моделей OpenRouter при 429/404**, `_provider_error`, `_extract_json`), `ai_personas.py` (5 персон-инвесторов).
- `instruments_catalog.py` — кураторские списки + иконки (RU = цветные монограммы, CDN не работает).
- `signal_journal.py` — журнал сигналов (⚠️ один общий `signals.json`). Авто-оценка TP/SL по 1h-истории; есть защита от рассинхрона пары/уровней (если `entry` вне ×5 диапазона цен инструмента — запись не закрывается). Во фронте пара для журнала берётся из снимка анализа (`lastAnalysisData.pair`), а не из `activePair`. **Запись сигнала — модалка `#journalAddOverlay` (`openJournalAdd`): пользователь вводит РЕАЛЬНУЮ цену входа (по умолчанию текущая рыночная `lastAnalysisData.price`), стоп/тейк/R:R считаются от неё на бэке через `/api/position` (та же `calculate_position`/`zone_stop_take`, что у графика) и пересчитываются на лету. Так вход = где человек реально зашёл (иначе авто-винрейт по истории бессмыслен), а методология стоп/тейк едина с графиком.**
- `serialization.py` (asdict → JSON), `markets.py`, `config.py`, `formatter.py`, `bot.py` (CLI).

**Фронтенд:** `templates/index.html`, `static/app.js` (главная логика), `static/chart.js` (lightweight-charts, зоны/имбаланс/live-поллинг 8с + троттл-обновление анализа 45с), `static/tradingview.js` (iframe + studies RSI/MACD/…), `static/i18n.js` (RU↔EN словарь + DOM-переводчик), `static/style.css`, `static/terminal.css` (в конце — «СОВРЕМЕННЫЙ РЕФРЕШ ИНТЕРФЕЙСА»), `static/refresh-pro.css` (**подключён последним — флагманский слой полировки: aurora-фон + матовое зерно, glass-топбар с saturate, hairline-рамки карточек, премиум-тени, tabular-nums для цен, focus-visible, плавные easing-переходы, prefers-reduced-motion. Также: чистая раскладка шапки (логотип без переноса, редкие ссылки ушли в футер), геро-вердикт с кольцом-прогрессом и тинтом по сигналу (классы `.verdict-card.v-buy/v-sell/v-wait`, `#verdictConfRing --pct`), единый тулбар графика + строка-статус Тренд/HTF/Сводка, карточки movers с дельтой ▲▼ и полосой силы (`--i`), карточные AI-персоны**).

## Навигация (UX)
Верхняя навигация: **Крипта / Акции / Валюта** (рыночный вид) ‖ **Обзор рынка / Скринер / Портфель / Новости / Журнал**.
В рыночном виде правая колонка анализа имеет под-вкладки: **Обзор / Анализ (pro-only) / Паттерны**.
Связность: клик по строке в Обзоре/Скринере/Корреляциях/Watchlist → открывает рыночный вид и `analyze(id)`.
В шапке справа от названия: «📘 Гайд», «🔑 AI-ключ», «💰 Дивиденды» (только для акций, `toggleDividendBtn`), выделенная «❤️ Поддержать» (`.btn-support-top`, открывает модалку support с Ozon-СБП для RU). Калькулятор дивидендов — модалка `#dividendOverlay` (ввод кол-ва акций + цены покупки → дивиденды/год+мес, доходность на вложения, P&L «по средствам»; данные из `/api/dividends`).

## Ключевые конвенции
- **BYOK** (свой ключ пользователя) для AI и FRED: хранится в браузере `localStorage` (`ai_cfg`, `fred_key`), шлётся POST'ом, **никогда не писать ключи в файлы**. Серверный `OPENAI_API_KEY`/`FRED_API_KEY` опциональны (в `.env`, gitignored).
- AI-провайдер определяется **по префиксу ключа** (`gsk_`→Groq, `sk-or-`→OpenRouter, `AIza`→Gemini, `sk-`→OpenAI). По умолчанию рекомендуется **OpenRouter**.
- **Per-TF**: зоны входа, имбаланс, паттерны считаются для каждого ТФ (5m/15m/1h/4h/1d), фронт берёт текущий ТФ графика.
- **Watchlist/портфель** — только localStorage (без сервера, под mobile).
- **i18n**: статика переводится DOM-обходом по словарю в `i18n.js`; динамические перечислимые значения оборачивать в `L()`/`I18N.tr()`. Тексты анализа из Python в основном остаются на русском (полный бэкенд-i18n не делали).
- Кэш: analyze 50с, news 300с, movers 90с/30м/60м, screener 300с, fundamentals/macro/corr 1800–3600с.

## Контакты/ссылки в UI
Telegram: `https://t.me/TradingInfoStats` · Поддержать: `https://flenk41.github.io/`.

## ⚠️ Открытые задачи / релиз-блокеры
1. **Гит**: много несохранённого — закоммитить (на ветке, не в default; формат коммита см. системные правила).
2. **Старый OpenAI-ключ** (`sk-proj-…`) был в `.env`, сейчас закомментирован — **пользователь должен ОТОЗВАТЬ его** на platform.openai.com (я не могу).
3. **`signals.json` — один общий файл на всех** → под публичный/многопользовательский режим вынести журнал в localStorage или привязать к сессии.
4. **Нет тестов** на 11 новых модулей (imbalance, screener, portfolio, correlation, fred, fundamentals, candle_patterns, movers, ai_*, universe).
5. **Прод-сервер**: точка входа `app.run` (dev). Для прод — gunicorn (Linux) / waitress (Windows) + reverse-proxy.
6. Сеть пользователя (РФ): OpenRouter/Groq часто блокируются на TLS; Gemini/Yahoo/MOEX/FRED доступны. **Binance тоже часто режется (WinError 10053) → есть авто-фолбэк крипты на Yahoo (см. `market_data._crypto_to_yf`).** Для полноценной работы крипты без VPN у конечного пользователя — деплой сервера вне РФ (Вариант А): браузер ходит только к нашему API, Binance дёргает сервер из доступной локации.

## Оценка готовности (последняя)
Локальный/портфолио-инструмент ~88%, публичный хобби-сайт ~72%, коммерческий ~52%.

## Дизайн
Тёмная тема (светлую удалили). Современный рефреш: индиго→фиолет акцент (`--accent #6366f1`, `--accent2 #a855f7`, `--grad`), полупрозрачные границы, стекло (topbar/nav/модалки), мягкие тени (`--shadow`, `--shadow-lg`), радиус 16px, фокус-кольцо `--ring`. Переключатель языка — пилюля «🌐 EN/RU».

## Происхождение идей
Часть фич вдохновлена FinceptTerminal (AGPL) — **брать только идеи, не код**. Уже внедрено: AI-персоны, мульти-AI BYOK, FRED-макро, скринер, фундаментал, watchlist+портфель, корреляции.

## Стиль работы с пользователем
Отвечать по-русски, кратко и по делу. Перед сложными правками — проверять в превью через `preview_eval`. Коммит/пуш — только по явной просьбе. Не реализовывать тангенциальные задачи без запроса.
