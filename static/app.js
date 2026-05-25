let activePair = null;
let activeMarket = "crypto";
let lastMarketPrice = null;
let activeSide = "long";
let activeRiskSide = "long";
let lastAnalysisData = null;
let lastPosition = null;
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

// ---- Тема и режим (Простой/Про) ----
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const btn = $("themeToggle");
  if (btn) btn.textContent = theme === "light" ? "☀️" : "🌙";
  if (TradingChart.setTheme) TradingChart.setTheme(theme);
  try { localStorage.setItem("ui_theme", theme); } catch (e) {}
}

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
  $("verdictConf").textContent = acc != null ? acc + "%" : "—";

  const levels = $("verdictLevels");
  const preview = d.position_preview && d.position_preview[side];
  if ((side === "long" || side === "short") && preview) {
    levels.classList.remove("hidden");
    levels.innerHTML =
      `<div class="vl entry"><span>Вход</span><strong>${money(preview.entry_price)}</strong></div>` +
      `<div class="vl stop"><span>Стоп</span><strong>${money(preview.stop_loss)}</strong></div>` +
      `<div class="vl tp"><span>Тейк</span><strong>${money(preview.take_profit)}</strong></div>` +
      `<div class="vl"><span>R:R</span><strong>1:${preview.risk_reward}</strong></div>`;
  } else {
    levels.classList.add("hidden");
    levels.innerHTML = "";
  }
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
    const url = `/api/news-ai?pair=${encodeURIComponent(activePair)}&market=${encodeURIComponent(activeMarket)}&range=${activeNewsRange}`;
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
      (sig.accuracy_pct != null ? `<span>Точн. ${sig.accuracy_pct}%</span>` : "") +
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
      switchTab("journal");
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
    const url = `/api/news?pair=${encodeURIComponent(activePair)}&market=${encodeURIComponent(activeMarket)}&range=${activeNewsRange}`;
    const json = await (await fetch(url)).json();
    if (json.ok) renderNews(json);
    else list.innerHTML = `<p class="news-empty">${json.error || "Ошибка загрузки новостей"}</p>`;
  } catch (e) {
    list.innerHTML = '<p class="news-empty">Не удалось загрузить новости.</p>';
  } finally {
    newsLoading = false;
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
  $("error").textContent = msg;
  $("error").classList.remove("hidden");
  setTimeout(() => $("error")?.classList.add("hidden"), 6000);
}

function switchTab(tabId) {
  document.querySelectorAll(".panel-tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-panel").forEach((p) => {
    p.classList.toggle("active", p.id === `tab-${tabId}`);
  });
  if (tabId === "news") loadNews();
  if (tabId === "journal") loadJournal();
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
  TradingChart.setEntryPicker((price) => {
    $("posEntry").value = price.toFixed(price >= 1 ? 4 : 6);
    if (activePair) calculatePosition(true);
  });
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
  ring.textContent = `${acc.overall_pct}%`;
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

function syncRiskFromPosition(p) {
  if (!p) return;
  $("riskEntry").value = p.entry_price;
  $("riskStop").value = p.stop_loss;
  $("riskTp").value = p.take_profit || "";
  $("riskMargin").value = p.margin_usdt;
  $("riskLeverage").value = p.leverage;
  activeRiskSide = p.side;
  $("btnRiskLong").classList.toggle("active", p.side === "long");
  $("btnRiskShort").classList.toggle("active", p.side === "short");
}

function renderRisk(r) {
  const box = $("riskResult");
  if (!box || !r) return;
  box.classList.remove("hidden", "ok", "warn", "danger");
  box.classList.add(r.status);

  $("riskVerdict").textContent = r.verdict;
  const metrics = $("riskMetrics");
  metrics.innerHTML = `
    <div class="risk-metric"><span>Риск сделки</span><strong>$${r.actual_risk_usdt} (${r.actual_risk_pct}%)</strong></div>
    <div class="risk-metric"><span>Лимит</span><strong>$${r.risk_budget_usdt}</strong></div>
    <div class="risk-metric"><span>Маржа (реком.)</span><strong>$${r.recommended_margin_usdt}</strong></div>
    <div class="risk-metric"><span>Плечо (макс.)</span><strong>x${r.max_safe_leverage}</strong></div>
    <div class="risk-metric"><span>Стоп</span><strong>${r.stop_distance_pct}%</strong></div>
    <div class="risk-metric"><span>R:R</span><strong>1:${r.risk_reward || "—"}</strong></div>
    <div class="risk-metric"><span>Убыток по стопу</span><strong>$${r.max_loss_at_stop_usdt}</strong></div>
    <div class="risk-metric"><span>День (остаток)</span><strong>$${r.daily_budget_left_usdt}</strong></div>
  `;

  const wEl = $("riskWarnings");
  wEl.innerHTML = "";
  (r.warnings || []).forEach((w) => {
    const li = document.createElement("li");
    li.textContent = w;
    wEl.appendChild(li);
  });

  const rules = $("riskRules");
  rules.innerHTML = "";
  (r.rules_checklist || []).forEach((t) => {
    const li = document.createElement("li");
    li.textContent = t;
    rules.appendChild(li);
  });

  const tips = $("riskTips");
  tips.textContent = (r.tips || []).join(" · ");

  if (r.recommended_margin_usdt && !$("posMargin").value) {
    $("posMargin").value = r.recommended_margin_usdt;
  }
  if (r.recommended_leverage) {
    $("posLeverage").value = r.recommended_leverage;
  }
}

async function calculateRisk() {
  if (!activePair) {
    showError("Сначала выберите инструмент и нажмите «Анализ»");
    return;
  }
  const entry = parseFloat($("riskEntry").value);
  const stop = parseFloat($("riskStop").value);
  const balance = parseFloat($("riskBalance").value);
  if (!entry || !stop || !balance) {
    showError("Заполните депозит, вход и стоп");
    return;
  }

  const body = {
    pair: activePair,
    market: activeMarket,
    balance,
    entry,
    stop,
    risk_pct: parseFloat($("riskPct").value) || 1,
    max_daily_pct: parseFloat($("riskDailyMax").value) || 3,
    daily_loss_used_pct: parseFloat($("riskDailyUsed").value) || 0,
    open_trades: parseInt($("riskOpenTrades").value, 10) || 0,
    leverage: parseInt($("riskLeverage").value, 10) || 10,
    side: activeRiskSide,
  };
  const margin = parseFloat($("riskMargin").value);
  const tp = parseFloat($("riskTp").value);
  if (margin > 0) body.margin = margin;
  if (tp > 0) body.take_profit = tp;

  setLoading(true);
  try {
    const res = await fetch("/api/risk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const json = await res.json();
    setLoading(false);
    if (!json.ok) {
      showError(json.error || "Ошибка расчёта риска");
      return;
    }
    renderRisk(json.risk);
    switchTab("risk");
  } catch (_) {
    setLoading(false);
    showError("Не удалось рассчитать риск");
  }
}

function setActiveButton(pair) {
  document.querySelectorAll(".instrument-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.pair === pair);
  });
}

function instrumentFallbackLabel(item) {
  if (item.subtitle) return item.subtitle.slice(0, 3).toUpperCase();
  const id = item.id || "";
  if (id.includes("/")) return id.split("/")[0].slice(0, 3);
  return id.replace(".ME", "").slice(0, 3);
}

function instrumentIconHtml(item) {
  const fb = instrumentFallbackLabel(item);
  const regionClass = item.region === "ru" ? "ru" : item.region === "us" ? "us" : "";
  if (activeMarket === "forex" && FOREX_ICONS[item.id]) {
    return `<span class="inst-emoji">${FOREX_ICONS[item.id]}</span>`;
  }
  if (item.icon_url) {
    return `<span class="inst-fallback ${regionClass}">${fb}</span>
      <img class="inst-icon" src="${item.icon_url}" alt="" loading="lazy"
        onerror="this.style.display='none'" />`;
  }
  return `<span class="inst-fallback ${regionClass}">${fb}</span>`;
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

function renderPairsGrid(market) {
  const grid = $("pairsGrid");
  const title = $("instrumentListTitle");
  const regionTabs = $("stockRegionTabs");
  if (!grid) return;

  if (title) title.textContent = LIST_TITLES[market] || "Инструменты";
  regionTabs?.classList.toggle("hidden", market !== "stock");

  const q = instrumentSearchQuery.trim().toLowerCase();
  const items = getCatalogItems(market).filter((item) => {
    if (!q) return true;
    const hay = `${item.id} ${item.name} ${item.subtitle || ""}`.toLowerCase();
    return hay.includes(q);
  });

  grid.innerHTML = "";
  if (!items.length) {
    grid.innerHTML = '<p class="instrument-empty">Ничего не найдено</p>';
    return;
  }

  items.forEach((item) => {
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
    grid.appendChild(btn);
  });

  if (activePair) setActiveButton(activePair);
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
      <strong>[${tf.timeframe.toUpperCase()}] ${tf.trend}</strong>
      <span>${tf.market_structure} · ADX ${tf.adx}</span>
      <span>RSI ${tf.rsi} · MACD ${tf.macd_trend} · ${tf.macd_cross}</span>
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

  $("macdSummary1h").textContent = "1H: " + tf1h.macd_trend;
  $("macdSummary1h").className = "macd-summary " + macdTrendClass(tf1h.macd_trend);
  $("macdCross1h").textContent = tf1h.macd_cross;
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
      <span class="${macdTrendClass(tf.macd_trend)}">${tf.macd_trend}</span>
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
  $("deepRisk").textContent = `${deep.risk_label} (${deep.risk_score}/100)`;
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
  changeEl.textContent = sign + data.change_24h_pct.toFixed(2) + "% за 24ч";
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
  if ($("riskEntry") && ! $("riskEntry").value) $("riskEntry").value = data.price;
}

function renderPosition(p) {
  $("positionResult").classList.remove("hidden");
  $("posStatus").textContent = p.side_label + " · " + p.status;

  const curEl = $("pnlCurrent");
  curEl.textContent = (p.pnl_current_usdt >= 0 ? "+" : "") + p.pnl_current_usdt.toFixed(2) + " USDT";
  curEl.className = p.pnl_current_usdt >= 0 ? "pnl-pos" : "pnl-neg";
  $("pnlCurrentPct").textContent = (p.pnl_current_pct >= 0 ? "+" : "") + p.pnl_current_pct.toFixed(2) + "%";

  $("pnlTp").textContent = "+" + p.pnl_tp_usdt.toFixed(2) + " USDT";
  $("pnlTpPct").textContent = "+" + p.pnl_tp_pct.toFixed(2) + "%";

  $("pnlSl").textContent = p.pnl_sl_usdt.toFixed(2) + " USDT";
  $("pnlSlPct").textContent = p.pnl_sl_pct.toFixed(2) + "%";

  $("posStopPrice").textContent = money(p.stop_loss) + " (−" + p.sl_distance_pct + "%)";
  $("posStopReason").textContent = p.stop_reason;
  $("posTpPrice").textContent = money(p.take_profit) + " (+" + p.tp_distance_pct + "%)";
  $("posTpReason").textContent = p.tp_reason;
  $("posTp2").textContent = p.take_profit_2 ? money(p.take_profit_2) : "—";
  $("posPrices").textContent = money(p.entry_price) + " → " + money(p.current_price);
  $("posNotional").textContent =
    p.position_notional_usdt.toFixed(2) + " USDT · x" + p.leverage + " · " + p.quantity + " шт.";
  $("posRR").textContent = "1:" + p.risk_reward;
  $("posAdvice").textContent = p.advice;
  if ($("posMethodology")) $("posMethodology").textContent = p.methodology || "—";
  lastPosition = p;
  syncRiskFromPosition(p);
}

function applyPositionPreview(preview, side) {
  if (!preview) return;
  const p = side === "short" ? preview.short : preview.long;
  if (!p) return;
  if (!$("riskStop").value) $("riskStop").value = p.stop_loss;
  if (!$("riskTp").value) $("riskTp").value = p.take_profit;
  syncRiskFromPosition(p);
}

async function calculatePosition(silent) {
  if (!activePair) {
    showError("Сначала выберите пару и нажмите «Анализ»");
    return;
  }
  const entry = parseFloat($("posEntry").value);
  const margin = parseFloat($("posMargin").value);
  const leverage = parseInt($("posLeverage").value, 10);

  if (!entry || entry <= 0) {
    if (!silent) showError("Укажите цену входа (или кликните по графику)");
    return;
  }
  if (!margin || margin <= 0) {
    if (!silent) showError("Укажите сумму в USDT");
    return;
  }

  if (!silent) setLoading(true);
  try {
    const res = await fetch("/api/position", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pair: activePair,
        market: activeMarket,
        entry,
        margin,
        leverage: leverage || 1,
        side: activeSide,
      }),
    });
    const json = await res.json();
    if (!silent) setLoading(false);
    if (!json.ok) {
      if (!silent) showError(json.error || "Ошибка расчёта");
      return;
    }
    $("error").classList.add("hidden");
    renderPosition(json.position);
    if (json.market_price) lastMarketPrice = json.market_price;
  } catch (e) {
    if (!silent) setLoading(false);
    if (!silent) showError("Не удалось рассчитать позицию");
  }
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

    if (!$("posEntry").value && json.data.price) {
      $("posEntry").value = json.data.price;
    }
    if ($("riskEntry") && json.data.price) $("riskEntry").value = json.data.price;
    applyPositionPreview(json.position_preview, activeSide);
    $("newsAiResult")?.classList.add("hidden");
    if ($("tab-news")?.classList.contains("active")) loadNews();
  } catch (e) {
    setLoading(false);
    showError("Не удалось подключиться к серверу");
  }
}

document.querySelectorAll(".btn-market").forEach((btn) => {
  btn.addEventListener("click", () => {
    activeMarket = btn.dataset.market;
    document.querySelectorAll(".btn-market").forEach((b) => b.classList.toggle("active", b === btn));
    instrumentSearchQuery = "";
    if ($("instrumentSearch")) $("instrumentSearch").value = "";
    renderPairsGrid(activeMarket);
    const ph = PLACEHOLDERS[activeMarket];
    if (ph && $("customPair")) $("customPair").placeholder = ph;
    const first = getFirstInstrumentId(activeMarket);
    if (first) analyze(first);
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

$("instrumentSearch")?.addEventListener("input", (e) => {
  instrumentSearchQuery = e.target.value;
  renderPairsGrid(activeMarket);
});

$("btnAnalyze").addEventListener("click", () => analyze($("customPair").value));
$("btnRefresh").addEventListener("click", () => activePair && analyze(activePair, true));

$("customPair").addEventListener("keydown", (e) => {
  if (e.key === "Enter") analyze($("customPair").value);
});

document.getElementById("btnSideLong").addEventListener("click", () => {
  activeSide = "long";
  document.getElementById("btnSideLong").classList.add("active");
  document.getElementById("btnSideShort").classList.remove("active");
  if (lastAnalysisData?.position_preview) applyPositionPreview(lastAnalysisData.position_preview, "long");
  if ($("posEntry").value) calculatePosition(true);
});
document.getElementById("btnSideShort").addEventListener("click", () => {
  activeSide = "short";
  document.getElementById("btnSideShort").classList.add("active");
  document.getElementById("btnSideLong").classList.remove("active");
  if (lastAnalysisData?.position_preview) applyPositionPreview(lastAnalysisData.position_preview, "short");
  if ($("posEntry").value) calculatePosition(true);
});

$("btnUsePrice").addEventListener("click", () => {
  if (lastMarketPrice) {
    $("posEntry").value = lastMarketPrice;
    calculatePosition(true);
  } else showError("Сначала загрузите анализ пары");
});

$("btnCalcPosition").addEventListener("click", () => calculatePosition(false));

$("btnCalcRisk")?.addEventListener("click", () => calculateRisk());
$("btnRiskFromPosition")?.addEventListener("click", () => {
  if (lastPosition) {
    syncRiskFromPosition(lastPosition);
    calculateRisk();
  } else calculatePosition(false);
});

$("btnRiskLong")?.addEventListener("click", () => {
  activeRiskSide = "long";
  $("btnRiskLong").classList.add("active");
  $("btnRiskShort").classList.remove("active");
});
$("btnRiskShort")?.addEventListener("click", () => {
  activeRiskSide = "short";
  $("btnRiskShort").classList.add("active");
  $("btnRiskLong").classList.remove("active");
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

$("themeToggle")?.addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  applyTheme(next);
});
document.querySelectorAll("#modeToggle button").forEach((b) => {
  b.addEventListener("click", () => applyMode(b.dataset.mode));
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
  let savedTheme = "dark";
  let savedMode = "simple";
  try {
    savedTheme = localStorage.getItem("ui_theme") || "dark";
    savedMode = localStorage.getItem("ui_mode") || "simple";
  } catch (e) {}
  applyTheme(savedTheme);
  applyMode(savedMode);
  $("fundingPanel")?.classList.add("hidden");
  renderPairsGrid("crypto");
  switchTab("overview");
  analyze("ETH/USDT");
});
