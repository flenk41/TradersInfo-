let activePair = null;
let activeMarket = "crypto";
let activeView = "market";
let loadedMarket = null;
let moversMarket = "crypto";
let moversRange = "day";
let moversRegion = "ru";
let lastMarketPrice = null;
let activeSide = "long";
let lastAnalysisData = null;
let tvReady = false;
let lwReady = false;
let tvInterval = "60";
let activeCurrency = "$";
let activeNewsRange = "week";

const CATALOG = window.INSTRUMENT_CATALOG || { crypto: [], stock: { regions: [] }, forex: [] };
let activeStockRegion = "ru";
let instrumentSearchQuery = "";

const PLACEHOLDERS = {
  crypto: "ETH/USDT, BTC/USDT",
  stock: "SBER.ME, GAZP.ME, AAPL",
  forex: "EUR/USD, GBP/USD",
};

const FOREX_ICONS = {
  "EUR/USD": "💶",
  "GBP/USD": "💷",
  "USD/JPY": "💴",
  "USD/CHF": "🇨🇭",
  "AUD/USD": "🇦🇺",
  "EUR/GBP": "💱",
  "USD/CNH": "🇨🇳",
  "NZD/USD": "🇳🇿",
  "USD/CAD": "🇨🇦",
  "EUR/JPY": "💶",
  "GBP/JPY": "💷",
  "AUD/JPY": "🇦🇺",
  "EUR/CHF": "🇨🇭",
  "GBP/CHF": "🇨🇭",
  "EUR/AUD": "🇦🇺",
  "NZD/JPY": "🇳🇿",
  "CAD/JPY": "🇨🇦",
  "USD/TRY": "🇹🇷",
  "USD/MXN": "🇲🇽",
  "USD/SGD": "🇸🇬",
  "USD/ZAR": "🇿🇦",
};

const LIST_TITLES = {
  crypto: "Криптовалюты",
  stock: "Акции",
  forex: "Валюта",
};

const $ = (id) => document.getElementById(id);

function formatPrice(v) {
  if (v >= 1000) return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (v >= 1) return v.toFixed(4);
  return v.toFixed(6);
}

function formatVolume(v) {
  if (v >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(2) + "K";
  return v.toFixed(2);
}

const QUOTE_SYMBOLS = {
  USD: "$", USDT: "$", RUB: "₽", EUR: "€", GBP: "£", JPY: "¥",
  CHF: "₣", CAD: "C$", AUD: "A$", NZD: "NZ$", CNH: "¥",
  TRY: "₺", MXN: "Mex$", SGD: "S$", ZAR: "R",
};

function currencyFor(data) {
  const sym = (data.symbol || "").toUpperCase();
  if (data.market_type === "stock") return sym.endsWith(".ME") ? "₽" : "$";
  if (data.market_type === "forex") {
    const disp = (data.display_name || "").toUpperCase();
    const quote = disp.includes("/") ? disp.split("/")[1].trim() : "USD";
    return QUOTE_SYMBOLS[quote] || quote + " ";
  }
  return "$";
}

function money(v) {
  return activeCurrency + formatPrice(v);
}

function moneyVol(v) {
  return activeCurrency + formatVolume(v);
}

// ---- Режим (Простой/Про) ----
function applyMode(mode) {
  document.body.classList.toggle("mode-simple", mode === "simple");
  document.body.classList.toggle("mode-pro", mode !== "simple");
  document.querySelectorAll("#modeToggle button").forEach((b) =>
    b.classList.toggle("active", b.dataset.mode === mode)
  );
  if (mode === "simple") {
    const active = document.querySelector(".panel-tabs button.active");
    if (active && active.classList.contains("pro-only")) switchTab("overview");
  }
  try { localStorage.setItem("ui_mode", mode); } catch (e) {}
}

function renderVerdict(d) {
  const badge = $("verdictBadge");
  if (!badge) return;
  const side = d.accuracy && d.accuracy.recommended_side;
  const acc = d.accuracy && d.accuracy.overall_pct;
  let cls, label, ttl;
  if (side === "long") { cls = "buy"; label = "ПОКУПАТЬ"; ttl = "Сигнал на покупку (лонг)"; }
  else if (side === "short") { cls = "sell"; label = "ПРОДАВАТЬ"; ttl = "Сигнал на продажу (шорт)"; }
  else { cls = "wait"; label = "ЖДАТЬ"; ttl = "Чёткого сигнала нет — лучше подождать"; }

  badge.className = "verdict-badge " + cls;
  badge.textContent = label;
  $("verdictTitle").textContent = ttl;
  $("verdictReason").textContent = d.trend_summary || (d.bias && d.bias.summary) || "—";
  $("verdictConf").textContent = acc != null ? acc + "/100" : "—";
  // Блок «позиции» (Вход/Стоп/Тейк/R:R/Ликвидация) убран: уровни входа со
  // стопом и тейком показываются на графике.
  applyI18n();
}

const NEWS_LABEL = { good: "Позитив", bad: "Негатив", neutral: "Нейтрально" };

function newsTimeAgo(ts) {
  if (!ts) return "";
  const diff = Date.now() / 1000 - ts;
  const h = Math.floor(diff / 3600);
  if (h < 1) return "только что";
  if (h < 24) return h + " ч назад";
  return Math.floor(h / 24) + " дн назад";
}

function renderNews(data) {
  const list = $("newsList");
  const counts = $("newsCounts");
  if (!list) return;
  if (!data.items || !data.items.length) {
    if (counts) counts.innerHTML = "";
    list.innerHTML = '<p class="news-empty">Нет новостей за выбранный период.</p>';
    return;
  }
  if (counts) {
    counts.innerHTML =
      `<span class="news-count good">▲ Хорошие: ${data.counts.good}</span>` +
      `<span class="news-count bad">▼ Плохие: ${data.counts.bad}</span>` +
      `<span class="news-count total">Всего: ${data.counts.total}</span>`;
  }
  list.innerHTML = "";
  data.items.forEach((n) => {
    const a = document.createElement("a");
    a.className = `news-item news-${n.sentiment}`;
    a.href = n.link;
    a.target = "_blank";
    a.rel = "noopener noreferrer";

    const badge = document.createElement("span");
    badge.className = `news-badge news-${n.sentiment}`;
    badge.textContent = NEWS_LABEL[n.sentiment] || "";

    const title = document.createElement("span");
    title.className = "news-title";
    title.textContent = n.title;

    const meta = document.createElement("span");
    meta.className = "news-meta";
    meta.textContent = `${n.source}${n.source ? " · " : ""}${newsTimeAgo(n.timestamp)}`;

    a.append(badge, title, meta);
    list.appendChild(a);
  });
  applyI18n();
}

const AI_OVERALL = {
  bullish: { label: "БЫЧИЙ 📈", cls: "good" },
  bearish: { label: "МЕДВЕЖИЙ 📉", cls: "bad" },
  neutral: { label: "НЕЙТРАЛЬНЫЙ", cls: "neutral" },
};

function renderAiPoints(parent, points, cls) {
  points.forEach((p) => {
    const li = document.createElement("li");
    li.className = `ai-point ${cls}`;
    const txt = document.createElement("span");
    txt.className = "ai-point-text";
    txt.textContent = p.point;
    li.appendChild(txt);
    if (p.sources && p.sources.length) {
      const refs = document.createElement("span");
      refs.className = "ai-refs";
      p.sources.forEach((s, i) => {
        const a = document.createElement("a");
        a.href = s.link;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.className = "ai-ref";
        a.textContent = `[${i + 1}] ${s.source || "источник"}`;
        a.title = s.title;
        refs.appendChild(a);
      });
      li.appendChild(refs);
    }
    parent.appendChild(li);
  });
}

function renderNewsAi(ai) {
  const box = $("newsAiResult");
  if (!box) return;
  box.classList.remove("hidden");
  box.innerHTML = "";

  const o = AI_OVERALL[ai.overall] || AI_OVERALL.neutral;
  const head = document.createElement("div");
  head.className = "ai-head";
  head.innerHTML =
    `<span class="ai-overall ${o.cls}">${o.label}</span>` +
    `<span class="ai-conf">Уверенность: ${ai.confidence || 0}%</span>` +
    `<span class="ai-model">${ai.model || "AI"} · ${ai.analyzed_count || 0} новостей</span>`;
  box.appendChild(head);

  const summary = document.createElement("p");
  summary.className = "ai-summary";
  summary.textContent = ai.summary || "";
  box.appendChild(summary);

  if (ai.bullish && ai.bullish.length) {
    const h = document.createElement("div");
    h.className = "ai-section-title good";
    h.textContent = "Позитивные факторы";
    const ul = document.createElement("ul");
    ul.className = "ai-points";
    renderAiPoints(ul, ai.bullish, "good");
    box.append(h, ul);
  }
  if (ai.bearish && ai.bearish.length) {
    const h = document.createElement("div");
    h.className = "ai-section-title bad";
    h.textContent = "Негативные факторы";
    const ul = document.createElement("ul");
    ul.className = "ai-points";
    renderAiPoints(ul, ai.bearish, "bad");
    box.append(h, ul);
  }

  const note = document.createElement("p");
  note.className = "ai-note";
  note.textContent = "AI-сводка по новостям, не финансовая рекомендация. Ссылки ведут на исходные публикации.";
  box.appendChild(note);
  applyI18n();
}

let aiLoading = false;
async function loadNewsAi() {
  const box = $("newsAiResult");
  if (!box) return;
  if (!activePair) {
    box.classList.remove("hidden");
    box.innerHTML = '<p class="news-empty">Сначала выберите инструмент и нажмите «Анализ».</p>';
    return;
  }
  if (aiLoading) return;
  aiLoading = true;
  box.classList.remove("hidden");
  box.innerHTML = '<p class="news-empty">🤖 Анализирую новости…</p>';
  try {
    const lang = window.I18N ? I18N.get() : "ru";
    const url = `/api/news-ai?pair=${encodeURIComponent(activePair)}&market=${encodeURIComponent(activeMarket)}&range=${activeNewsRange}&lang=${lang}`;
    const json = await (await fetch(url)).json();
    if (json.ok) renderNewsAi(json.ai);
    else box.innerHTML = `<p class="news-empty">${json.error || "AI-анализ недоступен"}</p>`;
  } catch (e) {
    box.innerHTML = '<p class="news-empty">Не удалось выполнить AI-анализ.</p>';
  } finally {
    aiLoading = false;
  }
}

const JOURNAL_STATUS = {
  open: { label: "Открыт", cls: "open" },
  tp: { label: "TP ✓", cls: "good" },
  sl: { label: "SL ✗", cls: "bad" },
  expired: { label: "Истёк", cls: "neutral" },
};

function sigCurrency(sig) {
  if (sig.market === "stock") return (sig.pair || "").toUpperCase().endsWith(".ME") ? "₽" : "$";
  if (sig.market === "forex") {
    const q = (sig.pair || "").toUpperCase().split("/")[1] || "USD";
    return QUOTE_SYMBOLS[q] || q + " ";
  }
  return "$";
}

function fmtDate(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" }) +
    " " + d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

function renderJournal(data) {
  const statsEl = $("journalStats");
  const list = $("journalList");
  if (!statsEl || !list) return;
  const s = data.stats || {};
  statsEl.innerHTML =
    `<div class="jstat"><span>Сделок закрыто</span><strong>${s.closed || 0}</strong></div>` +
    `<div class="jstat"><span>Винрейт</span><strong class="${(s.win_rate || 0) >= 50 ? "good" : "bad"}">${s.win_rate || 0}%</strong></div>` +
    `<div class="jstat"><span>Средний R</span><strong class="${(s.avg_r || 0) >= 0 ? "good" : "bad"}">${s.avg_r || 0}</strong></div>` +
    `<div class="jstat"><span>Профит-фактор</span><strong>${s.profit_factor || 0}</strong></div>` +
    `<div class="jstat"><span>Открыто</span><strong>${s.open || 0}</strong></div>` +
    `<div class="jstat"><span>Всего</span><strong>${s.total || 0}</strong></div>`;

  const sigs = data.signals || [];
  if (!sigs.length) {
    list.innerHTML = '<p class="news-empty">Пока нет записей. Откройте инструмент, нажмите «Анализ» и «Записать сигнал».</p>';
    return;
  }
  list.innerHTML = "";
  sigs.forEach((sig) => {
    const st = JOURNAL_STATUS[sig.status] || JOURNAL_STATUS.open;
    const cur = sigCurrency(sig);
    const fmt = (v) => (v == null ? "—" : cur + formatPrice(v));
    const item = document.createElement("div");
    item.className = `journal-item j-${st.cls}`;
    const rTxt = sig.r_multiple == null ? "" : `<span class="j-r ${sig.r_multiple >= 0 ? "good" : "bad"}">${sig.r_multiple > 0 ? "+" : ""}${sig.r_multiple}R</span>`;

    const head = document.createElement("div");
    head.className = "journal-item-head";
    head.innerHTML =
      `<span class="j-badge j-${st.cls}">${st.label}</span>` +
      `<span class="j-pair">${sig.display || sig.pair} · ${sig.side === "long" ? "ЛОНГ 📈" : "ШОРТ 📉"}</span>` +
      rTxt +
      `<button class="j-del" data-id="${sig.id}" title="Удалить">✕</button>`;

    const body = document.createElement("div");
    body.className = "journal-item-body";
    body.innerHTML =
      `<span>Вход ${fmt(sig.entry)}</span>` +
      `<span class="j-sl">Стоп ${fmt(sig.stop)}</span>` +
      `<span class="j-tp">Тейк ${fmt(sig.take_profit)}</span>` +
      `<span>R:R 1:${sig.rr}</span>` +
      (sig.accuracy_pct != null ? `<span>Балл ${sig.accuracy_pct}</span>` : "") +
      `<span class="j-date">${fmtDate(sig.created_ts)}</span>`;

    item.append(head, body);
    list.appendChild(item);
  });

  list.querySelectorAll(".j-del").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetch("/api/journal/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: btn.dataset.id }),
      });
      loadJournal();
    });
  });
  applyI18n();
}

let journalLoading = false;
async function loadJournal() {
  const list = $("journalList");
  if (!list) return;
  if (journalLoading) return;
  journalLoading = true;
  try {
    const json = await (await fetch("/api/journal")).json();
    if (json.ok) renderJournal(json);
  } catch (e) {
    /* keep previous */
  } finally {
    journalLoading = false;
  }
}

async function saveSignal() {
  if (!lastAnalysisData || !activePair) {
    showError("Сначала выберите инструмент и нажмите «Анализ»");
    return;
  }
  let side = lastAnalysisData.accuracy?.recommended_side;
  if (side !== "long" && side !== "short") side = activeSide;
  const preview = lastAnalysisData.position_preview?.[side];
  if (!preview) {
    showError("Нет рассчитанных уровней для записи");
    return;
  }
  const payload = {
    pair: activePair,
    market: activeMarket,
    display: lastAnalysisData.display_name || activePair,
    side,
    entry: preview.entry_price,
    stop: preview.stop_loss,
    take_profit: preview.take_profit,
    take_profit_2: preview.take_profit_2,
    rr: preview.risk_reward,
    accuracy_pct: lastAnalysisData.accuracy?.overall_pct,
  };
  try {
    const json = await (await fetch("/api/journal/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })).json();
    if (json.ok) {
      switchView("journal");
      loadJournal();
    } else {
      showError(json.error || "Не удалось записать сигнал");
    }
  } catch (e) {
    showError("Не удалось записать сигнал");
  }
}

let newsLoading = false;
async function loadNews() {
  const list = $("newsList");
  if (!list) return;
  if (!activePair) {
    list.innerHTML = '<p class="news-empty">Сначала выберите инструмент и нажмите «Анализ».</p>';
    return;
  }
  if (newsLoading) return;
  newsLoading = true;
  list.innerHTML = '<p class="news-empty">Загрузка новостей…</p>';
  try {
    const lang = window.I18N ? I18N.get() : "ru";
    const url = `/api/news?pair=${encodeURIComponent(activePair)}&market=${encodeURIComponent(activeMarket)}&range=${activeNewsRange}&lang=${lang}`;
    const json = await (await fetch(url)).json();
    if (json.ok) renderNews(json);
    else list.innerHTML = `<p class="news-empty">${json.error || "Ошибка загрузки новостей"}</p>`;
  } catch (e) {
    list.innerHTML = '<p class="news-empty">Не удалось загрузить новости.</p>';
  } finally {
    newsLoading = false;
  }
}

// ---- Обзор рынка (gainers / losers) ----
let moversLoading = false;

function moverCurrency(m) {
  if (m.market === "stock") return (m.id || "").toUpperCase().endsWith(".ME") ? "₽" : "$";
  if (m.market === "forex") {
    const q = (m.id || "").toUpperCase().split("/")[1] || "USD";
    return QUOTE_SYMBOLS[q] || q + " ";
  }
  return "$";
}

function moverIconHtml(m) {
  const fb = instrumentFallbackLabel(m);
  const style = monogramStyle(m.id || fb);
  if (m.market === "forex" && FOREX_ICONS[m.id]) {
    return `<span class="inst-emoji">${FOREX_ICONS[m.id]}</span>`;
  }
  if (m.icon_url) {
    return `<span class="inst-fallback" style="${style}">${fb}</span>` +
      `<img class="inst-icon" src="${m.icon_url}" alt="" loading="lazy" onerror="this.style.display='none'">`;
  }
  return `<span class="inst-fallback" style="${style}">${fb}</span>`;
}

function moverCard(m) {
  const up = m.change_pct >= 0;
  const cur = moverCurrency(m);
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "mover-card " + (up ? "up" : "down");
  btn.style.setProperty("--i", Math.min(1, Math.abs(m.change_pct) / 15).toFixed(2));
  btn.innerHTML =
    `<span class="mc-head">` +
      `<span class="inst-icon-wrap">${moverIconHtml(m)}</span>` +
      `<span class="mc-titles"><span class="mc-name">${m.name}</span>` +
      `<span class="mc-sub">${m.subtitle || m.id}</span></span>` +
    `</span>` +
    `<span class="mc-chg ${up ? "up" : "down"}">${up ? "+" : ""}${m.change_pct}%</span>` +
    `<span class="mc-price">${cur}${formatPrice(m.price)}</span>`;
  btn.addEventListener("click", () => {
    if (m.market === "stock") {
      activeStockRegion = m.region || activeStockRegion;
      document.querySelectorAll("#stockRegionTabs .btn-region").forEach((b) =>
        b.classList.toggle("active", b.dataset.region === activeStockRegion)
      );
    }
    switchView("market", m.market);
    analyze(m.id);
  });
  return btn;
}

function renderMovers(data) {
  const top = $("moversTop");
  const grid = $("moversGrid");
  if (!grid) return;
  if (!data.items || !data.items.length) {
    if (top) top.innerHTML = "";
    grid.innerHTML = '<p class="news-empty">Нет данных по этому рынку/периоду.</p>';
    return;
  }
  if (top) {
    const big = (m, kind) => {
      if (!m) return "";
      const cur = moverCurrency(m);
      return `<div class="mover-big ${kind}">
        <span class="mb-label">${kind === "up" ? "Лидер роста" : "Лидер падения"}</span>
        <span class="mb-name">${m.name}</span>
        <span class="mb-chg ${kind}">${m.change_pct >= 0 ? "+" : ""}${m.change_pct}%</span>
        <span class="mb-price">${cur}${formatPrice(m.price)}</span>
      </div>`;
    };
    top.innerHTML = big(data.top_gainer, "up") + big(data.top_loser, "down");
  }
  grid.innerHTML = "";
  data.items.forEach((m) => grid.appendChild(moverCard(m)));
  applyI18n();
}

async function loadMovers() {
  const grid = $("moversGrid");
  if (!grid || moversLoading) return;
  moversLoading = true;
  grid.innerHTML = '<p class="news-empty">Загрузка движений рынка…</p>';
  if ($("moversTop")) $("moversTop").innerHTML = "";
  try {
    let url = `/api/movers?market=${moversMarket}&range=${moversRange}`;
    if (moversMarket === "stock") url += `&region=${moversRegion}`;
    const json = await (await fetch(url)).json();
    if (json.ok) renderMovers(json);
    else grid.innerHTML = `<p class="news-empty">${json.error || "Ошибка загрузки"}</p>`;
  } catch (e) {
    grid.innerHTML = '<p class="news-empty">Не удалось загрузить движения рынка.</p>';
  } finally {
    moversLoading = false;
  }
}

function verdictClass(verdict) {
  if (!verdict) return "";
  if (verdict.includes("ВХОДИТЬ")) return "verdict-enter";
  if (verdict.includes("ЖДАТЬ")) return "verdict-wait";
  return "verdict-no";
}

function setLoading(on) {
  $("loading").classList.toggle("hidden", !on);
  if (on) $("error").classList.add("hidden");
}

function showError(msg) {
  $("error").textContent = window.I18N ? I18N.tr(msg) : msg;
  $("error").classList.remove("hidden");
  setTimeout(() => $("error")?.classList.add("hidden"), 6000);
}

// Внутренние под-вкладки колонки анализа: Обзор / Анализ.
function switchTab(tabId) {
  document.querySelectorAll(".panel-tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-panel").forEach((p) => {
    p.classList.toggle("active", p.id === `tab-${tabId}`);
  });
}

// Верхняя навигация: рынки (Крипта/Акции/Валюта) + Обзор рынка / Новости / Журнал.
function switchView(view, market) {
  activeView = view;
  if (view === "market" && market) activeMarket = market;

  document.querySelectorAll("#mainNav .nav-tab").forEach((b) => {
    const on = b.dataset.view === "market"
      ? view === "market" && b.dataset.market === activeMarket
      : b.dataset.view === view;
    b.classList.toggle("active", on);
  });
  document.querySelectorAll(".app-view").forEach((v) => {
    v.classList.toggle("hidden", v.id !== `view-${view}`);
    v.classList.toggle("active", v.id === `view-${view}`);
  });

  if (view === "market") {
    renderPairsGrid(activeMarket);
    const ph = PLACEHOLDERS[activeMarket];
    if (ph && $("customPair")) $("customPair").placeholder = ph;
    if (loadedMarket !== activeMarket || !activePair) {
      const first = getFirstInstrumentId(activeMarket);
      if (first) analyze(first);
    } else {
      setTimeout(() => TradingChart.resize?.(), 80);
    }
  } else if (view === "movers") {
    loadMovers();
  } else if (view === "news") {
    loadNews();
  } else if (view === "journal") {
    loadJournal();
  }
  applyI18n();
}

function initTradingViewLazy() {
  const el = $("tradingviewContainer");
  if (!el || !window.TradingViewWidget || tvReady) return;
  TradingViewWidget.init(el);
  tvReady = true;
}

function updateTvLink(symbol) {
  const a = $("btnOpenTv");
  if (!a || !symbol) return;
  const url = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(symbol)}`;
  a.href = url;
}

function initLightweightChartOnce() {
  if (lwReady) return;
  const main = $("chartContainer");
  const funding = $("fundingChartContainer");
  const overlay = $("zoneOverlay");
  if (!main || !funding || !window.LightweightCharts) return;
  TradingChart.init(main, funding, overlay);
  TradingChart.setRefreshCallback?.(onLiveRefresh);
  lwReady = true;
}

async function loadChartsForPair(pair, marketType) {
  initLightweightChartOnce();
  const lwMap = { "5": "5m", "15": "15m", "60": "1h", "240": "4h", D: "1d" };
  const tf = lwMap[tvInterval] || "1h";
  await TradingChart.loadPair(pair, activeMarket, tf);
}

function updateChartTrend(data) {
  if (!data) return;
  TradingChart.applyAnalysis(data);
  buildEntryMenu(data.long_entry_zones, data.short_entry_zones);
  renderZonesStrip(data);
  applyI18n();
}

function renderAccuracy(acc) {
  const panel = $("accuracyPanel");
  if (!panel) return;
  if (!acc) {
    $("accuracyGrade").textContent = "—";
    $("accuracyRing").textContent = "—";
    $("accuracyRing").style.setProperty("--pct", 0);
    return;
  }

  $("accuracyGrade").textContent = `Класс ${acc.confidence_grade}`;
  const ring = $("accuracyRing");
  ring.textContent = `${acc.overall_pct}`;
  ring.style.setProperty("--pct", acc.overall_pct);
  $("accuracyLabel").textContent = acc.reliability_label;
  $("accuracyExplanation").textContent = acc.explanation;

  const setBar = (id, pct, labelId, text) => {
    const bar = $(id);
    if (bar) bar.style.width = `${Math.min(100, pct)}%`;
    const lbl = $(labelId);
    if (lbl) lbl.textContent = text;
  };
  setBar("accBarTf", acc.timeframe_alignment_pct, "accTf", `${acc.timeframe_alignment_pct}%`);
  setBar(
    "accBarBt",
    acc.backtest_hit_rate,
    "accBt",
    acc.backtest_samples > 0 ? `${acc.backtest_hit_rate}%` : "мало данных"
  );
  setBar("accBarInd", acc.indicator_agreement_pct, "accInd", `${acc.indicator_agreement_pct}%`);

  const ul = $("accuracyFactors");
  ul.innerHTML = "";
  (acc.factors || []).forEach((f) => {
    const li = document.createElement("li");
    li.textContent = f;
    ul.appendChild(li);
  });

  renderAccuracyChecks(acc.checks || []);
}

const CHECK_ICON = { good: "✓", bad: "✗", neutral: "•" };

function renderAccuracyChecks(checks) {
  const wrap = $("accuracyChecks");
  if (!wrap) return;
  if (!checks.length) {
    wrap.innerHTML = "";
    return;
  }
  const passed = checks.filter((c) => c.status === "good").length;
  let html = `<div class="checks-title">Методы подтверждения <span>${passed}/${checks.length}</span></div>`;
  html += '<div class="checks-list">';
  checks.forEach((c) => {
    const delta = c.delta ? `<span class="chk-delta">${c.delta > 0 ? "+" : ""}${c.delta}</span>` : "";
    html += `<div class="chk chk-${c.status}">
      <span class="chk-ico">${CHECK_ICON[c.status] || "•"}</span>
      <span class="chk-name">${c.name}</span>
      ${delta}
      ${c.detail ? `<span class="chk-detail">${c.detail}</span>` : ""}
    </div>`;
  });
  html += "</div>";
  wrap.innerHTML = html;
}

function renderZonesStrip(data) {
  const strip = $("zonesStrip");
  if (!strip || !data) return;
  strip.innerHTML = "";
  const add = (zones, cls) => {
    (zones || []).forEach((z) => {
      const chip = document.createElement("div");
      chip.className = `zone-chip ${cls}`;
      chip.textContent = `${z.label}: ${money(z.price)}`;
      chip.title = `${money(z.low)} – ${money(z.high)}`;
      strip.appendChild(chip);
    });
  };
  add(data.long_entry_zones, "long");
  add(data.short_entry_zones, "short");
  if (!strip.children.length) {
    strip.innerHTML = '<span class="zone-chip">Зоны входа появятся после анализа</span>';
  }
}

function setActiveButton(pair) {
  document.querySelectorAll(".instrument-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.pair === pair);
  });
}

function instrumentFallbackLabel(item) {
  const id = item.id || "";
  // Для акций — тикер (SBER, AAPL), а не страна.
  if (item.market === "stock" || id.endsWith(".ME")) {
    return id.replace(".ME", "").slice(0, 4).toUpperCase();
  }
  if (id.includes("/")) return id.split("/")[0].slice(0, 4).toUpperCase();
  if (item.subtitle) return item.subtitle.slice(0, 4).toUpperCase();
  return id.slice(0, 4).toUpperCase();
}

// Детерминированный цвет монограммы по тикеру — чтобы у КАЖДОГО инструмента
// была своя иконка-аватар, даже если логотип не загрузился/отсутствует.
function _hue(s) {
  let h = 0;
  for (let i = 0; i < (s || "").length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return h;
}
function monogramStyle(key) {
  const h = _hue(key || "");
  return `background:linear-gradient(135deg,hsl(${h} 58% 48%),hsl(${(h + 40) % 360} 64% 36%));color:#fff;`;
}

function instrumentIconHtml(item) {
  const fb = instrumentFallbackLabel(item);
  const style = monogramStyle(item.id || fb);
  if ((item.market === "forex" || activeMarket === "forex") && FOREX_ICONS[item.id]) {
    return `<span class="inst-emoji">${FOREX_ICONS[item.id]}</span>`;
  }
  if (item.icon_url) {
    return `<span class="inst-fallback" style="${style}">${fb}</span>` +
      `<img class="inst-icon" src="${item.icon_url}" alt="" loading="lazy" onerror="this.style.display='none'" />`;
  }
  return `<span class="inst-fallback" style="${style}">${fb}</span>`;
}

function getCatalogItems(market) {
  if (market === "crypto") return CATALOG.crypto || [];
  if (market === "forex") return CATALOG.forex || [];
  if (market === "stock") {
    const regions = CATALOG.stock?.regions || [];
    const reg = regions.find((r) => r.id === activeStockRegion) || regions[0];
    return reg?.items || [];
  }
  return [];
}

function getFirstInstrumentId(market) {
  const items = getCatalogItems(market);
  return items[0]?.id || null;
}

function instrumentButton(item) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "instrument-item";
  btn.dataset.pair = item.id;
  btn.innerHTML = `
    <span class="inst-icon-wrap">${instrumentIconHtml(item)}</span>
    <span class="inst-text">
      <strong>${item.name}</strong>
      <small>${item.id}${item.subtitle && item.subtitle !== item.id ? " · " + item.subtitle : ""}</small>
    </span>
  `;
  btn.addEventListener("click", () => {
    $("customPair").value = item.id;
    analyze(item.id);
  });
  return btn;
}

function fillInstrumentGrid(items) {
  const grid = $("pairsGrid");
  if (!grid) return;
  grid.innerHTML = "";
  if (!items.length) {
    grid.innerHTML = '<p class="instrument-empty">Ничего не найдено</p>';
    return;
  }
  items.forEach((item) => grid.appendChild(instrumentButton(item)));
  if (activePair) setActiveButton(activePair);
  applyI18n();
}

let _listSeq = 0;
async function renderPairsGrid(market) {
  const title = $("instrumentListTitle");
  const regionTabs = $("stockRegionTabs");
  if (title) title.textContent = LIST_TITLES[market] || "Инструменты";
  regionTabs?.classList.toggle("hidden", market !== "stock");
  // Мгновенно показываем кураторский список, затем подменяем полным (все
  // пары Binance / все бумаги MOEX / расширенные США и форекс).
  fillInstrumentGrid(getCatalogItems(market));
  const seq = ++_listSeq;
  try {
    const region = market === "stock" ? activeStockRegion : "all";
    const json = await (await fetch(`/api/instruments/search?market=${market}&region=${region}&q=`)).json();
    if (seq === _listSeq && json.ok && instrumentSearchQuery.trim() === "") {
      fillInstrumentGrid(json.items);
    }
  } catch (e) {
    /* остаётся кураторский список */
  }
}

// Поиск по ПОЛНОЙ вселенной (все пары Binance / все бумаги MOEX / расширенный
// каталог США и форекса) — серверный эндпоинт с защитой от устаревших ответов.
let _searchSeq = 0;
async function searchInstrumentsRemote(q) {
  const market = activeMarket;
  const region = market === "stock" ? activeStockRegion : "all";
  const seq = ++_searchSeq;
  try {
    const url = `/api/instruments/search?market=${market}&region=${region}&q=${encodeURIComponent(q)}`;
    const json = await (await fetch(url)).json();
    if (seq !== _searchSeq) return;
    if (json.ok) fillInstrumentGrid(json.items);
  } catch (e) {
    /* оставляем текущий список */
  }
}

function normalizePairInput(pair, market) {
  let p = (pair || "").trim().toUpperCase();
  if (!p) return p;
  if (market === "crypto") {
    if (!p.includes("/")) {
      p = p.replace("USDT", "") + "/USDT";
    }
    return p;
  }
  if (market === "stock") {
    const items = getCatalogItems("stock");
    const allRu = (CATALOG.stock?.regions || []).flatMap((r) => r.items || []);
    const hit = [...items, ...allRu].find(
      (i) => i.id.toUpperCase() === p || i.id.replace(".ME", "") === p
    );
    if (hit) return hit.id;
    if (activeStockRegion === "ru" && !p.includes(".")) return `${p}.ME`;
    return p;
  }
  return p;
}

function renderScalping(scalp) {
  const panel = $("scalpPanel");
  if (!panel) return;
  if (!scalp) {
    $("scalpVerdict").textContent = "—";
    $("scalpVwap").textContent = "—";
    $("scalpSignals").innerHTML = "";
    $("scalpTips").innerHTML = "";
    return;
  }
  $("scalpVerdict").textContent = scalp.verdict || "—";
  $("scalpVwap").textContent = scalp.price_vs_vwap || (scalp.vwap ? "VWAP: " + money(scalp.vwap) : "—");

  const sigEl = $("scalpSignals");
  sigEl.innerHTML = "";
  (scalp.signals || []).forEach((s) => {
    const card = document.createElement("div");
    card.className = "scalp-signal " + (s.direction === "long" ? "scalp-long" : "scalp-short");
    card.innerHTML = `
      <strong>${s.timeframe.toUpperCase()} · ${s.direction === "long" ? "ЛОНГ" : "ШОРТ"} (${s.score})</strong>
      <span>Зона: ${s.entry_zone}</span>
      <span>${s.stop_hint}</span>
      <span>${s.target_hint}</span>
      <small>${s.note || ""}</small>
    `;
    sigEl.appendChild(card);
  });

  const tipsEl = $("scalpTips");
  tipsEl.innerHTML = "";
  (scalp.tips || []).forEach((t) => {
    const li = document.createElement("li");
    li.textContent = t;
    tipsEl.appendChild(li);
  });
}

function renderLevels(containerId, levels) {
  const el = $(containerId);
  el.innerHTML = "";
  if (!levels || !levels.length) {
    el.innerHTML = '<span class="tag">—</span>';
    return;
  }
  levels.forEach((l) => {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = money(l);
    el.appendChild(tag);
  });
}

function renderTimeframes(timeframes) {
  const el = $("timeframes");
  el.innerHTML = "";
  timeframes.forEach((tf) => {
    const div = document.createElement("div");
    div.className = "tf-item";
    const sma = tf.sma200 ? money(tf.sma200) : "—";
    div.innerHTML = `
      <strong>[${tf.timeframe.toUpperCase()}] ${L(tf.trend)}</strong>
      <span>${L(tf.market_structure)} · ADX ${tf.adx}</span>
      <span>RSI ${tf.rsi} · MACD ${L(tf.macd_trend)} · ${L(tf.macd_cross)}</span>
    `;
    el.appendChild(div);
  });
}

function macdTrendClass(trend) {
  if (!trend) return "";
  if (trend.includes("БЫЧИЙ") || trend.toLowerCase().includes("бычий")) return "macd-bull";
  if (trend.includes("МЕДВЕЖИЙ") || trend.toLowerCase().includes("медвежий")) return "macd-bear";
  return "";
}

function renderMacd(timeframes) {
  const tf1h = timeframes.find((t) => t.timeframe === "1h") || timeframes[0];
  if (!tf1h) return;

  $("macdSummary1h").textContent = "1H: " + L(tf1h.macd_trend);
  $("macdSummary1h").className = "macd-summary " + macdTrendClass(tf1h.macd_trend);
  $("macdCross1h").textContent = L(tf1h.macd_cross);
  $("macdLine1h").textContent = tf1h.macd >= 0 ? "+" + tf1h.macd.toFixed(4) : tf1h.macd.toFixed(4);
  $("macdSignal1h").textContent = tf1h.macd_signal >= 0 ? "+" + tf1h.macd_signal.toFixed(4) : tf1h.macd_signal.toFixed(4);
  const histEl = $("macdHist1h");
  histEl.textContent = (tf1h.macd_histogram >= 0 ? "+" : "") + tf1h.macd_histogram.toFixed(4);
  histEl.className = tf1h.macd_histogram >= 0 ? "hist-up" : "hist-down";

  const allEl = $("macdAll");
  allEl.innerHTML = "";
  timeframes.forEach((tf) => {
    const row = document.createElement("div");
    row.className = "macd-tf-row";
    const sign = tf.macd_histogram >= 0 ? "+" : "";
    row.innerHTML = `
      <span class="macd-tf-label">${tf.timeframe.toUpperCase()}</span>
      <span class="${macdTrendClass(tf.macd_trend)}">${L(tf.macd_trend)}</span>
      <span class="macd-tf-hist">${sign}${tf.macd_histogram.toFixed(4)}</span>
    `;
    allEl.appendChild(row);
  });
}

function renderTrade(trade, bias) {
  if (!trade) return;
  $("bestAction").textContent = trade.best_action;
  if (bias) {
    $("htfBias").textContent = "Bias: " + bias.summary;
  }
  $("longVerdict").textContent = trade.long_verdict;
  $("shortVerdict").textContent = trade.short_verdict;
  $("longVerdict").className = verdictClass(trade.long_verdict);
  $("shortVerdict").className = verdictClass(trade.short_verdict);
  $("longScore").textContent = trade.long_score + "/100";
  $("shortScore").textContent = trade.short_score + "/100";
  $("entryHint").textContent = trade.entry_price_hint;
  $("stopHint").textContent = trade.stop_loss_hint;
  $("tpHint").textContent = trade.take_profit_hint;

  const wEl = $("warnings");
  wEl.innerHTML = "";
  (trade.warnings || []).forEach((w) => {
    const li = document.createElement("li");
    li.textContent = "⚠ " + w;
    wEl.appendChild(li);
  });
}

function renderDeep(deep) {
  const panel = $("deepPanel");
  if (!deep || !panel) return;

  $("deepSummary").textContent = deep.executive_summary || "—";
  $("deepRegime").textContent = deep.market_regime || "—";
  $("deepRegimeDesc").textContent = deep.regime_description || "";
  $("deepRisk").textContent = `${L(deep.risk_label)} (${deep.risk_score}/100)`;
  const bar = $("deepRiskBar");
  if (bar) bar.style.width = `${deep.risk_score}%`;
  $("deepConfLong").textContent = deep.confluence_long + "%";
  $("deepConfShort").textContent = deep.confluence_short + "%";
  $("deepDepth").textContent = deep.depth_score + "/100";

  const divEl = $("deepDivergences");
  divEl.innerHTML = "";
  (deep.divergences || []).forEach((d) => {
    const li = document.createElement("li");
    li.textContent = d;
    divEl.appendChild(li);
  });

  $("deepFunding").textContent = deep.funding_trend || "—";
  $("deepOi").textContent = deep.oi_trend || "—";
  const btcEl = $("deepBtc");
  if (deep.btc_context) {
    btcEl.textContent = deep.btc_context;
    btcEl.classList.remove("hidden");
  } else if (btcEl) {
    btcEl.classList.add("hidden");
  }

  const insEl = $("deepInsights");
  insEl.innerHTML = "";
  (deep.insights || []).forEach((i) => {
    const card = document.createElement("div");
    card.className = "insight-card";
    card.innerHTML = `
      <strong>${i.name}</strong>
      <span class="ins-value">${i.value}</span>
      <span class="ins-signal">${i.signal}</span>
      ${i.detail ? `<small>${i.detail}</small>` : ""}
    `;
    insEl.appendChild(card);
  });

  const scEl = $("deepScenarios");
  scEl.innerHTML = "";
  (deep.scenarios || []).forEach((s) => {
    const card = document.createElement("div");
    card.className = "scenario-card";
    card.innerHTML = `
      <h5>${s.title} <em>${s.probability}</em></h5>
      <p><b>Триггер:</b> ${s.trigger}</p>
      <p><b>Цель:</b> ${s.target}</p>
      <p><b>Действие:</b> ${s.action}</p>
    `;
    scEl.appendChild(card);
  });

  const watchEl = $("deepWatch");
  watchEl.innerHTML = "";
  (deep.watch_levels || []).forEach((w) => {
    const li = document.createElement("li");
    li.textContent = w;
    watchEl.appendChild(li);
  });
}

function renderFibonacci(fib, price) {
  if (!fib) return;
  $("fibDirection").textContent = "Свинг: " + fib.direction;
  $("fibZone").textContent = fib.current_zone;
  $("fibHint").textContent = fib.entry_hint;
  $("fibLongZone").textContent = fib.optimal_long_zone;
  $("fibShortZone").textContent = fib.optimal_short_zone;
  $("fibGolden").classList.toggle("hidden", !fib.in_golden_zone);

  const el = $("fibLevels");
  el.innerHTML = "";
  fib.levels.forEach((lvl) => {
    const row = document.createElement("div");
    const near = Math.abs(lvl.price - price) / price < 0.008;
    row.className = "fib-level-row" + (near ? " active" : "");
    row.innerHTML = `<span class="fib-label">${lvl.label}</span><span>${money(lvl.price)}</span>`;
    el.appendChild(row);
  });
}

function renderSignals(signals) {
  const el = $("signals");
  el.innerHTML = "";
  if (!signals || !signals.length) {
    el.innerHTML = "<li>Нет особых сигналов</li>";
    return;
  }
  signals.forEach((s) => {
    const li = document.createElement("li");
    li.textContent = s;
    el.appendChild(li);
  });
}

function render(data) {
  activeCurrency = currencyFor(data);
  if (TradingChart.setCurrency) TradingChart.setCurrency(activeCurrency);
  const changeEl = $("priceChange");
  const sign = data.change_24h_pct >= 0 ? "+" : "";
  $("priceMain").textContent = money(data.price);
  changeEl.textContent = sign + data.change_24h_pct.toFixed(2) + "% " + L("за 24ч");
  changeEl.className = "price-change " + (data.change_24h_pct >= 0 ? "up" : "down");

  $("high24").textContent = money(data.high_24h);
  $("low24").textContent = money(data.low_24h);
  $("volume24").textContent = moneyVol(data.volume_24h);

  renderTrade(data.trade, data.bias);
  renderDeep(data.deep);

  $("overallTrend").textContent = data.overall_trend;
  $("trendSummary").textContent = data.trend_summary;
  renderTimeframes(data.timeframes);
  renderMacd(data.timeframes);

  if (data.volatility) {
    const v = data.volatility;
    $("volLevel").textContent = v.level;
    $("volDesc").textContent = v.description;
    $("atr").textContent = money(v.atr_14);
    $("atrPct").textContent = v.atr_percent + "%";
    $("dailyVol").textContent = v.daily_volatility_pct + "%";
    $("range24").textContent = v.range_24h_pct + "%";
  }

  if (data.funding) {
    const f = data.funding;
    const rateEl = $("fundingRate");
    const signF = f.rate_percent >= 0 ? "+" : "";
    rateEl.textContent = signF + f.rate_percent.toFixed(4) + "%";
    rateEl.className = "funding-rate " + (f.rate_percent >= 0 ? "positive" : "negative");
    $("fundingQuality").textContent = f.quality || "—";
    $("fundingLong").textContent = f.long_action || "—";
    $("fundingLong").className = verdictClass(f.long_action);
    $("fundingShort").textContent = f.short_action || "—";
    $("fundingShort").className = verdictClass(f.short_action);
    $("fundingSummary").textContent = f.summary || f.sentiment || "—";
    $("markPrice").textContent = money(f.mark_price);
    $("indexPrice").textContent = money(f.index_price);
    $("openInterest").textContent = f.open_interest != null ? formatVolume(f.open_interest) : "—";
    $("nextFunding").textContent = String(f.next_funding_time).replace("T", " ").slice(0, 19);
  } else {
    $("fundingRate").textContent = "Недоступен";
    $("fundingQuality").textContent = "—";
    $("fundingLong").textContent = "—";
    $("fundingShort").textContent = "—";
    $("fundingSummary").textContent = "Нет фьючерсной пары";
    $("markPrice").textContent = "—";
    $("indexPrice").textContent = "—";
    $("openInterest").textContent = "—";
    $("nextFunding").textContent = "—";
  }

  renderFibonacci(data.fibonacci, data.price);
  renderLevels("resistance", data.resistance_levels);
  renderLevels("support", data.support_levels);
  renderSignals(data.signals);
  renderScalping(data.scalp);
  renderAccuracy(data.accuracy);

  const label = data.display_name || data.symbol;
  $("currentPair").textContent = label + (data.market_type ? " · " + data.market_type : "");

  lastMarketPrice = data.price;
  applyI18n();
}

async function analyze(pair, forceRefresh = false) {
  if (!pair || !pair.trim()) return;

  pair = normalizePairInput(pair, activeMarket);
  activePair = pair;
  $("customPair").value = pair;
  $("btnRefresh").disabled = false;
  setActiveButton(pair);
  setLoading(true);

  try {
    let url =
      "/api/analyze?pair=" + encodeURIComponent(pair) + "&market=" + encodeURIComponent(activeMarket);
    if (forceRefresh) url += "&refresh=1";
    const res = await fetch(url);
    const json = await res.json();
    setLoading(false);

    if (!json.ok) {
      showError(json.error || "Ошибка загрузки");
      return;
    }
    render(json.data);
    loadedMarket = activeMarket;
    _lastAnalysisRefresh = Date.now();
    lastAnalysisData = {
      ...json.data,
      position_preview: json.position_preview,
      tv_symbol: json.data.tv_symbol || json.tv_symbol,
    };
    renderVerdict(lastAnalysisData);

    const tvSym = json.data.tv_symbol || json.tv_symbol || "BINANCE:ETHUSDT";
    const tvLabel = $("tvSymbolLabel");
    if (tvLabel) tvLabel.textContent = json.data.display_name || pair;
    updateTvLink(tvSym);

    await loadChartsForPair(pair, json.data.market_type);
    setTimeout(() => TradingChart.resize?.(), 120);
    updateChartTrend(json.data);

    $("newsAiResult")?.classList.add("hidden");
    if (activeView === "news") loadNews();
  } catch (e) {
    setLoading(false);
    showError("Не удалось подключиться к серверу");
  }
}

// Лёгкое обновление анализа (стоп/тейк/балл/вердикт) БЕЗ перезагрузки свечей.
let _lastAnalysisRefresh = 0;
async function refreshAnalysis() {
  if (!activePair || activeView !== "market" || document.hidden) return;
  try {
    const url =
      "/api/analyze?pair=" + encodeURIComponent(activePair) +
      "&market=" + encodeURIComponent(activeMarket) + "&refresh=1";
    const json = await (await fetch(url)).json();
    if (!json.ok) return;
    render(json.data);
    lastAnalysisData = {
      ...json.data,
      position_preview: json.position_preview,
      tv_symbol: json.data.tv_symbol || json.tv_symbol,
    };
    renderVerdict(lastAnalysisData);
    updateChartTrend(json.data); // перерисует зоны входа (стоп/тейк) и тренд-бар
    _lastAnalysisRefresh = Date.now();
  } catch (e) {
    /* тихо — следующий тик попробует снова */
  }
}

// Вызывается из chart.js по таймеру (каждые ~8с), но реально обновляет анализ
// не чаще раза в ~45с, чтобы не перегружать источники данных.
function onLiveRefresh() {
  if (Date.now() - _lastAnalysisRefresh < 45000) return;
  refreshAnalysis();
}

document.querySelectorAll("#mainNav .nav-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    const view = btn.dataset.view;
    if (view === "market") {
      if (btn.dataset.market !== activeMarket) {
        instrumentSearchQuery = "";
        if ($("instrumentSearch")) $("instrumentSearch").value = "";
      }
      switchView("market", btn.dataset.market);
    } else {
      switchView(view);
    }
  });
});

document.querySelectorAll(".btn-region").forEach((btn) => {
  btn.addEventListener("click", () => {
    activeStockRegion = btn.dataset.region;
    document.querySelectorAll(".btn-region").forEach((b) => b.classList.toggle("active", b === btn));
    renderPairsGrid("stock");
    const first = getFirstInstrumentId("stock");
    if (first) analyze(first);
  });
});

let _searchTimer = null;
$("instrumentSearch")?.addEventListener("input", (e) => {
  instrumentSearchQuery = e.target.value;
  const q = instrumentSearchQuery.trim();
  clearTimeout(_searchTimer);
  if (!q) {
    renderPairsGrid(activeMarket);
    return;
  }
  _searchTimer = setTimeout(() => searchInstrumentsRemote(q), 250);
});

$("btnAnalyze").addEventListener("click", () => analyze($("customPair").value));
$("btnRefresh").addEventListener("click", () => activePair && analyze(activePair, true));

$("customPair").addEventListener("keydown", (e) => {
  if (e.key === "Enter") analyze($("customPair").value);
});

document.querySelectorAll(".panel-tabs button").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

document.querySelectorAll("#newsRange button").forEach((btn) => {
  btn.addEventListener("click", () => {
    activeNewsRange = btn.dataset.range;
    document.querySelectorAll("#newsRange button").forEach((b) => b.classList.toggle("active", b === btn));
    $("newsAiResult")?.classList.add("hidden");
    loadNews();
  });
});

document.querySelectorAll("#moversMarkets button").forEach((btn) => {
  btn.addEventListener("click", () => {
    moversMarket = btn.dataset.market;
    document.querySelectorAll("#moversMarkets button").forEach((b) => b.classList.toggle("active", b === btn));
    $("moversRegion")?.classList.toggle("hidden", moversMarket !== "stock");
    loadMovers();
  });
});
document.querySelectorAll("#moversRegion button").forEach((btn) => {
  btn.addEventListener("click", () => {
    moversRegion = btn.dataset.region;
    document.querySelectorAll("#moversRegion button").forEach((b) => b.classList.toggle("active", b === btn));
    loadMovers();
  });
});
document.querySelectorAll("#moversRange button").forEach((btn) => {
  btn.addEventListener("click", () => {
    moversRange = btn.dataset.range;
    document.querySelectorAll("#moversRange button").forEach((b) => b.classList.toggle("active", b === btn));
    loadMovers();
  });
});
$("moversRefresh")?.addEventListener("click", () => loadMovers(true));

$("btnNewsAi")?.addEventListener("click", () => loadNewsAi());
$("btnJournalAdd")?.addEventListener("click", () => saveSignal());
$("btnJournalRefresh")?.addEventListener("click", () => loadJournal());

let entryConfig = {};

function applyEntryConfig() {
  if (TradingChart.setEntryConfig) TradingChart.setEntryConfig(entryConfig);
  const anyOn = Object.values(entryConfig).some((c) => c.entry || c.stop || c.take);
  $("btnEntryPoints")?.classList.toggle("active", anyOn);
}

function buildEntryMenu(longs, shorts) {
  const menu = $("entryMenu");
  if (!menu) return;
  const rows = [];
  (longs || []).slice(0, 3).forEach((z, i) => rows.push({ id: "L" + (i + 1), label: "ЛОНГ " + (i + 1), cls: "long" }));
  (shorts || []).slice(0, 3).forEach((z, i) => rows.push({ id: "S" + (i + 1), label: "ШОРТ " + (i + 1), cls: "short" }));

  // сохраняем прежние настройки для тех же id, новым — дефолт (вход вкл)
  const next = {};
  rows.forEach((r) => {
    next[r.id] = entryConfig[r.id] || { entry: true, stop: false, take: false };
  });
  entryConfig = next;

  if (!rows.length) {
    menu.innerHTML = '<div class="em-empty">Нет зон входа</div>';
    return;
  }

  let html = '<div class="em-head"><span>Зона</span><span>Вход</span><span>Стоп</span><span>Тейк</span></div>';
  html +=
    '<div class="em-row em-all"><span class="em-label">Все</span>' +
    '<input type="checkbox" data-act="entry"><input type="checkbox" data-act="stop"><input type="checkbox" data-act="take"></div>';
  rows.forEach((r) => {
    const c = entryConfig[r.id];
    html +=
      `<div class="em-row"><span class="em-label em-${r.cls}">${r.label}</span>` +
      `<input type="checkbox" data-id="${r.id}" data-k="entry" ${c.entry ? "checked" : ""}>` +
      `<input type="checkbox" data-id="${r.id}" data-k="stop" ${c.stop ? "checked" : ""}>` +
      `<input type="checkbox" data-id="${r.id}" data-k="take" ${c.take ? "checked" : ""}></div>`;
  });
  menu.innerHTML = html;

  menu.querySelectorAll("input[data-id]").forEach((cb) => {
    cb.addEventListener("change", () => {
      entryConfig[cb.dataset.id][cb.dataset.k] = cb.checked;
      applyEntryConfig();
    });
  });
  menu.querySelectorAll("input[data-act]").forEach((cb) => {
    cb.addEventListener("change", () => {
      const k = cb.dataset.act;
      Object.keys(entryConfig).forEach((id) => (entryConfig[id][k] = cb.checked));
      menu.querySelectorAll(`input[data-k="${k}"]`).forEach((x) => (x.checked = cb.checked));
      applyEntryConfig();
    });
  });

  applyEntryConfig();
}

$("btnEntryPoints")?.addEventListener("click", (e) => {
  e.stopPropagation();
  $("entryMenu")?.classList.toggle("hidden");
});
document.addEventListener("click", (e) => {
  const dd = $("entryDropdown");
  if (dd && !dd.contains(e.target)) $("entryMenu")?.classList.add("hidden");
});

document.querySelectorAll("#modeToggle button").forEach((b) => {
  b.addEventListener("click", () => applyMode(b.dataset.mode));
});

$("langToggle")?.addEventListener("click", () => {
  window.I18N?.setLang(I18N.get() === "en" ? "ru" : "en");
});

// Вызывается из i18n.js при смене языка: перерисовываем данные и перезагружаем
// новости/AI на нужном языке.
window.onLangChange = () => {
  if (lastAnalysisData) {
    render(lastAnalysisData);
    renderVerdict(lastAnalysisData);
    updateChartTrend(lastAnalysisData);
  }
  $("newsAiResult")?.classList.add("hidden");
  if (activeView === "news") loadNews();
  else if (activeView === "journal") loadJournal();
  else if (activeView === "movers") loadMovers();
  applyI18n();
};

function applyI18n() {
  if (window.I18N) I18N.apply(document.body);
}

function L(v) {
  return window.I18N ? I18N.tr(v) : v;
}

// ---- Модальные окна: Политика конфиденциальности и Info ----
const MODAL_CONTENT = {
  ru: {
    privacy: {
      title: "Политика конфиденциальности",
      html: `
        <p>Trading Info Stats (TIS) — сервис рыночной аналитики. Мы уважаем вашу приватность.</p>
        <ul>
          <li><b>Без регистрации и аккаунтов.</b> Мы не собираем имена, email, телефоны и иные персональные данные.</li>
          <li><b>Локальное хранение.</b> В браузере (localStorage) сохраняются только настройки интерфейса: язык, режим Простой/Про. Эти данные не покидают ваше устройство.</li>
          <li><b>Сторонние источники.</b> Котировки и новости поступают от Binance, Yahoo Finance, Московской биржи (MOEX) и Google News; AI-разбор — через OpenAI. На эти сервисы распространяются их собственные политики.</li>
          <li><b>Без рекламных трекеров.</b> Сервис не использует рекламные пиксели и не продаёт данные.</li>
        </ul>
        <p class="modal-note">Сервис носит информационный характер и не является финансовой рекомендацией. Торговля сопряжена с риском.</p>`,
    },
    info: {
      title: "О сервисе",
      html: `
        <p><b>Trading Info Stats (TIS)</b> — терминал рыночной аналитики для крипты, акций (США и Россия) и валютных пар.</p>
        <ul>
          <li>Технический анализ: тренд, MACD, RSI, ADX, волатильность, Фибоначчи, уровни.</li>
          <li>Зоны входа со стопом и тейком прямо на графике.</li>
          <li>Новости с разметкой тональности и AI-разбором со ссылками на источники.</li>
          <li>Журнал сигналов с автопроверкой исходов по истории цены.</li>
          <li>«Обзор рынка» — лидеры роста и падения за день/месяц/год.</li>
        </ul>
        <p>Данные: Binance, Yahoo Finance, MOEX, Google News, OpenAI.</p>
        <p>Telegram-канал: <a href="https://t.me/TradingInfoStats" target="_blank" rel="noopener">@TradingInfoStats</a></p>
        <p class="modal-note">⚠️ Не является индивидуальной инвестиционной рекомендацией.</p>`,
    },
  },
  en: {
    privacy: {
      title: "Privacy policy",
      html: `
        <p>Trading Info Stats (TIS) is a market-analytics service. We respect your privacy.</p>
        <ul>
          <li><b>No sign-up, no accounts.</b> We don't collect names, emails, phone numbers or other personal data.</li>
          <li><b>Local storage only.</b> The browser (localStorage) keeps only UI preferences: language and Simple/Pro mode. This data never leaves your device.</li>
          <li><b>Third-party sources.</b> Quotes and news come from Binance, Yahoo Finance, Moscow Exchange (MOEX) and Google News; AI review via OpenAI. Their own policies apply.</li>
          <li><b>No ad trackers.</b> The service uses no advertising pixels and does not sell data.</li>
        </ul>
        <p class="modal-note">For informational purposes only — not financial advice. Trading involves risk.</p>`,
    },
    info: {
      title: "About",
      html: `
        <p><b>Trading Info Stats (TIS)</b> is a market-analytics terminal for crypto, stocks (US & Russia) and forex pairs.</p>
        <ul>
          <li>Technical analysis: trend, MACD, RSI, ADX, volatility, Fibonacci, levels.</li>
          <li>Entry zones with stop and take-profit drawn on the chart.</li>
          <li>News with sentiment tagging and AI review linked to sources.</li>
          <li>Signal journal with automatic outcome checking against price history.</li>
          <li>"Market overview" — top gainers and losers for day/month/year.</li>
        </ul>
        <p>Data: Binance, Yahoo Finance, MOEX, Google News, OpenAI.</p>
        <p>Telegram: <a href="https://t.me/TradingInfoStats" target="_blank" rel="noopener">@TradingInfoStats</a></p>
        <p class="modal-note">⚠️ Not individual investment advice.</p>`,
    },
  },
};

// ---- Гайд-карусель: свайп + стрелки + точки, с визуальными мини-превью ----
const _GV = {
  market: `<div class="gv-tabs"><span class="gv-tab active">Крипта</span><span class="gv-tab">Акции</span><span class="gv-tab">Валюта</span></div>`,
  sides: `<div class="gv-badges"><span class="gv-badge buy">ПОКУПАТЬ</span><span class="gv-badge sell">ПРОДАВАТЬ</span><span class="gv-badge wait">ЖДАТЬ</span></div>`,
  entries: `<div class="gv-legend"><span><i style="background:#2dd4bf"></i>вход лонг</span><span><i style="background:#a855f7"></i>вход шорт</span><span><i style="background:#ef4444"></i>стоп</span><span><i style="background:#22c55e"></i>тейк</span></div>`,
  score: `<div class="gv-ring"><div class="gv-ring-in">78<small>/100</small></div></div>`,
  pro: `<div class="gv-chips"><span>MACD</span><span>RSI</span><span>ADX</span><span>Fibo</span><span>ATR</span></div>`,
  movers: `<div class="gv-movers"><span class="up">BTC +5.2%</span><span class="up">SOL +3.1%</span><span class="down">XRP −2.4%</span></div>`,
  news: `<div class="gv-news"><span class="gv-nb good">Хорошая</span><span class="gv-nb bad">Плохая</span></div>`,
  journal: `<div class="gv-stat"><span>Винрейт</span><b class="up">62%</b><span>Профит-фактор</span><b>1.8</b></div>`,
};

const GUIDE_SLIDES = {
  ru: [
    { v: _GV.market, t: "Выбор рынка", d: "Вверху выберите рынок — Крипта, Акции или Валюта. Инструмент берите из полосы сверху или вбейте в поиск: доступны все пары Binance и все бумаги MOEX." },
    { v: _GV.sides, t: "Лонг и Шорт", d: "ПОКУПАТЬ (лонг) — ставка на рост цены. ПРОДАВАТЬ (шорт) — на падение. ЖДАТЬ — чёткого сигнала нет, лучше не входить." },
    { v: _GV.entries, t: "Точки входа, стоп, тейк", d: "На графике: бирюзовые линии — вход в лонг, фиолетовые — вход в шорт, красные — стоп-лосс, зелёные — тейк-профит. Что показывать — настройте кнопкой «Точки входа»." },
    { v: _GV.score, t: "Балл согласованности", d: "0–100: насколько согласованы сигналы (таймфреймы, индикаторы, бэктест 4H). Чем выше — тем «чище» картина. Это НЕ вероятность прибыли." },
    { v: _GV.pro, t: "Режим «Про»", d: "Переключите «Простой → Про» вверху, чтобы увидеть глубокий анализ: тренды по ТФ, MACD/RSI, волатильность, Фибоначчи, сценарии и уровни." },
    { v: _GV.movers, t: "Обзор рынка", d: "Лидеры роста и падения за день / месяц / год (как cryptobubbles). Клик по карточке открывает график и анализ инструмента." },
    { v: _GV.news, t: "Новости + AI", d: "Хорошие и плохие новости по инструменту, плюс AI-разбор с подтверждающими ссылками на источники." },
    { v: _GV.journal, t: "Журнал сигналов", d: "Нажмите «Записать сигнал» — система сама проверит по истории цены, что сработало первым (тейк или стоп), и посчитает реальный винрейт." },
  ],
  en: [
    { v: _GV.market.replace("Крипта", "Crypto").replace("Акции", "Stocks").replace("Валюта", "Forex"), t: "Pick a market", d: "Choose Crypto, Stocks or Forex at the top. Pick an instrument from the strip or type in search — all Binance pairs and all MOEX stocks are available." },
    { v: _GV.sides.replace("ПОКУПАТЬ", "BUY").replace("ПРОДАВАТЬ", "SELL").replace("ЖДАТЬ", "WAIT"), t: "Long and Short", d: "BUY (long) — betting the price rises. SELL (short) — betting it falls. WAIT — no clear signal, better stay out." },
    { v: `<div class="gv-legend"><span><i style="background:#2dd4bf"></i>long entry</span><span><i style="background:#a855f7"></i>short entry</span><span><i style="background:#ef4444"></i>stop</span><span><i style="background:#22c55e"></i>take</span></div>`, t: "Entry, stop, take", d: "On the chart: turquoise — long entry, purple — short entry, red — stop-loss, green — take-profit. Configure via the “Entry points” button." },
    { v: _GV.score, t: "Agreement score", d: "0–100: how aligned the signals are (timeframes, indicators, 4H backtest). Higher = cleaner picture. This is NOT a probability of profit." },
    { v: _GV.pro, t: "Pro mode", d: "Switch “Simple → Pro” to see deep analysis: per-TF trends, MACD/RSI, volatility, Fibonacci, scenarios and levels." },
    { v: _GV.movers, t: "Market overview", d: "Top gainers and losers for day / month / year (like cryptobubbles). Click a card to open its chart and analysis." },
    { v: `<div class="gv-news"><span class="gv-nb good">Good</span><span class="gv-nb bad">Bad</span></div>`, t: "News + AI", d: "Good and bad news per instrument, plus an AI review with supporting links to sources." },
    { v: `<div class="gv-stat"><span>Win rate</span><b class="up">62%</b><span>Profit factor</span><b>1.8</b></div>`, t: "Signal journal", d: "Click “Log signal” — the system checks price history for what hit first (take or stop) and computes a real win rate." },
  ],
};

function openGuide() {
  const lang = window.I18N ? I18N.get() : "ru";
  const slides = GUIDE_SLIDES[lang] || GUIDE_SLIDES.ru;
  $("modalTitle").textContent = lang === "en" ? "Guide: how to use" : "Гайд: как пользоваться";
  const total = slides.length;
  const slidesHtml = slides.map((s, i) =>
    `<div class="guide-slide"><div class="guide-visual">${s.v}</div>` +
    `<div class="gs-step">${i + 1} / ${total}</div><h3>${s.t}</h3><p>${s.d}</p></div>`
  ).join("");
  const dots = slides.map((_, i) => `<span class="gd${i === 0 ? " active" : ""}" data-i="${i}"></span>`).join("");
  $("modalBody").innerHTML =
    `<div class="guide-viewport"><div class="guide-track" id="guideTrack">${slidesHtml}</div></div>` +
    `<div class="guide-nav"><button type="button" class="guide-arrow" id="guidePrev">‹</button>` +
    `<div class="guide-dots" id="guideDots">${dots}</div>` +
    `<button type="button" class="guide-arrow" id="guideNext">›</button></div>`;
  document.querySelector("#modalOverlay .modal")?.classList.add("wide");
  $("modalOverlay").classList.remove("hidden");
  _initGuideNav(total);
}

function _initGuideNav(total) {
  let idx = 0;
  const track = $("guideTrack");
  const dots = Array.from(document.querySelectorAll("#guideDots .gd"));
  const go = (n) => {
    idx = Math.max(0, Math.min(total - 1, n));
    if (track) track.style.transform = `translateX(-${idx * 100}%)`;
    dots.forEach((d, i) => d.classList.toggle("active", i === idx));
  };
  $("guidePrev")?.addEventListener("click", () => go(idx - 1));
  $("guideNext")?.addEventListener("click", () => go(idx + 1));
  dots.forEach((d) => d.addEventListener("click", () => go(+d.dataset.i)));
  // свайп
  let x0 = null;
  const vp = document.querySelector(".guide-viewport");
  vp?.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; }, { passive: true });
  vp?.addEventListener("touchend", (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 40) go(idx + (dx < 0 ? 1 : -1));
    x0 = null;
  });
  // мышь-перетаскивание
  let mx0 = null;
  vp?.addEventListener("mousedown", (e) => { mx0 = e.clientX; });
  window.addEventListener("mouseup", (e) => {
    if (mx0 === null) return;
    const dx = e.clientX - mx0;
    if (Math.abs(dx) > 50) go(idx + (dx < 0 ? 1 : -1));
    mx0 = null;
  });
  // стрелки клавиатуры
  _guideKeyHandler = (e) => {
    if ($("modalOverlay")?.classList.contains("hidden")) return;
    if (e.key === "ArrowLeft") go(idx - 1);
    if (e.key === "ArrowRight") go(idx + 1);
  };
  document.addEventListener("keydown", _guideKeyHandler);
}
let _guideKeyHandler = null;

function openModal(key) {
  const lang = window.I18N ? I18N.get() : "ru";
  const c = (MODAL_CONTENT[lang] || MODAL_CONTENT.ru)[key];
  if (!c) return;
  $("modalTitle").textContent = c.title;
  $("modalBody").innerHTML = c.html;
  document.querySelector("#modalOverlay .modal")?.classList.toggle("wide", key === "guide");
  $("modalOverlay").classList.remove("hidden");
}
function closeModal() {
  $("modalOverlay")?.classList.add("hidden");
}
$("linkPrivacy")?.addEventListener("click", () => openModal("privacy"));
$("linkInfo")?.addEventListener("click", () => openModal("info"));
$("linkGuide")?.addEventListener("click", () => openGuide());
$("modalClose")?.addEventListener("click", closeModal);
$("modalOverlay")?.addEventListener("click", (e) => {
  if (e.target === $("modalOverlay")) closeModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});

document.querySelectorAll(".btn-interval").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".btn-interval").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    tvInterval = btn.dataset.interval;
    if (tvReady) TradingViewWidget.setInterval(tvInterval);
    const lwMap = { "5": "5m", "15": "15m", "60": "1h", "240": "4h", D: "1d" };
    const lwTf = lwMap[tvInterval];
    if (lwReady && activePair && lwTf) {
      TradingChart.loadPair(activePair, activeMarket, lwTf);
    }
  });
});

$("tvDetails")?.addEventListener("toggle", () => {
  if (!$("tvDetails")?.open || !lastAnalysisData) return;
  initTradingViewLazy();
  const sym =
    lastAnalysisData.tv_symbol ||
    (activePair && activeMarket === "crypto" ? `BINANCE:${activePair.replace("/", "")}` : null);
  if (sym) TradingViewWidget.setSymbol(sym, tvInterval);
});

document.addEventListener("DOMContentLoaded", () => {
  initLightweightChartOnce();
  let savedMode = "simple";
  try {
    savedMode = localStorage.getItem("ui_mode") || "simple";
  } catch (e) {}
  applyMode(savedMode);
  window.I18N?.init();
  $("fundingPanel")?.classList.add("hidden");
  switchTab("overview");
  // Стартуем на рыночной вкладке (крипта), грузим инструмент по умолчанию.
  activeView = "market";
  activeMarket = "crypto";
  renderPairsGrid("crypto");
  analyze("ETH/USDT");
});
