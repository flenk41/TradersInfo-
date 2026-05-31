/**
 * График: свечи, зоны S/R (квадраты), фандинг CoinGlass-style.
 */
const TradingChart = (() => {
  let mainChart = null;
  let fundingChart = null;
  let candleSeries = null;
  let volumeSeries = null;
  let fundingSeries = null;
  let priceLineRefs = {};
  let entryZoneLines = [];
  let entryConfig = {}; // { L1:{entry,stop,take}, S2:{...} }
  let lastEntryZones = { long: [], short: [] };
  let lastImbalances = [];
  let imbalancesVisible = false;
  let onPricePick = null;
  let onRefresh = null;
  let lastCandles = [];
  let mainContainer = null;
  let zoneOverlay = null;
  let resizeObserver = null;
  let liveTimer = null;
  let curSymbol = "$";
  let live = { pair: null, market: "crypto", interval: "1h" };
  const LIVE_MS = 8000;
  const VOL_UP = "rgba(34, 197, 94, 0.5)";
  const VOL_DOWN = "rgba(239, 68, 68, 0.5)";

  const COLORS = {
    entry: "#3b82f6",
    stop: "#ef4444",
    tp: "#22c55e",
    tp2: "#86efac",
    current: "#eab308",
    longEntry: "#2dd4bf",
    shortEntry: "#a855f7",
    supportFill: "rgba(34, 197, 94, 0.22)",
    supportBorder: "rgba(34, 197, 94, 0.75)",
    resistFill: "rgba(239, 68, 68, 0.22)",
    resistBorder: "rgba(239, 68, 68, 0.75)",
    fundingPos: "#ef4444",
    fundingNeg: "#22c55e",
  };

  function init(mainEl, fundingEl, overlayEl) {
    if (!window.LightweightCharts) return;
    mainContainer = mainEl;
    zoneOverlay = overlayEl;

    if (mainChart) mainChart.remove();
    if (fundingChart) fundingChart.remove();

    const parent = mainEl.parentElement;
    const w = parent?.clientWidth || mainEl.clientWidth || 800;
    const h = Math.max(280, (parent?.clientHeight || 360) - 8);

    mainChart = LightweightCharts.createChart(mainEl, {
      layout: { background: { color: "#0b0f14" }, textColor: "#8b9cb3" },
      grid: { vertLines: { color: "#1a2330" }, horzLines: { color: "#1a2330" } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#243044" },
      timeScale: { borderColor: "#243044", timeVisible: true },
      width: w,
      height: h,
    });

    const fw = fundingEl.clientWidth || w;
    fundingChart = LightweightCharts.createChart(fundingEl, {
      layout: { background: { color: "#0b0f14" }, textColor: "#8b9cb3" },
      grid: { vertLines: { color: "#1a2330" }, horzLines: { color: "#1a2330" } },
      rightPriceScale: {
        borderColor: "#243044",
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: { borderColor: "#243044", visible: true, timeVisible: true },
      width: fw,
      height: 88,
    });

    candleSeries = mainChart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      // Масштаб цены строим ТОЛЬКО по свечам, игнорируя ценовые линии (входы/стоп/тейк),
      // иначе линия с чужого масштаба растягивает шкалу и сплющивает свечи.
      autoscaleInfoProvider: (original) => {
        if (!lastCandles.length) return original();
        let lo = Infinity;
        let hi = -Infinity;
        for (const c of lastCandles) {
          if (c.low < lo) lo = c.low;
          if (c.high > hi) hi = c.high;
        }
        if (!isFinite(lo) || !isFinite(hi) || hi <= 0) return original();
        const pad = (hi - lo) * 0.08 || hi * 0.01;
        return { priceRange: { minValue: lo - pad, maxValue: hi + pad } };
      },
    });

    volumeSeries = mainChart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    mainChart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    fundingSeries = fundingChart.addHistogramSeries({
      priceFormat: { type: "custom", formatter: (v) => v.toFixed(4) + "%" },
      priceScaleId: "right",
    });

    fundingChart.priceScale("right").applyOptions({
      scaleMargins: { top: 0.15, bottom: 0.05 },
    });

    mainChart.subscribeClick((param) => {
      if (!param.point || !candleSeries || !onPricePick) return;
      const price = candleSeries.coordinateToPrice(param.point.y);
      if (price != null && price > 0) onPricePick(price);
    });

    mainChart.timeScale().subscribeVisibleLogicalRangeChange(() => updateZoneBoxes());
    mainChart.timeScale().subscribeVisibleTimeRangeChange(() => updateZoneBoxes());

    if (resizeObserver) resizeObserver.disconnect();
    resizeObserver = new ResizeObserver(() => {
      resize();
    });
    resizeObserver.observe(parent || mainEl);
  }

  function resize() {
    if (!mainContainer || !mainChart) return;
    const parent = mainContainer.parentElement;
    const width = parent?.clientWidth || mainContainer.clientWidth || 800;
    const height = Math.max(280, (parent?.clientHeight || 360) - 8);
    mainChart.applyOptions({ width, height });
    if (fundingChart) {
      const fc = document.getElementById("fundingChartContainer");
      fundingChart.applyOptions({ width: fc?.clientWidth || width, height: 88 });
    }
  }

  function clearFunding() {
    if (fundingSeries) fundingSeries.setData([]);
    const panel = document.getElementById("fundingPanel");
    if (panel) panel.classList.add("hidden");
  }

  let zoneData = { support: [], resistance: [], longEntry: [], shortEntry: [] };

  function setZones() {
    zoneData = { support: [], resistance: [], longEntry: [], shortEntry: [] };
    if (zoneOverlay) zoneOverlay.innerHTML = "";
  }

  function updateZoneBoxes() {
    if (!zoneOverlay) return;
    if (!candleSeries || !mainChart || !lastCandles.length) return;
    if (!mainContainer || mainContainer.offsetHeight < 50) return;
    zoneOverlay.innerHTML = "";

    const tStart = lastCandles[0].time;
    const tEnd = lastCandles[lastCandles.length - 1].time;
    const x1 = mainChart.timeScale().timeToCoordinate(tStart);
    const x2 = mainChart.timeScale().timeToCoordinate(tEnd);
    if (x1 == null || x2 == null) return;

    const left = Math.min(x1, x2);
    const width = Math.abs(x2 - x1);

    const drawZone = (zone, kind) => {
      const yHigh = candleSeries.priceToCoordinate(zone.high);
      const yLow = candleSeries.priceToCoordinate(zone.low);
      if (yHigh == null || yLow == null) return;

      const top = Math.min(yHigh, yLow);
      const height = Math.abs(yLow - yHigh);
      if (height < 2) return;

      const box = document.createElement("div");
      box.className = `zone-box zone-${kind}`;
      box.style.left = `${left}px`;
      box.style.width = `${width}px`;
      box.style.top = `${top}px`;
      box.style.height = `${height}px`;
      box.title = `${zone.label}: ${curSymbol}${zone.price}`;

      const label = document.createElement("span");
      label.className = "zone-label";
      label.textContent = zone.label;
      box.appendChild(label);
      zoneOverlay.appendChild(box);
    };

    zoneData.longEntry.forEach((z) => drawZone(z, "long-entry"));
    zoneData.shortEntry.forEach((z) => drawZone(z, "short-entry"));
    zoneData.support.forEach((z) => drawZone(z, "support"));
    zoneData.resistance.forEach((z) => drawZone(z, "resistance"));
    if (imbalancesVisible) {
      lastImbalances.forEach((z) =>
        drawZone(z, z.kind === "bullish" ? "imbalance-bull" : "imbalance-bear")
      );
    }
  }

  function setImbalances(zones) {
    lastImbalances = Array.isArray(zones) ? zones : [];
    updateZoneBoxes();
  }

  function toggleImbalances(show) {
    imbalancesVisible = !!show;
    if (zoneOverlay) zoneOverlay.classList.toggle("hidden", !imbalancesVisible);
    updateZoneBoxes();
    return imbalancesVisible;
  }

  function _volBar(c) {
    return {
      time: c.time,
      value: c.volume || 0,
      color: c.close >= c.open ? VOL_UP : VOL_DOWN,
    };
  }

  function setCandles(candles) {
    if (!candleSeries || !candles?.length) return;
    lastCandles = candles;
    candleSeries.setData(candles);
    if (volumeSeries) volumeSeries.setData(candles.map(_volBar));
    mainChart.timeScale().fitContent();
    // принудительно пересчитываем ценовую шкалу под новые свечи
    try {
      mainChart.priceScale("right").applyOptions({ autoScale: true });
    } catch (_) {}
    setTimeout(updateZoneBoxes, 50);
  }

  function setFundingHistory(points) {
    if (!fundingSeries || !points?.length) return;
    const data = points.map((p) => ({
      time: p.time,
      value: p.value,
      color: p.value >= 0 ? COLORS.fundingPos : COLORS.fundingNeg,
    }));
    fundingSeries.setData(data);
    fundingChart.timeScale().fitContent();

    if (lastCandles.length) {
      const from = lastCandles[0].time;
      const to = lastCandles[lastCandles.length - 1].time;
      fundingChart.timeScale().setVisibleRange({ from, to });
    }

    mainChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range && fundingChart) {
        try {
          const from = mainChart.timeScale().coordinateToTime(0);
          const to = mainChart.timeScale().coordinateToTime(mainContainer.clientWidth);
          if (from && to) fundingChart.timeScale().setVisibleRange({ from, to });
        } catch (_) {}
      }
    });
  }

  function removeLines() {
    if (!candleSeries) return;
    Object.values(priceLineRefs).forEach((line) => {
      try {
        candleSeries.removePriceLine(line);
      } catch (_) {}
    });
    priceLineRefs = {};
  }

  function addLine(key, price, color, title, style) {
    if (!candleSeries || price == null || price <= 0) return;
    if (priceLineRefs[key]) {
      try {
        candleSeries.removePriceLine(priceLineRefs[key]);
      } catch (_) {}
    }
    priceLineRefs[key] = candleSeries.createPriceLine({
      price,
      color,
      lineWidth: 2,
      lineStyle: style ?? LightweightCharts.LineStyle.Solid,
      axisLabelVisible: true,
      title,
    });
  }

  function setLevels({ entry, stop, tp, tp2, current, side }) {
    removeLines();
    if (entry) {
      addLine(
        "entry",
        entry,
        COLORS.entry,
        side === "short" ? "Вход SHORT" : "Вход LONG",
        LightweightCharts.LineStyle.Solid
      );
    }
    if (stop) addLine("stop", stop, COLORS.stop, "Stop", LightweightCharts.LineStyle.Dashed);
    if (tp) addLine("tp", tp, COLORS.tp, "TP", LightweightCharts.LineStyle.Solid);
    if (tp2) addLine("tp2", tp2, COLORS.tp2, "TP2", LightweightCharts.LineStyle.Dotted);
    if (current) addLine("current", current, COLORS.current, "Сейчас", LightweightCharts.LineStyle.Solid);
  }

  function setTrendBar(data) {
    const el = document.getElementById("chartTrendBar");
    if (!el || !data) return;
    const bias = data.bias;
    el.innerHTML = `
      <div class="chart-trend-item">
        <span class="ct-label">Тренд</span>
        <strong class="ct-value">${data.overall_trend || "—"}</strong>
      </div>
      <div class="chart-trend-item">
        <span class="ct-label">HTF Bias</span>
        <strong class="ct-value bias-${bias?.direction || "neutral"}">${bias?.direction?.toUpperCase() || "—"}</strong>
      </div>
      <div class="chart-trend-item wide">
        <span class="ct-label">Сводка</span>
        <span class="ct-summary">${data.trend_summary || ""}</span>
      </div>
    `;
  }

  function renderReasons(data) {
    const bullEl = document.getElementById("bullishReasons");
    const bearEl = document.getElementById("bearishReasons");
    if (!bullEl || !bearEl) return;

    bullEl.innerHTML = "";
    bearEl.innerHTML = "";

    (data.bullish_reasons || []).forEach((r) => {
      const li = document.createElement("li");
      li.textContent = r;
      bullEl.appendChild(li);
    });
    (data.bearish_reasons || []).forEach((r) => {
      const li = document.createElement("li");
      li.textContent = r;
      bearEl.appendChild(li);
    });

    if (!(data.bearish_reasons || []).length) {
      bearEl.innerHTML = "<li>Явных медвежьих факторов мало</li>";
    }
    if (!(data.bullish_reasons || []).length) {
      bullEl.innerHTML = "<li>Явных бычьих факторов мало</li>";
    }
  }

  function setFundingVisible(visible) {
    const wrap = document.getElementById("fundingPanel");
    if (wrap) wrap.classList.toggle("hidden", !visible);
  }

  async function loadPair(pair, market, interval) {
    const m = market || "crypto";
    const tf = interval || "1h";
    // При смене инструмента убираем старые ценовые линии: иначе линии входа/уровни
    // с другого ценового масштаба (напр. BTC 76000 vs EUR 1.16) растягивают автошкалу
    // и новые свечи сплющиваются в невидимую полоску.
    const pairChanged = live.pair !== pair;
    if (pairChanged) {
      clearEntryZones();
      removeLines();
    }
    live = { pair, market: m, interval: tf };
    const base = `pair=${encodeURIComponent(pair)}&interval=${tf}&limit=200&market=${encodeURIComponent(m)}`;
    const kRes = await fetch(`/api/klines?${base}`);
    const kJson = await kRes.json();
    if (kJson.ok) setCandles(kJson.candles);

    if (m === "crypto") {
      setFundingVisible(true);
      const fRes = await fetch(
        `/api/funding-history?pair=${encodeURIComponent(pair)}&market=${m}&limit=90`
      );
      const fJson = await fRes.json();
      if (fJson.ok) setFundingHistory(fJson.points);
    } else {
      setFundingVisible(false);
      if (fundingSeries) fundingSeries.setData([]);
    }
    startLive();
    return kJson.ok;
  }

  let liveCountdown = 0;

  function updateTimerDisplay() {
    const el = document.getElementById("chartTimer");
    if (!el) return;
    if (!live.pair) {
      el.textContent = "↻ —";
      return;
    }
    if (document.hidden) {
      el.textContent = "↻ пауза";
      return;
    }
    el.textContent = `↻ ${Math.max(0, liveCountdown)}с`;
  }

  function startLive() {
    stopLive();
    liveCountdown = LIVE_MS / 1000;
    updateTimerDisplay();
    liveTimer = setInterval(() => {
      if (document.hidden) {
        updateTimerDisplay();
        return;
      }
      liveCountdown -= 1;
      if (liveCountdown <= 0) {
        pollLive();
        liveCountdown = LIVE_MS / 1000;
      }
      updateTimerDisplay();
    }, 1000);
  }

  function stopLive() {
    if (liveTimer) {
      clearInterval(liveTimer);
      liveTimer = null;
    }
    updateTimerDisplay();
  }

  async function pollLive() {
    if (!live.pair || !candleSeries || document.hidden) return;
    try {
      const base = `pair=${encodeURIComponent(live.pair)}&interval=${live.interval}&limit=3&market=${encodeURIComponent(live.market)}`;
      const res = await fetch(`/api/klines?${base}`);
      const json = await res.json();
      if (!json.ok || !json.candles?.length) return;
      // lightweight-charts .update() кидает ошибку для свечей СТАРШЕ последней,
      // поэтому обновляем только текущую (или более новую) свечу.
      const lastTime = lastCandles.length ? lastCandles[lastCandles.length - 1].time : 0;
      json.candles.forEach((c) => {
        if (c.time < lastTime) return;
        candleSeries.update(c);
        if (volumeSeries) volumeSeries.update(_volBar(c));
      });
      const latest = json.candles[json.candles.length - 1];
      if (lastCandles.length) {
        if (latest.time === lastTime) {
          lastCandles[lastCandles.length - 1] = latest;
        } else if (latest.time > lastTime) {
          lastCandles.push(latest);
        }
      }
    } catch (_) {}
    // Помимо свечей — даём знать приложению обновить анализ (с троттлингом на его стороне).
    if (typeof onRefresh === "function") {
      try { onRefresh(); } catch (_) {}
    }
  }

  function clearEntryZones() {
    if (!candleSeries) return;
    entryZoneLines.forEach((l) => {
      try {
        candleSeries.removePriceLine(l);
      } catch (_) {}
    });
    entryZoneLines = [];
  }

  function _addEntryLine(price, color, style, title, labelVisible, width) {
    if (!price || price <= 0) return;
    entryZoneLines.push(
      candleSeries.createPriceLine({
        price,
        color,
        lineWidth: width || 2,
        lineStyle: style,
        axisLabelVisible: !!labelVisible,
        title: title || "",
      })
    );
  }

  function _cfg(id) {
    return entryConfig[id] || { entry: true, stop: false, take: false };
  }

  function drawEntryZones() {
    clearEntryZones();
    if (!candleSeries) return;
    const dash = LightweightCharts.LineStyle.Dashed;
    const dot = LightweightCharts.LineStyle.Dotted;
    const longs = (lastEntryZones.long || []).slice(0, 3);
    const shorts = (lastEntryZones.short || []).slice(0, 3);

    longs.forEach((z, i) => {
      const c = _cfg("L" + (i + 1));
      if (c.stop) _addEntryLine(z.stop, COLORS.stop, dot, "", false, 1);
      if (c.take) _addEntryLine(z.take, COLORS.tp, dot, "", false, 1);
      if (c.entry) _addEntryLine(z.price, COLORS.longEntry, dash, "▲ " + (window.I18N ? I18N.tr("ЛОНГ") : "ЛОНГ") + " " + (i + 1), true, 2);
    });

    shorts.forEach((z, i) => {
      const c = _cfg("S" + (i + 1));
      if (c.stop) _addEntryLine(z.stop, COLORS.stop, dot, "", false, 1);
      if (c.take) _addEntryLine(z.take, COLORS.tp, dot, "", false, 1);
      if (c.entry) _addEntryLine(z.price, COLORS.shortEntry, dash, "▼ " + (window.I18N ? I18N.tr("ШОРТ") : "ШОРТ") + " " + (i + 1), true, 2);
    });
  }

  function setEntryZones(longZones, shortZones) {
    lastEntryZones = { long: longZones || [], short: shortZones || [] };
    drawEntryZones();
  }

  function setEntryConfig(config) {
    entryConfig = config || {};
    drawEntryZones();
  }

  function applyAnalysis(data) {
    if (!data) return;
    setTrendBar(data);
    if (document.getElementById("bullishReasons")) renderReasons(data);
    setZones();
    setEntryZones(data.long_entry_zones, data.short_entry_zones);
  }

  function setEntryPicker(callback) {
    onPricePick = callback;
  }

  function setRefreshCallback(callback) {
    onRefresh = callback;
  }

  function setCurrency(symbol) {
    curSymbol = symbol || "$";
  }

  const CHART_THEMES = {
    dark: { bg: "#0b0f14", text: "#8b9cb3", grid: "#1a2330", border: "#243044" },
    light: { bg: "#ffffff", text: "#5e6b80", grid: "#e7ecf4", border: "#d7deea" },
  };
  let curTheme = "dark";

  function setTheme(theme) {
    curTheme = CHART_THEMES[theme] ? theme : "dark";
    const t = CHART_THEMES[curTheme];
    const layout = { background: { color: t.bg }, textColor: t.text };
    const grid = { vertLines: { color: t.grid }, horzLines: { color: t.grid } };
    if (mainChart) {
      mainChart.applyOptions({
        layout,
        grid,
        rightPriceScale: { borderColor: t.border },
        timeScale: { borderColor: t.border },
      });
    }
    if (fundingChart) {
      fundingChart.applyOptions({ layout, grid, rightPriceScale: { borderColor: t.border } });
    }
  }

  return {
    init,
    setCandles,
    setLevels,
    setTrendBar,
    setZones,
    loadPair,
    setEntryPicker,
    setRefreshCallback,
    applyAnalysis,
    setFundingHistory,
    resize,
    clearFunding,
    stopLive,
    setCurrency,
    setTheme,
    setEntryZones,
    setEntryConfig,
    setImbalances,
    toggleImbalances,
  };
})();
