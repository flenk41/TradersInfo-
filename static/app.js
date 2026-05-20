let activePair = null;
let lastMarketPrice = null;
let activeSide = "long";

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

function verdictClass(verdict) {
  if (!verdict) return "";
  if (verdict.includes("ВХОДИТЬ")) return "verdict-enter";
  if (verdict.includes("ЖДАТЬ")) return "verdict-wait";
  return "verdict-no";
}

function setLoading(on) {
  $("loading").classList.toggle("hidden", !on);
  $("results").classList.toggle("hidden", on);
  if (on) $("error").classList.add("hidden");
}

function showError(msg) {
  $("error").textContent = msg;
  $("error").classList.remove("hidden");
  $("results").classList.add("hidden");
}

function setActiveButton(pair) {
  document.querySelectorAll(".btn-pair").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.pair === pair);
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
    tag.textContent = "$" + formatPrice(l);
    el.appendChild(tag);
  });
}

function renderTimeframes(timeframes) {
  const el = $("timeframes");
  el.innerHTML = "";
  timeframes.forEach((tf) => {
    const div = document.createElement("div");
    div.className = "tf-item";
    const sma = tf.sma200 ? "$" + formatPrice(tf.sma200) : "—";
    div.innerHTML = `
      <strong>[${tf.timeframe.toUpperCase()}] ${tf.trend} (${tf.trend_strength})</strong>
      <span>RSI ${tf.rsi} · MACD ${tf.macd_trend} · ${tf.macd_cross}</span>
      <span>EMA20 $${formatPrice(tf.ema20)} · EMA50 $${formatPrice(tf.ema50)} · SMA200 ${sma}</span>
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

function renderTrade(trade) {
  if (!trade) return;
  $("bestAction").textContent = trade.best_action;
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
    row.innerHTML = `<span class="fib-label">${lvl.label}</span><span>$${formatPrice(lvl.price)}</span>`;
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
  const changeEl = $("priceChange");
  const sign = data.change_24h_pct >= 0 ? "+" : "";
  $("priceMain").textContent = "$" + formatPrice(data.price);
  changeEl.textContent = sign + data.change_24h_pct.toFixed(2) + "% за 24ч";
  changeEl.className = "price-change " + (data.change_24h_pct >= 0 ? "up" : "down");

  $("high24").textContent = "$" + formatPrice(data.high_24h);
  $("low24").textContent = "$" + formatPrice(data.low_24h);
  $("volume24").textContent = "$" + formatVolume(data.volume_24h);

  renderTrade(data.trade);

  $("overallTrend").textContent = data.overall_trend;
  $("trendSummary").textContent = data.trend_summary;
  renderTimeframes(data.timeframes);
  renderMacd(data.timeframes);

  if (data.volatility) {
    const v = data.volatility;
    $("volLevel").textContent = v.level;
    $("volDesc").textContent = v.description;
    $("atr").textContent = "$" + formatPrice(v.atr_14);
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
    $("markPrice").textContent = "$" + formatPrice(f.mark_price);
    $("indexPrice").textContent = "$" + formatPrice(f.index_price);
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

  $("results").classList.remove("hidden");
  lastMarketPrice = data.price;
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

  $("posStopPrice").textContent = "$" + formatPrice(p.stop_loss) + " (−" + p.sl_distance_pct + "%)";
  $("posStopReason").textContent = p.stop_reason;
  $("posTpPrice").textContent = "$" + formatPrice(p.take_profit) + " (+" + p.tp_distance_pct + "%)";
  $("posTpReason").textContent = p.tp_reason;
  $("posPrices").textContent =
    "$" + formatPrice(p.entry_price) + " → $" + formatPrice(p.current_price);
  $("posNotional").textContent =
    p.position_notional_usdt.toFixed(2) + " USDT · x" + p.leverage + " · " + p.quantity + " шт.";
  $("posRR").textContent = "1:" + p.risk_reward;
  $("posAdvice").textContent = p.advice;
}

async function calculatePosition() {
  if (!activePair) {
    showError("Сначала выберите пару и нажмите «Анализ»");
    return;
  }
  const entry = parseFloat($("posEntry").value);
  const margin = parseFloat($("posMargin").value);
  const leverage = parseInt($("posLeverage").value, 10);

  if (!entry || entry <= 0) {
    showError("Укажите цену входа");
    return;
  }
  if (!margin || margin <= 0) {
    showError("Укажите сумму в USDT");
    return;
  }

  setLoading(true);
  try {
    const res = await fetch("/api/position", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pair: activePair,
        entry,
        margin,
        leverage: leverage || 1,
        side: activeSide,
      }),
    });
    const json = await res.json();
    setLoading(false);
    if (!json.ok) {
      showError(json.error || "Ошибка расчёта");
      return;
    }
    $("error").classList.add("hidden");
    renderPosition(json.position);
    if (json.market_price) lastMarketPrice = json.market_price;
  } catch (e) {
    setLoading(false);
    showError("Не удалось рассчитать позицию");
  }
}

async function analyze(pair) {
  if (!pair || !pair.trim()) return;

  pair = pair.trim().toUpperCase();
  if (!pair.includes("/")) {
    const base = pair.replace("USDT", "");
    pair = base + "/USDT";
  }

  activePair = pair;
  $("currentPair").textContent = pair;
  $("customPair").value = pair;
  $("btnRefresh").disabled = false;
  setActiveButton(pair);
  setLoading(true);

  try {
    const res = await fetch("/api/analyze?pair=" + encodeURIComponent(pair));
    const json = await res.json();
    setLoading(false);

    if (!json.ok) {
      showError(json.error || "Ошибка загрузки");
      return;
    }
    render(json.data);
  } catch (e) {
    setLoading(false);
    showError("Не удалось подключиться к серверу");
  }
}

document.querySelectorAll(".btn-pair").forEach((btn) => {
  btn.addEventListener("click", () => analyze(btn.dataset.pair));
});

$("btnAnalyze").addEventListener("click", () => analyze($("customPair").value));
$("btnRefresh").addEventListener("click", () => activePair && analyze(activePair));

$("customPair").addEventListener("keydown", (e) => {
  if (e.key === "Enter") analyze($("customPair").value);
});

document.getElementById("btnSideLong").addEventListener("click", () => {
  activeSide = "long";
  document.getElementById("btnSideLong").classList.add("active");
  document.getElementById("btnSideShort").classList.remove("active");
});
document.getElementById("btnSideShort").addEventListener("click", () => {
  activeSide = "short";
  document.getElementById("btnSideShort").classList.add("active");
  document.getElementById("btnSideLong").classList.remove("active");
});

$("btnUsePrice").addEventListener("click", () => {
  if (lastMarketPrice) $("posEntry").value = lastMarketPrice;
  else showError("Сначала загрузите анализ пары");
});

$("btnCalcPosition").addEventListener("click", calculatePosition);

analyze("ETH/USDT");
