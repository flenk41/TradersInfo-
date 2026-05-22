/**
 * График: свечи, зоны S/R (квадраты), фандинг CoinGlass-style.
 */
const TradingChart = (() => {
  let mainChart = null;
  let fundingChart = null;
  let candleSeries = null;
  let fundingSeries = null;
  let priceLineRefs = {};
  let onPricePick = null;
  let lastCandles = [];
  let mainContainer = null;
  let zoneOverlay = null;
  let resizeObserver = null;

  const COLORS = {
    entry: "#3b82f6",
    stop: "#ef4444",
    tp: "#22c55e",
    tp2: "#86efac",
    current: "#eab308",
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
    if (!zoneOverlay || zoneOverlay.classList.contains("hidden")) return;
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
      box.title = `${zone.label}: $${zone.price}`;

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
  }

  function setCandles(candles) {
    if (!candleSeries || !candles?.length) return;
    lastCandles = candles;
    candleSeries.setData(candles);
    mainChart.timeScale().fitContent();
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

  async function loadPair(pair, market) {
    const m = market || "crypto";
    const base = `pair=${encodeURIComponent(pair)}&interval=1h&limit=200&market=${encodeURIComponent(m)}`;
    const kRes = await fetch(`/api/klines?${base}`);
    const kJson = await kRes.json();
    if (kJson.ok) setCandles(kJson.candles);

    if (m === "crypto") {
      setFundingVisible(true);
      const fRes = await fetch(`/api/funding-history?${base.replace("interval=1h&", "")}&limit=90`);
      const fJson = await fRes.json();
      if (fJson.ok) setFundingHistory(fJson.points);
    } else {
      setFundingVisible(false);
      if (fundingSeries) fundingSeries.setData([]);
    }
    return kJson.ok;
  }

  function applyAnalysis(data) {
    if (!data) return;
    setTrendBar(data);
    if (document.getElementById("bullishReasons")) renderReasons(data);
    setZones();
  }

  function setEntryPicker(callback) {
    onPricePick = callback;
  }

  return {
    init,
    setCandles,
    setLevels,
    setTrendBar,
    setZones,
    loadPair,
    setEntryPicker,
    applyAnalysis,
    setFundingHistory,
    resize,
    clearFunding,
  };
})();
