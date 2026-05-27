/* Двуязычный режим RU <-> EN.
 *
 * Подход: единый словарь «русский исходник -> английский». Движок обходит
 * текстовые узлы и атрибуты (placeholder/title/aria-label) и подменяет текст,
 * запоминая оригинал, чтобы можно было вернуться на русский. Для динамически
 * вставленного контента app.js повторно вызывает I18N.apply() после рендера,
 * а перечислимые значения из бэкенда (тренды, метки и т.п.) оборачивает в I18N.tr().
 */
(function () {
  "use strict";

  // ru -> en. Ключ — точный русский текст (после trim).
  const STR = {
    // — Topbar / общие —
    "Торговый терминал": "Trading Terminal",
    "TradingView · Риск · Анализ": "TradingView · Risk · Analysis",
    "Анализ": "Analyze",
    "Обновить": "Refresh",
    "Уровень детализации": "Detail level",
    "Простой": "Simple",
    "Про": "Pro",
    "Сменить язык / Switch language": "Switch language / Сменить язык",
    "Язык": "Language",
    "TIS · аналитика рынков": "TIS · market analytics",
    "Политика конфиденциальности": "Privacy policy",
    "Info": "Info",
    "📘 Гайд": "📘 Guide",
    "О сервисе": "About",
    "Закрыть": "Close",
    "Поддержать автора": "Support the author",
    "❤️ Поддержать": "❤️ Support",
    "Telegram-канал @TradingInfoStats": "Telegram channel @TradingInfoStats",
    "Загрузка данных...": "Loading data...",
    "—": "—",

    // — Навигация / рынки —
    "Рынок": "Market",
    "Крипто": "Crypto",
    "Крипта": "Crypto",
    "Акции": "Stocks",
    "Валюта": "Forex",

    // — Обзор рынка (движущиеся) —
    "Обзор рынка": "Market overview",
    "📊 Обзор рынка": "📊 Market overview",
    "Год": "Year",
    "Лидер роста": "Top gainer",
    "Лидер падения": "Top loser",
    "Поиск...": "Search...",
    "Топ роста и падения за период. Клик по карточке открывает график и анализ.":
      "Top gainers and losers for the period. Click a card to open chart and analysis.",
    "Выберите рынок и период — данные загрузятся.": "Pick a market and period — data will load.",
    "Загрузка движений рынка…": "Loading market movers…",
    "Нет данных по этому рынку/периоду.": "No data for this market/period.",
    "Не удалось загрузить движения рынка.": "Failed to load market movers.",
    "Криптовалюты": "Cryptocurrencies",
    "🇷🇺 Россия": "🇷🇺 Russia",
    "🇺🇸 США": "🇺🇸 USA",
    "Поиск в списке...": "Search the list...",
    "Инструменты": "Instruments",
    "Ничего не найдено": "Nothing found",

    // — Chart toolbar —
    "Свечи": "Candles",
    "Обновление графика в реальном времени": "Live chart refresh",
    "Настройка точек входа": "Entry points settings",
    "◎ Точки входа ▾": "◎ Entry points ▾",
    "Анализ пары": "Pair analysis",
    "Тренд": "Trend",
    "Сводка": "Summary",
    "HTF Bias": "HTF Bias",
    "Расширенный график TradingView": "Advanced TradingView chart",
    "крипто · красный = лонги платят": "crypto · red = longs pay",
    "Зоны входа появятся после анализа": "Entry zones appear after analysis",
    "Нет зон входа": "No entry zones",
    "Зона": "Zone",
    "Вход": "Entry",
    "Стоп": "Stop",
    "Тейк": "Take",
    "Все": "All",
    "ЛОНГ": "LONG",
    "ШОРТ": "SHORT",

    // — Panel tabs —
    "Обзор": "Overview",
    "Новости": "News",
    "Журнал": "Journal",

    // — Verdict card —
    "Выберите инструмент": "Pick an instrument",
    "Нажмите «Анализ», чтобы получить понятную рекомендацию.": "Click “Analyze” to get a clear recommendation.",
    "балл согласов.": "agreement score",
    "Балл согласованности сигналов — это не вероятность прибыли": "Signal-agreement score — not a probability of profit",
    "ПОКУПАТЬ": "BUY",
    "ПРОДАВАТЬ": "SELL",
    "ЖДАТЬ": "WAIT",
    "Сигнал на покупку (лонг)": "Buy signal (long)",
    "Сигнал на продажу (шорт)": "Sell signal (short)",
    "Чёткого сигнала нет — лучше подождать": "No clear signal — better wait",

    // — Accuracy / agreement —
    "Согласованность сигналов": "Signal agreement",
    "Загрузите анализ": "Run the analysis",
    "Таймфреймы": "Timeframes",
    "Бэктест 4H": "4H backtest",
    "Индикаторы": "Indicators",
    "мало данных": "not enough data",
    "Методы подтверждения": "Confirmation methods",

    // — Verdict banner —
    "Рекомендация": "Recommendation",

    // — Price card —
    "💰 Цена": "💰 Price",
    "Макс 24ч": "24h High",
    "Мин 24ч": "24h Low",
    "Объём": "Volume",
    "за 24ч": "24h",

    // — Scalping —
    "⚡ Скальпинг": "⚡ Scalping",

    // — Market reasons —
    "Медвежьи факторы": "Bearish factors",
    "Бычьи факторы": "Bullish factors",

    // — Deep analysis —
    "🔬 Глубокий анализ": "🔬 Deep analysis",
    "Режим": "Regime",
    "Риск": "Risk",
    "Схождение ЛОНГ": "LONG confluence",
    "Схождение ШОРТ": "SHORT confluence",
    "Глубина": "Depth",
    "Дивергенции": "Divergences",
    "Фандинг / OI": "Funding / OI",
    "Сценарии": "Scenarios",
    "Уровни": "Levels",
    "Триггер:": "Trigger:",
    "Цель:": "Target:",
    "Действие:": "Action:",

    // — Trend / MACD / Volatility / Fibonacci cards —
    "📈 Тренд": "📈 Trend",
    "📉 MACD": "📉 MACD",
    "Линия": "Line",
    "Сигнал": "Signal",
    "Гист.": "Hist.",
    "⚡ Волатильность": "⚡ Volatility",
    "📐 Фибоначчи": "📐 Fibonacci",
    "★ Золотая зона": "★ Golden zone",
    "Лонг": "Long",
    "Шорт": "Short",
    "🎯 Уровни": "🎯 Levels",
    "Сопр.": "Resist.",
    "Подд.": "Support",
    "🔔 Сигналы": "🔔 Signals",
    "Нет особых сигналов": "No notable signals",

    // — Funding —
    "💸 Фандинг": "💸 Funding",
    "Недоступен": "Unavailable",
    "Нет фьючерсной пары": "No futures pair",

    // — News —
    "📰 Новости": "📰 News",
    "День": "Day",
    "Неделя": "Week",
    "Месяц": "Month",
    "🤖 AI-разбор": "🤖 AI review",
    "Сводка по новостям с подтверждающими ссылками": "News summary with supporting links",
    "Выберите инструмент и откройте вкладку — новости загрузятся автоматически.": "Pick an instrument and open the tab — news loads automatically.",
    "Сначала выберите инструмент и нажмите «Анализ».": "First pick an instrument and click “Analyze”.",
    "Нет новостей за выбранный период.": "No news for the selected period.",
    "Загрузка новостей…": "Loading news…",
    "Не удалось загрузить новости.": "Failed to load news.",
    "Ошибка загрузки новостей": "News loading error",
    "🤖 Анализирую новости…": "🤖 Analyzing news…",
    "AI-анализ недоступен": "AI analysis unavailable",
    "Не удалось выполнить AI-анализ.": "Failed to run AI analysis.",
    "AI-сводка по новостям, не финансовая рекомендация. Ссылки ведут на исходные публикации.": "AI news summary, not financial advice. Links point to original publications.",
    "Позитивные факторы": "Positive factors",
    "Негативные факторы": "Negative factors",
    "Уверенность:": "Confidence:",
    "источник": "source",
    "Позитив": "Positive",
    "Негатив": "Negative",
    "Нейтрально": "Neutral",
    "БЫЧИЙ 📈": "BULLISH 📈",
    "МЕДВЕЖИЙ 📉": "BEARISH 📉",
    "НЕЙТРАЛЬНЫЙ": "NEUTRAL",

    // — Journal —
    "📒 Журнал сигналов": "📒 Signal journal",
    "+ Записать сигнал": "+ Log signal",
    "Пересчитать исходы": "Recalculate outcomes",
    "Фиксируем сигнал и автоматически проверяем по истории цены, что сработало первым — тейк или стоп. Так копится реальный винрейт вместо эвристики.":
      "We log the signal and auto-check price history for what hit first — take or stop. This builds a real win rate instead of a heuristic.",
    "Пока нет записей. Откройте инструмент, нажмите «Анализ» и «Записать сигнал».":
      "No records yet. Open an instrument, click “Analyze” and “Log signal”.",
    "Сделок закрыто": "Trades closed",
    "Винрейт": "Win rate",
    "Средний R": "Avg R",
    "Профит-фактор": "Profit factor",
    "Открыто": "Open",
    "Всего": "Total",
    "Открыт": "Open",
    "Истёк": "Expired",
    "Удалить": "Delete",

    // — Errors / misc —
    "Сначала выберите инструмент и нажмите «Анализ»": "First pick an instrument and click “Analyze”",
    "Нет рассчитанных уровней для записи": "No calculated levels to log",
    "Не удалось записать сигнал": "Failed to log signal",
    "Ошибка загрузки": "Loading error",
    "Не удалось подключиться к серверу": "Could not connect to the server",

    // — Перечислимые значения анализа (бэкенд) —
    "БОКОВОЙ ↔️": "SIDEWAYS ↔️",
    "СМЕШАННЫЙ ↔️": "MIXED ↔️",
    "Сильный": "Strong",
    "Умеренный": "Moderate",
    "Слабый": "Weak",
    "Слабо бычий": "Slightly bullish",
    "Слабо медвежий": "Slightly bearish",
    "Смешанные сигналы": "Mixed signals",
    "Флэт (ADX низкий) — не торгуем пробои": "Flat (low ADX) — don't trade breakouts",
    "Бычье пересечение 🟢": "Bullish cross 🟢",
    "Медвежье пересечение 🔴": "Bearish cross 🔴",
    "Без пересечения": "No cross",
    "ВЫСОКАЯ 🔥": "HIGH 🔥",
    "СРЕДНЯЯ ⚡": "MEDIUM ⚡",
    "НИЗКАЯ 😴": "LOW 😴",
    "Риск выше нормы — режьте плечо в 2 раза": "Above-normal risk — cut leverage by half",
    "Нормальный риск — стоп за структурой": "Normal risk — stop behind structure",
    "Тихий рынок — сделки могут застрять в диапазоне": "Quiet market — trades may stall in range",
    "ВОСХОДЯЩИЙ": "UPTREND",
    "НИСХОДЯЩИЙ": "DOWNTREND",

    // — Footer —
    "⚠️ Не финансовая рекомендация · Binance / Yahoo · График TradingView":
      "⚠️ Not financial advice · Binance / Yahoo · TradingView chart",
  };

  const ATTR_KEYS = ["placeholder", "title", "aria-label"];
  const origText = new WeakMap(); // TextNode -> исходная строка
  const origAttr = new WeakMap(); // Element -> {attr: исходная строка}
  let lang = "ru";

  function translate(value) {
    if (value == null) return value;
    const key = String(value).trim();
    if (!key) return value;
    const en = STR[key];
    if (!en) return value;
    // сохраняем ведущие/замыкающие пробелы исходного текстового узла
    return String(value).replace(key, en);
  }

  function walkText(root) {
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    const nodes = [];
    while (tw.nextNode()) nodes.push(tw.currentNode);
    for (const n of nodes) {
      if (!origText.has(n)) {
        if (!n.nodeValue || !n.nodeValue.trim()) continue;
        origText.set(n, n.nodeValue);
      }
      const o = origText.get(n);
      if (o === undefined) continue;
      n.nodeValue = lang === "en" ? translate(o) : o;
    }
  }

  function walkAttr(root) {
    for (const attr of ATTR_KEYS) {
      const els = root.querySelectorAll("[" + attr + "]");
      els.forEach((el) => {
        let store = origAttr.get(el) || {};
        if (!(attr in store)) store[attr] = el.getAttribute(attr);
        origAttr.set(el, store);
        const o = store[attr];
        el.setAttribute(attr, lang === "en" ? translate(o) : o);
      });
    }
  }

  function apply(root) {
    root = root || document.body;
    walkText(root);
    walkAttr(root);
  }

  function updateToggle() {
    const b = document.getElementById("langToggle");
    if (b) b.textContent = lang === "en" ? "RU" : "EN";
  }

  function setLang(l) {
    lang = l === "en" ? "en" : "ru";
    try { localStorage.setItem("ui_lang", lang); } catch (e) {}
    document.documentElement.lang = lang;
    apply(document.body);
    updateToggle();
    if (typeof window.onLangChange === "function") window.onLangChange(lang);
  }

  function init() {
    let saved = "ru";
    try { saved = localStorage.getItem("ui_lang") || "ru"; } catch (e) {}
    lang = saved === "en" ? "en" : "ru";
    document.documentElement.lang = lang;
    apply(document.body);
    updateToggle();
  }

  window.I18N = {
    apply,
    setLang,
    init,
    get: () => lang,
    // перевод перечислимого значения (для строк, собираемых в JS)
    tr: (s) => (lang === "en" ? translate(s) : s),
    // перевод по ключу (RU-ключ); вернёт EN или сам ключ
    t: (k) => (lang === "en" && STR[k] ? STR[k] : k),
  };
})();
