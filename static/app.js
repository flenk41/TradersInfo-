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
  $("verdictConf").textContent = acc != null ? acc : "—";
  const card = $("verdictCard");
  if (card) { card.classList.remove("v-buy", "v-sell", "v-wait"); card.classList.add("v-" + cls); }
  const ring = $("verdictConfRing");
  if (ring) {
    ring.classList.remove("v-buy", "v-sell", "v-wait");
    ring.classList.add("v-" + cls);
    ring.style.setProperty("--pct", acc != null ? acc : 0);
  }
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
    const cfg = getAiCfg();
    const url = `/api/news-ai?pair=${encodeURIComponent(activePair)}&market=${encodeURIComponent(activeMarket)}&range=${activeNewsRange}&lang=${lang}`;
    const json = await (await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ai_key: cfg.key || "", ai_base: cfg.base || "", ai_model: cfg.model || "" }),
    })).json();
    if (json.ok) {
      renderNewsAi(json.ai);
    } else if (json.need_key) {
      box.innerHTML = `<p class="news-empty">${json.error || "Нужен AI-ключ"}</p>` +
        `<button type="button" class="btn-primary" id="aiOpenFromNews">🔑 AI-ключ</button>`;
      $("aiOpenFromNews")?.addEventListener("click", openAiKeyModal);
    } else {
      box.innerHTML = `<p class="news-empty">${json.error || "AI-анализ недоступен"}</p>`;
    }
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

// ---- Запись сигнала: реальная цена входа пользователя + стоп/тейк от неё ----
let jaddState = { side: "long", levels: null, recalcTimer: null };

function openJournalAdd() {
  if (!lastAnalysisData || !activePair) {
    showError("Сначала выберите инструмент и нажмите «Анализ»");
    return;
  }
  const sigPair = lastAnalysisData.pair || activePair;
  if (activePair && sigPair !== activePair) {
    showError("Анализ ещё не обновился для текущего инструмента — нажмите «Анализ» и повторите");
    return;
  }
  let side = lastAnalysisData.accuracy?.recommended_side;
  if (side !== "long" && side !== "short") side = activeSide || "long";
  jaddState.side = side;
  $("jaddPair").textContent = (lastAnalysisData.display_name || sigPair) + " · " + (side === "long" ? "ЛОНГ 📈" : "ШОРТ 📉");
  document.querySelectorAll("#jaddSide button").forEach((b) => b.classList.toggle("active", b.dataset.side === side));
  // По умолчанию — текущая рыночная цена (где человек реально входит сейчас).
  $("jaddEntry").value = lastAnalysisData.price != null ? lastAnalysisData.price : "";
  $("jaddLevels").innerHTML = "";
  $("journalAddOverlay").classList.remove("hidden");
  jaddRecalc();
}

function closeJournalAdd() { $("journalAddOverlay")?.classList.add("hidden"); }

async function jaddRecalc() {
  const entry = parseFloat($("jaddEntry").value);
  const box = $("jaddLevels");
  if (isNaN(entry) || entry <= 0) {
    box.innerHTML = "";
    jaddState.levels = null;
    return;
  }
  const pair = lastAnalysisData.pair || activePair;
  const market = lastAnalysisData.market || activeMarket;
  box.innerHTML = '<div class="dr-row"><span>Расчёт уровней…</span><b>…</b></div>';
  try {
    const r = await fetch("/api/position", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pair, market, entry, side: jaddState.side, margin: 100, leverage: 10 }),
    });
    const j = await r.json();
    if (!j.ok || !j.position) { box.innerHTML = `<div class="dr-row bad"><span>${j.error || "Не удалось рассчитать"}</span><b>—</b></div>`; jaddState.levels = null; return; }
    const p = j.position;
    jaddState.levels = { entry, stop: p.stop_loss, take_profit: p.take_profit, take_profit_2: p.take_profit_2, rr: p.risk_reward };
    const cur = (typeof curSymbol !== "undefined" ? "" : "");
    const f = (v) => (v != null ? money(v) : "—");
    const slPct = entry ? Math.abs((p.stop_loss - entry) / entry * 100).toFixed(2) : "—";
    const tpPct = entry ? Math.abs((p.take_profit - entry) / entry * 100).toFixed(2) : "—";
    box.innerHTML =
      `<div class="dr-row bad"><span>Стоп-лосс (−${slPct}%)</span><b>${f(p.stop_loss)}</b></div>` +
      `<div class="dr-row good"><span>Тейк-профит (+${tpPct}%)</span><b>${f(p.take_profit)}</b></div>` +
      (p.take_profit_2 != null ? `<div class="dr-row"><span>Тейк 2</span><b>${f(p.take_profit_2)}</b></div>` : "") +
      `<div class="dr-row"><span>R:R</span><b>1:${p.risk_reward}</b></div>`;
  } catch (e) {
    box.innerHTML = `<div class="dr-row bad"><span>Ошибка сети</span><b>—</b></div>`;
    jaddState.levels = null;
  }
}

async function confirmJournalAdd() {
  if (!lastAnalysisData) return;
  const lvl = jaddState.levels;
  if (!lvl || lvl.stop == null || lvl.take_profit == null) {
    showError("Укажите корректную цену входа");
    return;
  }
  const sigPair = lastAnalysisData.pair || activePair;
  const payload = {
    pair: sigPair,
    market: lastAnalysisData.market || activeMarket,
    display: lastAnalysisData.display_name || sigPair,
    side: jaddState.side,
    entry: lvl.entry,
    stop: lvl.stop,
    take_profit: lvl.take_profit,
    take_profit_2: lvl.take_profit_2,
    rr: lvl.rr,
    accuracy_pct: lastAnalysisData.accuracy?.overall_pct,
  };
  try {
    const json = await (await fetch("/api/journal/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })).json();
    if (json.ok) {
      closeJournalAdd();
      switchView("journal");
      loadJournal();
    } else {
      showError(json.error || "Не удалось записать сигнал");
    }
  } catch (e) {
    showError("Не удалось записать сигнал");
  }
}

// Подсказка про AI-ключ во вкладке «Новости».
function updateNewsAiHint() {
  const el = $("newsAiHint");
  if (!el) return;
  const en = window.I18N && I18N.get() === "en";
  if (getAiCfg().key) {
    el.textContent = en ? "AI summary with supporting links" : "Сводка по новостям с подтверждающими ссылками";
    el.classList.remove("news-ai-need");
  } else {
    el.textContent = en ? "🔑 Free AI key needed — click to connect" : "🔑 Нужен бесплатный AI-ключ — подключить";
    el.classList.add("news-ai-need");
  }
}
$("newsAiHint")?.addEventListener("click", () => {
  if (!getAiCfg().key && typeof openAiKeyModal === "function") openAiKeyModal();
});

let newsLoading = false;
async function loadNews() {
  updateNewsAiHint();
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

// ---- Скринер ----
let scrMarket = "crypto", scrRegion = "ru", scrTf = "1d", scrRows = [], scrLoading = false;
let scrSort = { key: "change_pct", dir: "desc" };
const SCR_SIGNAL = {
  bull_pullback: { ru: "Бычий откат", en: "Bull pullback", cls: "good" },
  bear_pullback: { ru: "Медвежий откат", en: "Bear pullback", cls: "bad" },
  oversold: { ru: "Перепродан", en: "Oversold", cls: "good" },
  overbought: { ru: "Перекуплен", en: "Overbought", cls: "bad" },
  uptrend: { ru: "Восходящий", en: "Uptrend", cls: "good" },
  downtrend: { ru: "Нисходящий", en: "Downtrend", cls: "bad" },
  flat: { ru: "Флэт", en: "Flat", cls: "neutral" },
};
const SCR_TREND = { bull: { ru: "Бычий", en: "Bull", cls: "good" }, bear: { ru: "Медвежий", en: "Bear", cls: "bad" }, flat: { ru: "Флэт", en: "Flat", cls: "neutral" } };

async function loadScreener(force) {
  const table = $("scrTable");
  if (!table || (scrLoading && !force)) return;
  scrLoading = true;
  table.innerHTML = '<p class="news-empty">Считаю сигналы по инструментам…</p>';
  try {
    let url = `/api/screener?market=${scrMarket}&tf=${scrTf}`;
    if (scrMarket === "stock") url += `&region=${scrRegion}`;
    const json = await (await fetch(url)).json();
    if (json.ok) { scrRows = json.items || []; applyScreenerFilters(); }
    else table.innerHTML = `<p class="news-empty">${json.error || "Ошибка"}</p>`;
  } catch (e) {
    table.innerHTML = '<p class="news-empty">Не удалось загрузить скринер.</p>';
  } finally {
    scrLoading = false;
  }
}

function applyScreenerFilters() {
  const trend = $("scrTrend")?.value || "any";
  const signal = $("scrSignal")?.value || "any";
  const rsiMax = parseFloat($("scrRsiMax")?.value);
  const rsiMin = parseFloat($("scrRsiMin")?.value);
  const chgMin = parseFloat($("scrChgMin")?.value);
  const rows = scrRows.filter((r) => {
    if (trend !== "any" && r.trend !== trend) return false;
    if (signal !== "any" && r.signal !== signal) return false;
    if (!isNaN(rsiMax) && r.rsi > rsiMax) return false;
    if (!isNaN(rsiMin) && r.rsi < rsiMin) return false;
    if (!isNaN(chgMin) && r.change_pct < chgMin) return false;
    return true;
  });
  const k = scrSort.key, mul = scrSort.dir === "asc" ? 1 : -1;
  rows.sort((a, b) => {
    const av = a[k], bv = b[k];
    if (typeof av === "string") return mul * String(av).localeCompare(String(bv));
    return mul * ((av || 0) - (bv || 0));
  });
  renderScreenerRows(rows);
}

function _setScrSort(key) {
  if (scrSort.key === key) scrSort.dir = scrSort.dir === "asc" ? "desc" : "asc";
  else scrSort = { key, dir: key === "name" ? "asc" : "desc" };
  applyScreenerFilters();
}

function renderScreenerRows(rows) {
  const table = $("scrTable");
  const cnt = $("scrCount");
  const en = window.I18N && I18N.get() === "en";
  if (cnt) cnt.textContent = `${rows.length} / ${scrRows.length}`;
  if (!rows.length) {
    table.innerHTML = '<p class="news-empty">Ничего не подходит под фильтры.</p>';
    return;
  }
  const arrow = (key) => (scrSort.key === key ? (scrSort.dir === "asc" ? " ▲" : " ▼") : "");
  const sortable = (key, label) => `<span class="scr-sortable${scrSort.key === key ? " active" : ""}" data-sort="${key}">${label}${arrow(key)}</span>`;
  const head = `<div class="scr-row scr-head">` +
    sortable("name", en ? "Instrument" : "Инструмент") +
    sortable("price", en ? "Price" : "Цена") +
    sortable("change_pct", "Δ%") +
    sortable("score", en ? "Score" : "Балл") +
    sortable("rsi", "RSI") +
    `<span>${en ? "Trend" : "Тренд"}</span>` +
    `<span>${en ? "Signal" : "Сигнал"}</span></div>`;
  table.innerHTML = head;
  table.querySelectorAll(".scr-head .scr-sortable").forEach((el) =>
    el.addEventListener("click", () => _setScrSort(el.dataset.sort))
  );
  rows.forEach((r) => {
    const tr = SCR_TREND[r.trend] || SCR_TREND.flat;
    const sg = SCR_SIGNAL[r.signal] || SCR_SIGNAL.flat;
    const up = r.change_pct >= 0;
    const row = document.createElement("button");
    row.type = "button";
    row.className = "scr-row";
    row.innerHTML =
      `<span class="scr-inst"><span class="inst-icon-wrap">${moverIconHtml(r)}</span><span class="scr-name">${r.name}<small>${r.subtitle}</small></span></span>` +
      `<span>${moverCurrency(r)}${formatPrice(r.price)}</span>` +
      `<span class="${up ? "up" : "down"}">${up ? "+" : ""}${r.change_pct}%</span>` +
      `<span class="scr-score ${r.score >= 70 ? "good" : r.score < 52 ? "weak" : "mid"}" title="Балл согласованности сигналов (лёгкая оценка, не вероятность прибыли)">${r.score != null ? r.score : "—"}</span>` +
      `<span class="scr-rsi ${r.rsi >= 70 ? "down" : r.rsi <= 30 ? "up" : ""}">${r.rsi}</span>` +
      `<span class="chip-${tr.cls}">${en ? tr.en : tr.ru}</span>` +
      `<span class="chip-${sg.cls}">${en ? sg.en : sg.ru}</span>`;
    row.addEventListener("click", () => {
      if (r.market === "stock") {
        activeStockRegion = r.region || activeStockRegion;
        document.querySelectorAll("#stockRegionTabs .btn-region").forEach((b) =>
          b.classList.toggle("active", b.dataset.region === activeStockRegion));
      }
      switchView("market", r.market);
      analyze(r.id);
    });
    table.appendChild(row);
  });
  applyI18n();
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
  if (tabId === "patterns") {
    patViewTf = currentLwTf();
    document.querySelectorAll("#patTf button").forEach((x) => x.classList.toggle("active", x.dataset.tf === patViewTf));
    renderPatternsView();
  }
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
  } else if (view === "screener") {
    if (!scrRows.length) loadScreener();
  } else if (view === "portfolio") {
    loadPortfolio();
  } else if (view === "news") {
    loadNews();
  } else if (view === "journal") {
    loadJournal();
  }
  toggleDividendBtn();
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
  applyEntryColors();
  lwReady = true;
}

// ---- Кастомные цвета линий входа (хранятся в браузере) ----
const DEFAULT_ENTRY_COLORS = {
  longEntry: "#2dd4bf", shortEntry: "#a855f7",
  longEntryApprox: "#5eead4", shortEntryApprox: "#c4b5fd",
};
function getEntryColors() {
  try { return Object.assign({}, DEFAULT_ENTRY_COLORS, JSON.parse(localStorage.getItem("chart_colors") || "{}")); }
  catch (e) { return Object.assign({}, DEFAULT_ENTRY_COLORS); }
}
function applyEntryColors() {
  TradingChart.setEntryColors?.(getEntryColors());
}
const _COLOR_FIELDS = [
  ["colLong", "longEntry", "dotLong"],
  ["colShort", "shortEntry", "dotShort"],
  ["colLongApprox", "longEntryApprox", "dotLongApprox"],
  ["colShortApprox", "shortEntryApprox", "dotShortApprox"],
];
function _syncColorDots() {
  _COLOR_FIELDS.forEach(([inp, , dot]) => {
    const d = $(dot); if (d) d.style.background = $(inp).value;
  });
}
function openColorsModal() {
  const cur = getEntryColors();
  _COLOR_FIELDS.forEach(([inp, key]) => { if ($(inp)) $(inp).value = cur[key]; });
  _syncColorDots();
  $("colorsOverlay").classList.remove("hidden");
}
function closeColorsModal() { $("colorsOverlay")?.classList.add("hidden"); }
function _previewColors() {
  const c = {};
  _COLOR_FIELDS.forEach(([inp, key]) => { c[key] = $(inp).value; });
  TradingChart.setEntryColors?.(c);
  _syncColorDots();
}
$("btnColors")?.addEventListener("click", openColorsModal);
$("colorsClose")?.addEventListener("click", closeColorsModal);
$("colorsOverlay")?.addEventListener("click", (e) => { if (e.target === $("colorsOverlay")) closeColorsModal(); });
_COLOR_FIELDS.forEach(([inp]) => $(inp)?.addEventListener("input", _previewColors));
$("colorsSave")?.addEventListener("click", () => {
  const c = {};
  _COLOR_FIELDS.forEach(([inp, key]) => { c[key] = $(inp).value; });
  try { localStorage.setItem("chart_colors", JSON.stringify(c)); } catch (e) {}
  applyEntryColors();
  closeColorsModal();
});
$("colorsReset")?.addEventListener("click", () => {
  try { localStorage.removeItem("chart_colors"); } catch (e) {}
  _COLOR_FIELDS.forEach(([inp, key]) => { if ($(inp)) $(inp).value = DEFAULT_ENTRY_COLORS[key]; });
  applyEntryColors();
  _syncColorDots();
});

async function loadChartsForPair(pair, marketType) {
  initLightweightChartOnce();
  const lwMap = { "5": "5m", "15": "15m", "60": "1h", "240": "4h", D: "1d" };
  const tf = lwMap[tvInterval] || "1h";
  await TradingChart.loadPair(pair, activeMarket, tf);
}

const LW_TF_MAP = { "5": "5m", "15": "15m", "60": "1h", "240": "4h", D: "1d" };
function currentLwTf() {
  return LW_TF_MAP[tvInterval] || "1h";
}
// Зоны входа под текущий таймфрейм графика (стоп/тейк масштабированы под ATR ТФ).
function zonesForTf(data) {
  const byTf = data && data.entry_zones_by_tf;
  const tf = currentLwTf();
  if (byTf && byTf[tf]) {
    return { long: byTf[tf].long || [], short: byTf[tf].short || [] };
  }
  return { long: (data && data.long_entry_zones) || [], short: (data && data.short_entry_zones) || [] };
}

// Имбаланс под текущий таймфрейм графика.
function imbalancesForTf(data) {
  const byTf = data && data.imbalances_by_tf;
  const tf = currentLwTf();
  if (byTf && byTf[tf]) return byTf[tf];
  return (data && data.imbalances) || [];
}

function updateChartTrend(data) {
  if (!data) return;
  const z = zonesForTf(data);
  const view = Object.assign({}, data, { long_entry_zones: z.long, short_entry_zones: z.short });
  TradingChart.applyAnalysis(view);
  buildEntryMenu(z.long, z.short);
  renderZonesStrip(view);
  TradingChart.setImbalances?.(imbalancesForTf(data));
  renderImbalance(data);
  if (document.querySelector('.panel-tabs button.active')?.dataset.tab === "patterns") renderPatternsView();
  applyI18n();
}

// ---- Свечные паттерны (картинки) ----
// Описание свечей: [x, highY, lowY, bodyTopY, bodyBottomY, цвет g/r/n]; viewBox высота 44.
const PATTERN_SHAPES = {
  doji: [40, [[20, 4, 42, 22, 25, "n"]]],
  marubozu_bull: [40, [[20, 6, 42, 8, 40, "g"]]],
  marubozu_bear: [40, [[20, 6, 42, 8, 40, "r"]]],
  hammer: [40, [[20, 8, 42, 8, 18, "g"]]],
  hanging_man: [40, [[20, 8, 42, 8, 18, "r"]]],
  shooting_star: [40, [[20, 2, 36, 26, 36, "r"]]],
  inv_hammer: [40, [[20, 2, 36, 26, 36, "g"]]],
  engulf_bull: [64, [[18, 14, 34, 20, 30, "r"], [44, 8, 40, 12, 38, "g"]]],
  engulf_bear: [64, [[18, 14, 34, 20, 30, "g"], [44, 8, 40, 12, 38, "r"]]],
  morning_star: [88, [[16, 6, 30, 8, 28, "r"], [44, 30, 42, 34, 37, "n"], [72, 10, 40, 14, 38, "g"]]],
  evening_star: [88, [[16, 14, 38, 16, 36, "g"], [44, 2, 14, 6, 9, "n"], [72, 8, 34, 10, 32, "r"]]],
  three_soldiers: [88, [[16, 24, 42, 28, 40, "g"], [44, 14, 32, 18, 30, "g"], [72, 4, 22, 8, 20, "g"]]],
  three_crows: [88, [[16, 2, 20, 4, 18, "r"], [44, 12, 30, 14, 28, "r"], [72, 22, 40, 24, 38, "r"]]],
};
const PATTERN_COL = { g: "#22c55e", r: "#ef4444", n: "#9aa7bd" };

function patternSvg(key) {
  const shape = PATTERN_SHAPES[key];
  if (!shape) return "";
  const [w, candles] = shape;
  let body = "";
  candles.forEach(([x, hi, lo, bt, bb, col]) => {
    const c = PATTERN_COL[col] || PATTERN_COL.n;
    body += `<line x1="${x}" y1="${hi}" x2="${x}" y2="${lo}" stroke="${c}" stroke-width="2"/>`;
    body += `<rect x="${x - 5}" y="${bt}" width="10" height="${Math.max(2, bb - bt)}" fill="${c}" rx="1"/>`;
  });
  return `<svg class="pat-svg" viewBox="0 0 ${w} 44" preserveAspectRatio="xMidYMid meet">${body}</svg>`;
}

let patViewTf = "1h";

function renderOutlook() {
  const box = $("patOutlook");
  if (!box) return;
  const en = window.I18N && I18N.get() === "en";
  const o = (lastAnalysisData && lastAnalysisData.pattern_outlook_by_tf && lastAnalysisData.pattern_outlook_by_tf[patViewTf]) || null;
  if (!o || !o.current_time) { box.innerHTML = ""; return; }
  const DIR = {
    up: { ru: "↑ Скорее зелёная (рост)", en: "↑ Likely green (up)", cls: "up" },
    down: { ru: "↓ Скорее красная (падение)", en: "↓ Likely red (down)", cls: "down" },
    neutral: { ru: "↔ Неопределённо", en: "↔ Uncertain", cls: "neutral" },
  };
  const CONF = { high: en ? "high" : "высокая", medium: en ? "medium" : "средняя", low: en ? "low" : "низкая" };
  const d = DIR[o.direction] || DIR.neutral;
  const curCls = o.current_bias === "bullish" ? "up" : "down";
  const curTxt = o.current_bias === "bullish" ? (en ? "green" : "зелёная") : (en ? "red" : "красная");
  const based = o.based_on_key ? `${en ? "by pattern" : "по паттерну"} «${en ? o.based_on_en : o.based_on_ru}», ${en ? "confidence" : "уверенность"} ${CONF[o.confidence] || ""}` : (en ? "no recent pattern" : "свежих паттернов нет");
  box.innerHTML =
    `<div class="po-cur"><span class="po-label">${en ? "Current candle" : "Текущая свеча"}</span>` +
    `<span class="po-val">🕐 ${fmtDate(o.current_time)} · <b class="${curCls}">${curTxt}</b></span></div>` +
    `<div class="po-next"><span class="po-label">${en ? "Next candle forecast" : "Прогноз следующей свечи"}</span>` +
    `<span class="po-dir ${d.cls}">${en ? d.en : d.ru}</span><small>${based}</small></div>` +
    `<p class="po-note">${en ? "Heuristic by candlestick theory — not a guarantee." : "Эвристика по теории свечей — не гарантия."}</p>`;
}

function renderPatternsView() {
  const grid = $("patternsGrid");
  if (!grid) return;
  const en = window.I18N && I18N.get() === "en";
  if (!lastAnalysisData) {
    if ($("patOutlook")) $("patOutlook").innerHTML = "";
    grid.innerHTML = `<span class="pat-empty">${en ? "Open an instrument and click Analyze." : "Откройте инструмент и нажмите «Анализ»."}</span>`;
    return;
  }
  renderOutlook();
  const byTf = lastAnalysisData.patterns_by_tf || {};
  const pats = byTf[patViewTf] || [];
  if (!pats.length) {
    grid.innerHTML = `<span class="pat-empty">${en ? "No clear patterns on this timeframe" : "Чётких паттернов на этом таймфрейме нет"}</span>`;
    return;
  }
  grid.innerHTML = "";
  pats.forEach((p) => {
    const card = document.createElement("div");
    card.className = "pat-card pat-" + p.bias;
    const when = p.time ? fmtDate(p.time) : "";
    const ageTxt = p.age === 0 ? (en ? "current candle" : "текущая свеча") : when;
    card.innerHTML =
      `<div class="pat-pic">${patternSvg(p.key)}</div>` +
      `<div class="pat-name">${en ? p.name_en : p.name_ru}</div>` +
      `<div class="pat-time">🕐 ${ageTxt}</div>` +
      `<div class="pat-detail">${en ? p.detail_en : p.detail_ru}</div>`;
    grid.appendChild(card);
  });
}

document.querySelectorAll("#patTf button").forEach((b) => {
  b.addEventListener("click", () => {
    patViewTf = b.dataset.tf;
    document.querySelectorAll("#patTf button").forEach((x) => x.classList.toggle("active", x === b));
    renderPatternsView();
  });
});


function renderImbalance(data) {
  const summary = $("imbalanceSummary");
  const list = $("imbalanceList");
  const zones = imbalancesForTf(data);
  if (summary) summary.textContent = data.imbalance_summary || "—";
  if (!list) return;
  if (!zones.length) {
    list.innerHTML = '<span class="imb-empty">Незаполненных имбалансов рядом нет</span>';
    return;
  }
  list.innerHTML = "";
  zones.forEach((z) => {
    const up = z.kind === "bullish";
    const row = document.createElement("div");
    row.className = "imb-row " + (up ? "bull" : "bear");
    row.innerHTML =
      `<span class="imb-tag">${up ? "↑ Бычий" : "↓ Медвежий"}</span>` +
      `<span class="imb-range">${money(z.low)} – ${money(z.high)}</span>` +
      `<span class="imb-dist ${z.distance_pct >= 0 ? "up" : "down"}">${z.distance_pct >= 0 ? "+" : ""}${z.distance_pct}%</span>`;
    list.appendChild(row);
  });
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
      pair: pair,
      market: json.data.market_type || activeMarket,
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
    if ($("personaResult")) $("personaResult").innerHTML = "";
    document.querySelectorAll(".persona-chip.active").forEach((c) => c.classList.remove("active"));
    loadFundamentals(pair, json.data.market_type);
    loadCorrelations(pair, json.data.market_type);
    updateWatchBtn();
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
    // без refresh=1 — используем 50-сек серверный кэш; значения освежаются,
    // когда кэш истекает, без «холодного» пересчёта на каждом тике.
    const refPair = activePair, refMarket = activeMarket;
    const url =
      "/api/analyze?pair=" + encodeURIComponent(refPair) +
      "&market=" + encodeURIComponent(refMarket);
    const json = await (await fetch(url)).json();
    if (!json.ok) return;
    // Инструмент мог смениться, пока шёл запрос — не перетираем свежими чужими данными.
    if (activePair !== refPair) return;
    render(json.data);
    lastAnalysisData = {
      ...json.data,
      position_preview: json.position_preview,
      tv_symbol: json.data.tv_symbol || json.tv_symbol,
      pair: refPair,
      market: json.data.market_type || refMarket,
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

// Скринер: рынок / регион / ТФ
document.querySelectorAll("#scrMarkets button").forEach((b) => {
  b.addEventListener("click", () => {
    scrMarket = b.dataset.market;
    document.querySelectorAll("#scrMarkets button").forEach((x) => x.classList.toggle("active", x === b));
    $("scrRegion")?.classList.toggle("hidden", scrMarket !== "stock");
    loadScreener(true);
  });
});
document.querySelectorAll("#scrRegion button").forEach((b) => {
  b.addEventListener("click", () => {
    scrRegion = b.dataset.region;
    document.querySelectorAll("#scrRegion button").forEach((x) => x.classList.toggle("active", x === b));
    loadScreener(true);
  });
});
document.querySelectorAll("#scrTf button").forEach((b) => {
  b.addEventListener("click", () => {
    scrTf = b.dataset.tf;
    document.querySelectorAll("#scrTf button").forEach((x) => x.classList.toggle("active", x === b));
    loadScreener(true);
  });
});
$("scrRefresh")?.addEventListener("click", () => loadScreener(true));
["scrTrend", "scrSignal", "scrRsiMax", "scrRsiMin", "scrChgMin"].forEach((id) => {
  $(id)?.addEventListener("input", () => applyScreenerFilters());
  $(id)?.addEventListener("change", () => applyScreenerFilters());
});

$("btnNewsAi")?.addEventListener("click", () => loadNewsAi());
$("btnJournalAdd")?.addEventListener("click", () => openJournalAdd());
$("journalAddClose")?.addEventListener("click", closeJournalAdd);
$("journalAddOverlay")?.addEventListener("click", (e) => { if (e.target === $("journalAddOverlay")) closeJournalAdd(); });
$("jaddConfirm")?.addEventListener("click", () => confirmJournalAdd());
$("jaddEntry")?.addEventListener("input", () => {
  clearTimeout(jaddState.recalcTimer);
  jaddState.recalcTimer = setTimeout(jaddRecalc, 350);
});
document.querySelectorAll("#jaddSide button").forEach((b) =>
  b.addEventListener("click", () => {
    jaddState.side = b.dataset.side;
    document.querySelectorAll("#jaddSide button").forEach((x) => x.classList.toggle("active", x === b));
    const sigPair = lastAnalysisData?.display_name || lastAnalysisData?.pair || activePair;
    if (sigPair) $("jaddPair").textContent = sigPair + " · " + (jaddState.side === "long" ? "ЛОНГ 📈" : "ШОРТ 📉");
    jaddRecalc();
  })
);
$("btnJournalRefresh")?.addEventListener("click", () => loadJournal());
$("btnJournalClear")?.addEventListener("click", async () => {
  if (!confirm("Удалить ВСЕ записи журнала? Действие необратимо.")) return;
  try {
    const json = await (await fetch("/api/journal/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ all: true }),
    })).json();
    if (json.ok) loadJournal();
    else showError(json.error || "Не удалось очистить журнал");
  } catch (e) {
    showError("Не удалось очистить журнал");
  }
});

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

let imbalanceOn = false;
$("btnImbalance")?.addEventListener("click", () => {
  imbalanceOn = !imbalanceOn;
  TradingChart.toggleImbalances?.(imbalanceOn);
  $("btnImbalance")?.classList.toggle("active", imbalanceOn);
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
  updateNewsAiHint();
  buildPersonaChips();
  if ($("personaResult")) $("personaResult").innerHTML = "";
  macroLoaded = false; loadMacro(true);
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
    support: {
      title: "❤️ Поддержать проект",
      html: `
        <p>Trading Info Stats — бесплатный проект с открытым кодом. Сервис существует благодаря энтузиазму и вашей поддержке.</p>
        <div class="support-highlight">💯 <b>100% пожертвованных денежных средств</b> пойдут на покупку сервера для сайта и поддержку проекта.</div>
        <p class="modal-note">Любая сумма помогает держать сервис онлайн и развивать его дальше. Спасибо! 🙏</p>
        <div class="support-actions">
          <a class="btn-primary support-btn" href="https://finance.ozon.ru/apps/sbp/ozonbankpay/019e7ffd-85f4-732f-ad99-6a6ce7ede158" target="_blank" rel="noopener">🇷🇺 Поддержать через СБП (Ozon Банк)</a>
          <a class="support-btn-alt" href="https://flenk41.github.io/" target="_blank" rel="noopener">Другие способы поддержки ↗</a>
        </div>`,
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
    support: {
      title: "❤️ Support the project",
      html: `
        <p>Trading Info Stats is a free, open-source project. It runs thanks to enthusiasm and your support.</p>
        <div class="support-highlight">💯 <b>100% of donated funds</b> go toward buying a server for the site and supporting the project.</div>
        <p class="modal-note">Any amount helps keep the service online and growing. Thank you! 🙏</p>
        <div class="support-actions">
          <a class="btn-primary support-btn" href="https://flenk41.github.io/" target="_blank" rel="noopener">❤️ Support</a>
          <a class="support-btn-alt" href="https://finance.ozon.ru/apps/sbp/ozonbankpay/019e7ffd-85f4-732f-ad99-6a6ce7ede158" target="_blank" rel="noopener">🇷🇺 SBP / Ozon Bank (Russia) ↗</a>
        </div>`,
    },
  },
};

// ---- Гайд-карусель: свайп + стрелки + точки, с визуальными мини-превью ----
const _GV = {
  market: `<div class="gv-tabs"><span class="gv-tab active">Крипта</span><span class="gv-tab">Акции</span><span class="gv-tab">Валюта</span></div>`,
  sides: `<div class="gv-badges"><span class="gv-badge buy">ПОКУПАТЬ</span><span class="gv-badge sell">ПРОДАВАТЬ</span><span class="gv-badge wait">ЖДАТЬ</span></div>`,
  entries: `<div class="gv-legend"><span><i style="background:#2dd4bf"></i>лонг</span><span><i style="background:#a855f7"></i>шорт</span><span><i style="background:#ef4444"></i>стоп</span><span><i style="background:#22c55e"></i>тейк</span></div>`,
  approx: `<div class="gv-legend"><span><i style="background:#2dd4bf"></i>лонг</span><span><i style="background:#5eead4;outline:1px dotted #5eead4"></i>~лонг</span><span><i style="background:#a855f7"></i>шорт</span><span><i style="background:#c4b5fd;outline:1px dotted #c4b5fd"></i>~шорт</span></div>`,
  colors: `<div class="gv-aikey">🎨 → 〰️</div>`,
  score: `<div class="gv-ring"><div class="gv-ring-in">78<small>/100</small></div></div>`,
  pro: `<div class="gv-chips"><span>MACD</span><span>RSI</span><span>ADX</span><span>Fibo</span><span>ATR</span></div>`,
  movers: `<div class="gv-movers"><span class="up">BTC +5.2%</span><span class="up">SOL +3.1%</span><span class="down">XRP −2.4%</span></div>`,
  screener: `<div class="gv-stat"><span>INJ</span><b class="up">79</b><span>SOL</span><b>53</b></div>`,
  news: `<div class="gv-news"><span class="gv-nb good">Хорошая</span><span class="gv-nb bad">Плохая</span></div>`,
  personas: `<div class="gv-movers"><span>🛡 Баффет</span><span>🚀 Линч</span><span>⚡ Трейдер</span></div>`,
  dividends: `<div class="gv-aikey">💰 → 📈</div>`,
  insider: `<div class="gv-aikey">🏛 Form 4</div>`,
  journal: `<div class="gv-stat"><span>Винрейт</span><b class="up">62%</b><span>R:R</span><b>1:2</b></div>`,
  aikey: `<div class="gv-aikey">🔑 → 🤖</div>`,
  support: `<div class="gv-aikey">❤️ СБП</div>`,
};

const GUIDE_SLIDES = {
  ru: [
    { v: _GV.market, t: "Выбор рынка", d: "Вверху — Крипта / Акции / Валюта. Инструмент берите из полосы сверху или из поиска: доступны все пары Binance и бумаги MOEX. Крипта работает даже без VPN (при блокировке Binance данные берутся с Yahoo)." },
    { v: _GV.sides, t: "Лонг, Шорт, Ждать", d: "ПОКУПАТЬ (лонг) — ставка на рост, ПРОДАВАТЬ (шорт) — на падение. ЖДАТЬ — сигнал слабый. Направленный сигнал показывается ТОЛЬКО на сильных сетапах — слабые отсекаются, чтобы повышать качество входов." },
    { v: _GV.entries, t: "Точки входа, стоп, тейк", d: "На графике: бирюзовые линии — вход в лонг, фиолетовые — в шорт, красные — стоп, зелёные — тейк. Стоп ставится за структурой + буфер ATR (не в шуме), тейк — у уровня с R:R ≥ 1:2. Кнопка «Точки входа» — что показывать." },
    { v: _GV.approx, t: "Приблизительные зоны", d: "Если по тренду явной зоны нет (напр. сильное падение) — система всё равно даёт ПРИБЛИЗИТЕЛЬНЫЙ вход от объёмной поддержки/сопротивления (Volume POC). Такие линии светлее, пунктиром и с пометкой «~»." },
    { v: _GV.colors, t: "Свои цвета линий", d: "Кнопка «🎨 Цвета» в панели графика — задайте свои цвета для лонга, шорта и приблизительных зон. Меняются на графике сразу, сохраняются в браузере. «Сбросить» вернёт стандартные." },
    { v: _GV.score, t: "Балл согласованности", d: "Кольцо 0–100: насколько согласованы сигналы — таймфреймы, индикаторы, бэктест 4H, новостной фон и инсайдеры. Цвет кольца и карточки = сигналу. Это НЕ вероятность прибыли, а «чистота» картины." },
    { v: _GV.pro, t: "Режим «Про»", d: "Переключите «Простой → Про» вверху — глубокий анализ: тренды по ТФ, MACD/RSI/ADX, волатильность, Фибоначчи, имбаланс (FVG), свечные паттерны и сценарии." },
    { v: _GV.movers, t: "Обзор рынка", d: "Лидеры роста и падения за день / месяц / год (как cryptobubbles), с полосой силы движения. Клик по карточке открывает график и анализ." },
    { v: _GV.screener, t: "Скринер", d: "Таблица по всем инструментам с сортируемой колонкой «Балл» — тот же балл согласованности, что в Обзоре. Фильтры по тренду, RSI, сигналу. Клик по строке — полный анализ." },
    { v: _GV.news, t: "Новости + AI", d: "Хорошие и плохие новости по инструменту с тональностью, плюс AI-разбор с подтверждающими ссылками на источники." },
    { v: _GV.personas, t: "AI-мнения инвесторов", d: "Один актив глазами разных стилей: Баффет (стоимость), Линч (рост), Грэм, Трейдер (техника), Макро. Нужен бесплатный AI-ключ." },
    { v: _GV.dividends, t: "Калькулятор дивидендов", d: "Для акций — кнопка «💰 Дивиденды»: введите количество акций и цену покупки → увидите дивиденды в год/месяц, доходность на вложения и прибыль/убыток «по средствам»." },
    { v: _GV.insider, t: "Инсайдеры / умные деньги", d: "Для акций США — живой сигнал по SEC Form 4: покупки инсайдеров (особенно топ-менеджмента/крупные/кластерные) бычьи и добавляют к баллу. Для РФ-акций — доли инсайдеров/институционалов. Виден в факторах согласованности." },
    { v: _GV.journal, t: "Журнал сигналов", d: "«Записать сигнал» → введите РЕАЛЬНУЮ цену входа (по умолчанию текущая) — стоп/тейк считаются от неё по той же методике, что на графике. Система сама проверит по истории, что сработало (тейк/стоп), и посчитает винрейт. Есть «🗑 Очистить»." },
    { v: _GV.aikey, t: "AI-ключ (свой, бесплатный)", d: "Для AI-разбора и мнений нажмите «🔑 AI-ключ» вверху и вставьте бесплатный ключ. Рекомендую OpenRouter ⭐ (openrouter.ai) — бесплатные модели, доступен из большинства регионов. Ключ хранится только в вашем браузере." },
    { v: _GV.support, t: "Поддержать проект", d: "Кнопка «❤️ Поддержать» вверху. Для РФ — оплата через СБП (Ozon Банк). 100% средств идут на сервер для сайта и развитие проекта." },
  ],
  en: [
    { v: _GV.market.replace("Крипта", "Crypto").replace("Акции", "Stocks").replace("Валюта", "Forex"), t: "Pick a market", d: "Crypto / Stocks / Forex at the top. Pick from the strip or search — all Binance pairs and MOEX stocks. Crypto works even without a VPN (falls back to Yahoo if Binance is blocked)." },
    { v: _GV.sides.replace("ПОКУПАТЬ", "BUY").replace("ПРОДАВАТЬ", "SELL").replace("ЖДАТЬ", "WAIT"), t: "Long, Short, Wait", d: "BUY (long) — bet on a rise, SELL (short) — on a fall. WAIT — weak signal. A directional call shows ONLY on strong setups — weak ones are filtered out to improve entry quality." },
    { v: `<div class="gv-legend"><span><i style="background:#2dd4bf"></i>long</span><span><i style="background:#a855f7"></i>short</span><span><i style="background:#ef4444"></i>stop</span><span><i style="background:#22c55e"></i>take</span></div>`, t: "Entry, stop, take", d: "Turquoise — long entry, purple — short, red — stop, green — take. Stop sits behind structure + ATR buffer (out of noise); take at a level with R:R ≥ 1:2. Use the “Entry points” button to toggle." },
    { v: _GV.approx, t: "Approximate zones", d: "If the trend leaves no clear zone (e.g. a strong drop), the system still gives an APPROXIMATE entry at a volume support/resistance (Volume POC). Such lines are lighter, dotted and marked with “~”." },
    { v: _GV.colors, t: "Custom line colors", d: "The “🎨 Colors” button on the chart bar — set your own colors for long, short and approximate zones. Applied instantly, saved in your browser. “Reset” restores defaults." },
    { v: _GV.score, t: "Agreement score", d: "A 0–100 ring: how aligned the signals are — timeframes, indicators, 4H backtest, news and insiders. Ring/card color = the signal. NOT a probability of profit — it's how clean the picture is." },
    { v: _GV.pro, t: "Pro mode", d: "Switch “Simple → Pro” for deep analysis: per-TF trends, MACD/RSI/ADX, volatility, Fibonacci, imbalance (FVG), candlestick patterns and scenarios." },
    { v: _GV.movers, t: "Market overview", d: "Top gainers and losers for day / month / year (like cryptobubbles) with a move-strength bar. Click a card to open its chart and analysis." },
    { v: `<div class="gv-stat"><span>INJ</span><b class="up">79</b><span>SOL</span><b>53</b></div>`, t: "Screener", d: "A table across instruments with a sortable “Score” column — the same agreement score as the Overview. Filters by trend, RSI, signal. Click a row for full analysis." },
    { v: `<div class="gv-news"><span class="gv-nb good">Good</span><span class="gv-nb bad">Bad</span></div>`, t: "News + AI", d: "Good and bad news per instrument with sentiment, plus an AI review with supporting links to sources." },
    { v: `<div class="gv-movers"><span>🛡 Buffett</span><span>🚀 Lynch</span><span>⚡ Trader</span></div>`, t: "AI investor views", d: "One asset through different styles: Buffett (value), Lynch (growth), Graham, Trader (technical), Macro. Needs a free AI key." },
    { v: _GV.dividends, t: "Dividend calculator", d: "For stocks — the “💰 Dividends” button: enter share count and buy price → see yearly/monthly dividends, yield on cost and P&L on your money." },
    { v: _GV.insider, t: "Insiders / smart money", d: "US stocks — a live SEC Form 4 signal: insider buys (esp. executives/large/clustered) are bullish and add to the score. RU stocks — insider/institutional ownership. Shown in the agreement factors." },
    { v: `<div class="gv-stat"><span>Win rate</span><b class="up">62%</b><span>R:R</span><b>1:2</b></div>`, t: "Signal journal", d: "“Log signal” → enter your REAL entry price (defaults to current) — stop/take are computed from it with the same method as the chart. The system checks history for what hit first and computes a real win rate. There's a “🗑 Clear”." },
    { v: _GV.aikey, t: "AI key (your own, free)", d: "For the AI review and views, click “🔑 AI key” and paste a free key. Recommended: OpenRouter ⭐ (openrouter.ai) — free models, works in most regions. Stored only in your browser." },
    { v: `<div class="gv-aikey">❤️</div>`, t: "Support the project", d: "The “❤️ Support” button at the top. For Russia — payment via SBP (Ozon Bank). 100% of funds go to the server and project development." },
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
$("linkSupport")?.addEventListener("click", () => openModal("support"));
$("linkGuide")?.addEventListener("click", () => openGuide());

// ---- Калькулятор дивидендов (только для акций) ----
let divData = null;

function toggleDividendBtn() {
  const btn = $("linkDividends");
  if (!btn) return;
  btn.classList.toggle("hidden", !(activeView === "market" && activeMarket === "stock"));
}

function divCur(cur) {
  return cur === "USD" ? "$" : cur === "RUB" ? "₽" : cur === "EUR" ? "€" : cur === "GBP" ? "£" : "";
}
function divFmt(v, cur) {
  if (v == null || isNaN(v)) return "—";
  const sym = divCur(cur);
  const n = Math.abs(v) >= 1 ? v.toFixed(2) : parseFloat(v.toFixed(4)).toString();
  return sym ? `${sym}${n}` : `${n} ${cur}`;
}

async function openDividends() {
  if (activeMarket !== "stock" || !activePair) {
    showError("Откройте акцию и нажмите «Анализ», затем считайте дивиденды");
    return;
  }
  $("dividendOverlay").classList.remove("hidden");
  $("divStock").textContent = "Загрузка…";
  $("divMarket").innerHTML = "";
  $("divResults").innerHTML = "";
  $("divNote").textContent = "Введите количество акций и цену покупки.";
  divData = null;
  try {
    const r = await fetch(`/api/dividends?pair=${encodeURIComponent(activePair)}&market=stock`);
    const j = await r.json();
    if (!j.ok || !j.available) {
      $("divStock").textContent = (j && j.name) || activePair;
      $("divNote").textContent = "Нет данных по дивидендам для этой бумаги (часть RU-акций Yahoo не отдаёт).";
      return;
    }
    divData = j;
    const cur = j.currency || "";
    $("divStock").textContent = j.name || activePair;
    $("divMarket").innerHTML =
      `<div class="dm-row"><span>Текущая цена</span><b>${divFmt(j.price, cur)}</b></div>` +
      `<div class="dm-row"><span>Дивиденд на акцию (в год)</span><b>${divFmt(j.dividend_per_share, cur)}</b></div>` +
      `<div class="dm-row"><span>Дивидендная доходность</span><b>${j.dividend_yield != null ? (j.dividend_yield * 100).toFixed(2) + "%" : "—"}</b></div>`;
    if (j.price != null && !$("divBuy").value) $("divBuy").value = j.price;
    computeDividends();
  } catch (e) {
    $("divNote").textContent = "Ошибка загрузки данных.";
  }
}

function computeDividends() {
  const box = $("divResults");
  if (!divData) { box.innerHTML = ""; return; }
  const shares = parseFloat($("divShares").value);
  const buy = parseFloat($("divBuy").value);
  const cur = divData.currency || "";
  const price = divData.price, dps = divData.dividend_per_share;
  if (isNaN(shares) || shares <= 0) {
    box.innerHTML = "";
    $("divNote").textContent = "Введите количество акций.";
    return;
  }
  const rows = [];
  if (dps != null) {
    const annual = dps * shares;
    rows.push(["Дивиденды в год", divFmt(annual, cur), "good"]);
    rows.push(["≈ в месяц", divFmt(annual / 12, cur), ""]);
    if (!isNaN(buy) && buy > 0) {
      rows.push(["Доходность на ваши вложения", ((dps / buy) * 100).toFixed(2) + "%", ""]);
    }
  }
  if (price != null && !isNaN(buy) && buy > 0) {
    const invested = buy * shares, nowVal = price * shares, pnl = nowVal - invested, pct = (pnl / invested) * 100;
    rows.push(["Вложено", divFmt(invested, cur), ""]);
    rows.push(["Сейчас стоит", divFmt(nowVal, cur), ""]);
    rows.push([
      (pnl >= 0 ? "Прибыль" : "Убыток") + " по средствам",
      (pnl >= 0 ? "+" : "") + divFmt(pnl, cur) + ` (${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%)`,
      pnl >= 0 ? "good" : "bad",
    ]);
  }
  box.innerHTML = rows.map(([k, v, c]) => `<div class="dr-row ${c || ""}"><span>${k}</span><b>${v}</b></div>`).join("");
  $("divNote").textContent = "Оценка по годовым дивидендам Yahoo — не гарантия будущих выплат.";
}

function closeDividends() { $("dividendOverlay")?.classList.add("hidden"); }
$("linkDividends")?.addEventListener("click", openDividends);
$("dividendClose")?.addEventListener("click", closeDividends);
$("dividendOverlay")?.addEventListener("click", (e) => { if (e.target === $("dividendOverlay")) closeDividends(); });
["divShares", "divBuy"].forEach((id) => $(id)?.addEventListener("input", computeDividends));

// ---- BYOK: пользователь подключает свой AI-ключ (хранится только в браузере) ----
const AI_PROVIDERS = {
  openrouter: { label: "OpenRouter — рекомендуется ⭐ (бесплатно)", base: "https://openrouter.ai/api/v1", model: "meta-llama/llama-3.3-70b-instruct:free", url: "https://openrouter.ai/keys" },
  groq: { label: "Groq — бесплатно, быстро", base: "https://api.groq.com/openai/v1", model: "llama-3.3-70b-versatile", url: "https://console.groq.com/keys" },
  gemini: { label: "Google Gemini — бесплатно", base: "https://generativelanguage.googleapis.com/v1beta/openai/", model: "gemini-2.0-flash", url: "https://aistudio.google.com/apikey" },
  ollama: { label: "Ollama — локально, бесплатно", base: "http://localhost:11434/v1", model: "llama3.1", url: "https://ollama.com/download" },
  openai: { label: "OpenAI — платно", base: "https://api.openai.com/v1", model: "gpt-4o-mini", url: "https://platform.openai.com/api-keys" },
};

// Определяем провайдера по префиксу ключа — чтобы бесплатный ключ всегда ушёл
// на правильный эндпоинт, даже если в списке выбран не тот провайдер.
function detectProviderByKey(key) {
  const k = (key || "").trim();
  if (k.startsWith("gsk_")) return "groq";
  if (k.startsWith("sk-or-")) return "openrouter";
  if (k.startsWith("AIza")) return "gemini";
  if (k.startsWith("sk-")) return "openai";
  return null;
}

function getAiCfg() {
  try { return JSON.parse(localStorage.getItem("ai_cfg") || "{}"); } catch (e) { return {}; }
}
function saveAiCfgObj(cfg) {
  try { localStorage.setItem("ai_cfg", JSON.stringify(cfg)); } catch (e) {}
}

function openAiKeyModal() {
  const en = window.I18N && I18N.get() === "en";
  const cfg = getAiCfg();
  const prov = cfg.provider || "openrouter";
  const T = en ? {
    title: "🔑 Connect AI (free)",
    intro: "The AI news review needs a key. It's free — get one in ~1 minute and paste it below. The key is stored only in your browser and is never shared.",
    steps: ["Open the provider site (link below) and sign in.", "Create an API key (button “Create API key”).", "Copy the key and paste it here.", "Save — then use “🤖 AI review” on the News tab."],
    provider: "Provider", key: "API key", model: "Model", get: "Get a free key ↗",
    save: "Save", clear: "Clear", saved: "Key saved ✓", none: "No key set", note: "Recommended: OpenRouter ⭐ (free models, works in most regions). Alternatives: Groq, Gemini, or Ollama (local).",
  } : {
    title: "🔑 Подключение AI (бесплатно)",
    intro: "Для AI-разбора новостей нужен ключ. Это бесплатно — получите его за ~1 минуту и вставьте ниже. Ключ хранится только в вашем браузере и никому не передаётся.",
    steps: ["Откройте сайт провайдера (ссылка ниже) и войдите.", "Создайте API-ключ (кнопка «Create API key»).", "Скопируйте ключ и вставьте сюда.", "Сохраните — и пользуйтесь «🤖 AI-разбор» во вкладке «Новости»."],
    provider: "Провайдер", key: "API-ключ", model: "Модель", get: "Получить бесплатный ключ ↗",
    save: "Сохранить", clear: "Очистить", saved: "Ключ сохранён ✓", none: "Ключ не задан", note: "Рекомендую OpenRouter ⭐ (бесплатные модели, доступен из большинства регионов). Альтернативы: Groq, Gemini или Ollama (локально).",
  };
  const opts = Object.entries(AI_PROVIDERS).map(([k, v]) => `<option value="${k}" ${k === prov ? "selected" : ""}>${v.label}</option>`).join("");
  const steps = T.steps.map((s, i) => `<div class="ai-step"><span class="ai-step-n">${i + 1}</span><span>${s}</span></div>`).join("");
  $("aiKeyTitle").textContent = T.title;
  $("aiKeyBody").innerHTML =
    `<p>${T.intro}</p>` +
    `<div class="ai-steps">${steps}</div>` +
    `<label class="ai-field"><span>${T.provider}</span><select id="aiProvider">${opts}</select></label>` +
    `<a class="ai-getkey" id="aiGetKey" target="_blank" rel="noopener">${T.get}</a>` +
    `<label class="ai-field"><span>${T.key}</span><input type="password" id="aiKeyInput" placeholder="••••••••" autocomplete="off"></label>` +
    `<label class="ai-field"><span>${T.model}</span><input type="text" id="aiModelInput"></label>` +
    `<div class="ai-actions"><button type="button" class="btn-primary" id="aiSave">${T.save}</button>` +
    `<button type="button" class="btn-secondary" id="aiClear">${T.clear}</button>` +
    `<span class="ai-status" id="aiStatus">${cfg.key ? T.saved : T.none}</span></div>` +
    `<p class="modal-note">${T.note}</p>`;

  const keyInput = $("aiKeyInput"), modelInput = $("aiModelInput"), provSel = $("aiProvider"), getLink = $("aiGetKey");
  if (cfg.key) keyInput.value = cfg.key;
  modelInput.value = cfg.model || AI_PROVIDERS[prov].model;
  getLink.href = AI_PROVIDERS[prov].url;
  provSel.addEventListener("change", () => {
    const p = AI_PROVIDERS[provSel.value];
    modelInput.value = p.model;
    getLink.href = p.url;
  });
  // Авто-подстройка провайдера по введённому ключу.
  keyInput.addEventListener("input", () => {
    const det = detectProviderByKey(keyInput.value);
    if (det && det !== provSel.value) {
      provSel.value = det;
      modelInput.value = AI_PROVIDERS[det].model;
      getLink.href = AI_PROVIDERS[det].url;
    }
  });
  $("aiSave").addEventListener("click", () => {
    const key = keyInput.value.trim();
    // Ключ — источник истины: если префикс распознан, берём его провайдера/адрес.
    const p = detectProviderByKey(key) || provSel.value;
    const next = { provider: p, key, base: AI_PROVIDERS[p].base, model: modelInput.value.trim() || AI_PROVIDERS[p].model };
    saveAiCfgObj(next);
    provSel.value = p;
    $("aiStatus").textContent = key
      ? (T.saved + " · " + (AI_PROVIDERS[p].label.split(" ")[0]) + " → " + next.model)
      : T.none;
    updateNewsAiHint();
  });
  $("aiClear").addEventListener("click", () => {
    try { localStorage.removeItem("ai_cfg"); } catch (e) {}
    keyInput.value = "";
    $("aiStatus").textContent = T.none;
    updateNewsAiHint();
  });
  $("aiKeyOverlay").classList.remove("hidden");
}
function closeAiKey() { $("aiKeyOverlay")?.classList.add("hidden"); }
$("linkAiKey")?.addEventListener("click", openAiKeyModal);

// ---- AI-персоны инвесторов ----
const PERSONA_META = [
  { id: "value", emoji: "🛡️", ru: "Баффет", en: "Buffett", ruTag: "Стоимость", enTag: "Value" },
  { id: "growth", emoji: "🚀", ru: "Линч", en: "Lynch", ruTag: "Рост", enTag: "Growth" },
  { id: "deepvalue", emoji: "📉", ru: "Грэм", en: "Graham", ruTag: "Осторожно", enTag: "Cautious" },
  { id: "trader", emoji: "⚡", ru: "Трейдер", en: "Trader", ruTag: "Техника", enTag: "Technicals" },
  { id: "macro", emoji: "🌍", ru: "Макро", en: "Macro", ruTag: "Сверху вниз", enTag: "Top-down" },
];
const PERSONA_VERDICT = {
  buy: { ru: "ПОКУПАТЬ", en: "BUY", cls: "buy" },
  hold: { ru: "ДЕРЖАТЬ", en: "HOLD", cls: "wait" },
  avoid: { ru: "ИЗБЕГАТЬ", en: "AVOID", cls: "sell" },
};
let personaLoading = false;

function buildPersonaChips() {
  const wrap = $("personaChips");
  if (!wrap) return;
  const en = window.I18N && I18N.get() === "en";
  wrap.innerHTML = "";
  PERSONA_META.forEach((p) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "persona-chip";
    b.dataset.id = p.id;
    b.innerHTML = `<span class="pc-emoji">${p.emoji}</span><span class="pc-name">${en ? p.en : p.ru}</span><small>${en ? p.enTag : p.ruTag}</small>`;
    b.addEventListener("click", () => askPersona(p.id, b));
    wrap.appendChild(b);
  });
}

async function askPersona(id, chip) {
  const box = $("personaResult");
  if (!box) return;
  if (!activePair) { showError("Сначала выберите инструмент и нажмите «Анализ»"); return; }
  if (personaLoading) return;
  if (!getAiCfg().key) {
    box.innerHTML = `<p class="news-empty">🔑 Нужен бесплатный AI-ключ</p><button type="button" class="btn-primary" id="personaKeyBtn">🔑 AI-ключ</button>`;
    $("personaKeyBtn")?.addEventListener("click", openAiKeyModal);
    return;
  }
  personaLoading = true;
  document.querySelectorAll(".persona-chip").forEach((c) => c.classList.toggle("active", c === chip));
  box.innerHTML = '<p class="news-empty">🧠 Анализирую…</p>';
  try {
    const cfg = getAiCfg();
    const json = await (await fetch("/api/ai-persona", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pair: activePair, market: activeMarket, persona: id,
        lang: window.I18N ? I18N.get() : "ru",
        ai_key: cfg.key || "", ai_base: cfg.base || "", ai_model: cfg.model || "",
        fred_key: getFredKey(),
      }),
    })).json();
    if (json.ok) renderPersona(json.persona);
    else if (json.need_key) {
      box.innerHTML = `<p class="news-empty">${json.error}</p><button type="button" class="btn-primary" id="personaKeyBtn">🔑 AI-ключ</button>`;
      $("personaKeyBtn")?.addEventListener("click", openAiKeyModal);
    } else box.innerHTML = `<p class="news-empty">${json.error || "AI недоступен"}</p>`;
  } catch (e) {
    box.innerHTML = '<p class="news-empty">Не удалось получить мнение.</p>';
  } finally {
    personaLoading = false;
  }
}

// ---- Макро-фон (FRED) ----
let macroLoaded = false;
function getFredKey() {
  try { return localStorage.getItem("fred_key") || ""; } catch (e) { return ""; }
}
function renderFredKeyForm(message) {
  const grid = $("macroGrid"), label = $("macroLabel"), note = $("macroNote");
  label.textContent = ""; label.className = "macro-label";
  grid.innerHTML = "";
  const en = window.I18N && I18N.get() === "en";
  note.innerHTML =
    `<span class="macro-msg">🔑 ${message || (en ? "Free FRED key needed" : "Нужен бесплатный ключ FRED")}</span>` +
    `<span class="fred-form">` +
    `<input type="password" id="fredKeyInput" placeholder="${en ? "paste FRED key" : "вставьте ключ FRED"}" autocomplete="off">` +
    `<button type="button" class="btn-primary" id="fredSave">${en ? "Save" : "Сохранить"}</button>` +
    `</span>` +
    `<a href="https://fredaccount.stlouisfed.org/apikeys" target="_blank" rel="noopener">${en ? "Get a free key ↗" : "Получить бесплатный ключ ↗"}</a>`;
  const inp = $("fredKeyInput");
  if (inp) inp.value = getFredKey();
  $("fredSave")?.addEventListener("click", () => {
    const v = ($("fredKeyInput")?.value || "").trim();
    try { v ? localStorage.setItem("fred_key", v) : localStorage.removeItem("fred_key"); } catch (e) {}
    macroLoaded = false;
    loadMacro(true);
  });
}
async function loadMacro(force) {
  const card = $("macroCard");
  if (!card) return;
  if (macroLoaded && !force) return;
  const grid = $("macroGrid");
  grid.innerHTML = '<span class="macro-empty">Загрузка…</span>';
  try {
    const lang = window.I18N ? I18N.get() : "ru";
    const json = await (await fetch(`/api/macro?lang=${lang}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fred_key: getFredKey() }),
    })).json();
    if (json.ok) {
      macroLoaded = true;
      renderMacro(json);
    } else if (json.need_key) {
      renderFredKeyForm(json.error);
    } else {
      renderFredKeyForm(json.error); // ошибка ключа — тоже показываем форму
    }
  } catch (e) {
    $("macroGrid").innerHTML = '<span class="macro-empty">Не удалось загрузить макро.</span>';
  }
}

function renderMacro(m) {
  const grid = $("macroGrid"), label = $("macroLabel"), note = $("macroNote");
  label.textContent = m.label || "";
  label.className = "macro-label " + (m.risk || "mixed");
  note.textContent = m.note || "";
  grid.innerHTML = "";
  (m.items || []).forEach((it) => {
    const up = it.change > 0, down = it.change < 0;
    const arrow = up ? "▲" : down ? "▼" : "•";
    const tile = document.createElement("div");
    tile.className = "macro-tile";
    tile.innerHTML =
      `<span class="mt-name">${it.name}</span>` +
      `<span class="mt-val">${it.value}${it.unit}</span>` +
      `<span class="mt-chg ${up ? "up" : down ? "down" : ""}">${arrow} ${it.change > 0 ? "+" : ""}${it.change}${it.unit}</span>`;
    grid.appendChild(tile);
  });
  applyI18n();
}

// ---- Фундаментал акций ----
async function loadFundamentals(pair, market) {
  const panel = $("fundamentalsPanel");
  if (!panel) return;
  if (market !== "stock") { panel.classList.add("hidden"); return; }
  try {
    const lang = window.I18N ? I18N.get() : "ru";
    const json = await (await fetch(`/api/fundamentals?pair=${encodeURIComponent(pair)}&market=stock&lang=${lang}`)).json();
    if (json.ok && json.available) renderFundamentals(json);
    else panel.classList.add("hidden");
  } catch (e) {
    panel.classList.add("hidden");
  }
}

function renderFundamentals(d) {
  const panel = $("fundamentalsPanel");
  panel.classList.remove("hidden");
  const meta = $("fundMeta"), grid = $("fundGrid"), sum = $("fundSummary");
  meta.textContent = [d.sector, d.industry].filter(Boolean).join(" · ");
  grid.innerHTML = "";
  (d.items || []).forEach((it) => {
    const tile = document.createElement("div");
    tile.className = "fund-tile";
    tile.innerHTML = `<span class="ft-name">${it.name}</span><span class="ft-val">${it.value}</span>`;
    grid.appendChild(tile);
  });
  sum.textContent = d.summary || "";
}

// ---- Корреляции ----
async function loadCorrelations(pair, market) {
  const panel = $("corrPanel");
  if (!panel) return;
  $("corrPositive").innerHTML = '<span class="corr-empty">…</span>';
  $("corrNegative").innerHTML = "";
  try {
    let url = `/api/correlations?pair=${encodeURIComponent(pair)}&market=${market}`;
    if (market === "stock") url += `&region=${activeStockRegion}`;
    const json = await (await fetch(url)).json();
    if (json.ok) renderCorrelations(json);
    else { $("corrPositive").innerHTML = `<span class="corr-empty">${json.error || "—"}</span>`; }
  } catch (e) {
    $("corrPositive").innerHTML = '<span class="corr-empty">Не удалось загрузить.</span>';
  }
}

function _corrRow(it) {
  const up = it.corr >= 0;
  const row = document.createElement("button");
  row.type = "button";
  row.className = "corr-row";
  row.innerHTML =
    `<span class="inst-icon-wrap">${moverIconHtml(it)}</span>` +
    `<span class="corr-name">${it.name}<small>${it.subtitle}</small></span>` +
    `<span class="corr-val ${up ? "up" : "down"}">${it.corr > 0 ? "+" : ""}${it.corr}</span>`;
  row.addEventListener("click", () => {
    if (it.market === "stock") {
      activeStockRegion = it.region || activeStockRegion;
      document.querySelectorAll("#stockRegionTabs .btn-region").forEach((b) =>
        b.classList.toggle("active", b.dataset.region === activeStockRegion));
    }
    switchView("market", it.market);
    analyze(it.id);
  });
  return row;
}

function renderCorrelations(d) {
  const pos = $("corrPositive"), neg = $("corrNegative");
  pos.innerHTML = ""; neg.innerHTML = "";
  if (!d.positive?.length) pos.innerHTML = '<span class="corr-empty">—</span>';
  else d.positive.forEach((it) => pos.appendChild(_corrRow(it)));
  if (!d.negative?.length) neg.innerHTML = '<span class="corr-empty">—</span>';
  else d.negative.forEach((it) => neg.appendChild(_corrRow(it)));
  applyI18n();
}

// ================= Watchlist + Портфель =================
function guessMarket(pair) {
  const p = (pair || "").toUpperCase();
  if (p.endsWith(".ME")) return "stock";
  if (p.includes("/")) return p.includes("USDT") ? "crypto" : "forex";
  return "stock";
}
function getWatchlist() { try { return JSON.parse(localStorage.getItem("watchlist") || "[]"); } catch (e) { return []; } }
function setWatchlist(a) { try { localStorage.setItem("watchlist", JSON.stringify(a)); } catch (e) {} }
function getPortfolio() { try { return JSON.parse(localStorage.getItem("portfolio") || "[]"); } catch (e) { return []; } }
function setPortfolio(a) { try { localStorage.setItem("portfolio", JSON.stringify(a)); } catch (e) {} }

function inWatchlist(id) { return getWatchlist().some((w) => w.id === id); }
function updateWatchBtn() {
  const b = $("btnWatch");
  if (!b) return;
  const on = activePair && inWatchlist(activePair);
  b.textContent = on ? "★ В списке" : "☆ В список";
  b.classList.toggle("active", !!on);
}
function toggleWatch() {
  if (!activePair) return;
  let wl = getWatchlist();
  if (inWatchlist(activePair)) wl = wl.filter((w) => w.id !== activePair);
  else wl.unshift({ id: activePair, market: activeMarket, name: (lastAnalysisData && lastAnalysisData.display_name) || activePair });
  setWatchlist(wl);
  updateWatchBtn();
  if (activeView === "portfolio") renderWatchlist();
}
$("btnWatch")?.addEventListener("click", toggleWatch);

async function renderWatchlist() {
  const box = $("watchlist");
  if (!box) return;
  const wl = getWatchlist();
  if (!wl.length) {
    box.innerHTML = '<p class="news-empty">Пусто. Откройте инструмент и нажмите «☆ В список» над графиком.</p>';
    return;
  }
  box.innerHTML = wl.map((w) =>
    `<div class="wl-row" data-id="${w.id}" data-market="${w.market}"><span class="wl-name">${w.name}<small>${w.id}</small></span>` +
    `<span class="wl-quote" data-q="${w.id}">…</span>` +
    `<button class="wl-del" data-del="${w.id}" title="Убрать">✕</button></div>`
  ).join("");
  box.querySelectorAll(".wl-row").forEach((r) => {
    r.addEventListener("click", (e) => {
      if (e.target.closest(".wl-del")) return;
      switchView("market", r.dataset.market);
      analyze(r.dataset.id);
    });
  });
  box.querySelectorAll(".wl-del").forEach((b) =>
    b.addEventListener("click", (e) => { e.stopPropagation(); setWatchlist(getWatchlist().filter((w) => w.id !== b.dataset.del)); renderWatchlist(); updateWatchBtn(); })
  );
  // котировки
  wl.forEach(async (w) => {
    try {
      const j = await (await fetch(`/api/quote?pair=${encodeURIComponent(w.id)}&market=${w.market}`)).json();
      const cell = box.querySelector(`[data-q="${CSS.escape(w.id)}"]`);
      if (cell && j.ok) {
        const cur = moverCurrency({ market: w.market, id: w.id });
        const up = j.change_pct >= 0;
        cell.innerHTML = `${cur}${formatPrice(j.price)} <span class="${up ? "up" : "down"}">${up ? "+" : ""}${j.change_pct}%</span>`;
      }
    } catch (e) {}
  });
}

function pfAddHolding() {
  const pair = ($("pfPair").value || "").trim();
  const qty = parseFloat($("pfQty").value);
  const entry = parseFloat($("pfEntry").value);
  if (!pair || !(qty > 0)) { showError("Укажите инструмент и количество"); return; }
  const market = guessMarket(pair);
  const pf = getPortfolio();
  pf.push({ id: pair.toUpperCase(), market, name: pair.toUpperCase(), qty, entry: entry > 0 ? entry : 0 });
  setPortfolio(pf);
  $("pfPair").value = ""; $("pfQty").value = ""; $("pfEntry").value = "";
  loadPortfolio();
}
$("pfAddBtn")?.addEventListener("click", pfAddHolding);
$("pfRefresh")?.addEventListener("click", () => loadPortfolio());

async function loadPortfolio() {
  renderWatchlist();
  const pf = getPortfolio();
  const hbox = $("pfHoldings"), mbox = $("pfMetrics"), ebox = $("pfEquity");
  if (!hbox) return;
  if (!pf.length) {
    mbox.innerHTML = ""; ebox.innerHTML = "";
    hbox.innerHTML = '<p class="news-empty">Добавьте позиции, чтобы увидеть P&L и риск (Sharpe, просадка).</p>';
    return;
  }
  hbox.innerHTML = '<p class="news-empty">Считаю риск по истории…</p>';
  try {
    const json = await (await fetch("/api/portfolio-risk", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ holdings: pf.map((h) => ({ pair: h.id, market: h.market, qty: h.qty, entry: h.entry })) }),
    })).json();
    if (json.ok) renderPortfolio(json, pf);
    else hbox.innerHTML = `<p class="news-empty">${json.error || "Ошибка"}</p>`;
  } catch (e) {
    hbox.innerHTML = '<p class="news-empty">Не удалось посчитать портфель.</p>';
  }
}

function renderPortfolio(d, pf) {
  const mbox = $("pfMetrics"), ebox = $("pfEquity"), hbox = $("pfHoldings");
  const pnlUp = d.pnl >= 0;
  mbox.innerHTML =
    `<div class="pf-metric"><span>Стоимость</span><strong>$${d.value.toLocaleString("en-US")}</strong></div>` +
    `<div class="pf-metric"><span>P&L</span><strong class="${pnlUp ? "up" : "down"}">${pnlUp ? "+" : ""}${d.pnl_pct}%</strong></div>` +
    `<div class="pf-metric"><span>Доходность (6м)</span><strong class="${d.total_return_pct >= 0 ? "up" : "down"}">${d.total_return_pct}%</strong></div>` +
    `<div class="pf-metric"><span>Sharpe</span><strong class="${d.sharpe >= 1 ? "up" : d.sharpe < 0 ? "down" : ""}">${d.sharpe}</strong></div>` +
    `<div class="pf-metric"><span>Волатильность</span><strong>${d.volatility_pct}%</strong></div>` +
    `<div class="pf-metric"><span>Макс. просадка</span><strong class="down">${d.max_drawdown_pct}%</strong></div>`;
  ebox.innerHTML = sparkline(d.equity);

  const cur = (h) => moverCurrency({ market: h.market, id: h.pair });
  hbox.innerHTML =
    `<div class="pf-row pf-hhead"><span>Инструмент</span><span>Кол-во</span><span>Цена</span><span>Стоимость</span><span>P&L</span><span>Доля</span><span></span></div>` +
    d.holdings.map((h) =>
      `<div class="pf-row"><span class="pf-inst">${h.name}</span>` +
      `<span>${h.qty}</span>` +
      `<span>${cur(h)}${formatPrice(h.price)}</span>` +
      `<span>${cur(h)}${h.value.toLocaleString("en-US")}</span>` +
      `<span class="${h.pnl_pct >= 0 ? "up" : "down"}">${h.pnl_pct == null ? "—" : (h.pnl_pct >= 0 ? "+" : "") + h.pnl_pct + "%"}</span>` +
      `<span>${h.weight_pct}%</span>` +
      `<button class="pf-del" data-del="${h.pair}" title="Убрать">✕</button></div>`
    ).join("");
  hbox.querySelectorAll(".pf-del").forEach((b) =>
    b.addEventListener("click", () => { setPortfolio(getPortfolio().filter((h) => h.id !== b.dataset.del)); loadPortfolio(); })
  );
}

function sparkline(values) {
  if (!values || values.length < 2) return "";
  const w = 100, h = 28, min = Math.min(...values), max = Math.max(...values), rng = max - min || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1) * w).toFixed(1)},${(h - (v - min) / rng * h).toFixed(1)}`).join(" ");
  const up = values[values.length - 1] >= values[0];
  const col = up ? "#22c55e" : "#ef4444";
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.5"/></svg>`;
}

function renderPersona(p) {
  const box = $("personaResult");
  if (!box || !p) return;
  const en = window.I18N && I18N.get() === "en";
  const v = PERSONA_VERDICT[p.verdict] || PERSONA_VERDICT.hold;
  const li = (arr, cls) => (arr || []).map((x) => `<li class="${cls}">${x}</li>`).join("");
  box.innerHTML =
    `<div class="persona-top"><span class="persona-name">${p.emoji} ${p.name}</span>` +
    `<span class="verdict-badge ${v.cls}">${en ? v.en : v.ru}</span>` +
    `<span class="persona-conf">${p.confidence || 0}%</span></div>` +
    (p.horizon ? `<div class="persona-horizon">${en ? "Horizon" : "Горизонт"}: ${p.horizon}</div>` : "") +
    `<p class="persona-summary">${p.summary || ""}</p>` +
    `<ul class="persona-points">${li(p.pros, "pro")}${li(p.cons, "con")}</ul>` +
    `<p class="persona-note">${en ? "AI opinion in a style, not financial advice." : "AI-мнение в стиле, не финансовая рекомендация."} · ${p.model || ""}</p>`;
}
$("aiKeyClose")?.addEventListener("click", closeAiKey);
$("aiKeyOverlay")?.addEventListener("click", (e) => { if (e.target === $("aiKeyOverlay")) closeAiKey(); });
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
    const lwTf = LW_TF_MAP[tvInterval];
    if (lwReady && activePair && lwTf) {
      Promise.resolve(TradingChart.loadPair(activePair, activeMarket, lwTf)).then(() => {
        // перерисовываем зоны входа под новый таймфрейм (стоп/тейк под его ATR)
        if (lastAnalysisData) updateChartTrend(lastAnalysisData);
      });
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
  buildPersonaChips();
  loadMacro();
  $("fundingPanel")?.classList.add("hidden");
  switchTab("overview");
  // Стартуем на рыночной вкладке (крипта), грузим инструмент по умолчанию.
  activeView = "market";
  activeMarket = "crypto";
  renderPairsGrid("crypto");
  analyze("ETH/USDT");
});
