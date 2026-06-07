/**
 * ChartDraw — настоящие инструменты рисования поверх lightweight-charts
 * (трендлинии, лучи, горизонтали, фибоначчи, прямоугольники, кисть).
 *
 * Отличие от прежнего freehand-оверлея: фигуры привязаны к данным графика
 * (time/price), а не к пикселям. При зуме/панораме/догрузке свечей они
 * остаются на «своих» свечах и ценах — как в TradingView. Хранятся в
 * localStorage по паре, редактируются (перетаскивание, ручки), удаляются.
 */
const ChartDraw = (() => {
  let chart = null, series = null, container = null, canvas = null, ctx = null;
  let barCount = 0;
  let shapes = [];          // фигуры текущей пары
  let storeKey = "";        // ключ localStorage
  let tool = "cursor";      // активный инструмент
  let lastTool = "trend";   // последний инструмент рисования (для авто-выбора при включении)
  let color = "#a855f7";
  let lineWidth = 2;
  let draft = null;         // фигура в процессе создания
  let selected = -1;        // индекс выбранной фигуры
  let drag = null;          // активное перетаскивание
  let palette = null, hint = null;
  let editing = false;      // открыта ли палитра / включено редактирование

  const HIT = 7;            // радиус попадания, px
  const HANDLE = 4;         // полуразмер ручки, px
  const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

  // ── привязка ────────────────────────────────────────────────────────────
  function attach(refs) {
    chart = refs.chart; series = refs.series;
    container = refs.container; canvas = refs.canvas;
    if (!canvas) return;
    ctx = canvas.getContext("2d");
    buildPalette();
    bindCanvas();
    resize();
    try { chart.timeScale().subscribeVisibleLogicalRangeChange(redraw); } catch (_) {}
    window.addEventListener("keydown", onKey);
  }

  function setBars(n) { barCount = n || 0; }

  function setPair(market, pair) {
    storeKey = "chart_drawings:" + (market || "?") + ":" + (pair || "?");
    selected = -1; draft = null; drag = null;
    shapes = load();
    redraw();
  }

  // ── localStorage ──────────────────────────────────────────────────────────
  function load() {
    try {
      const raw = localStorage.getItem(storeKey);
      const arr = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(arr)) return [];
      // отсеять повреждённые записи (нет точек/цены) — иначе redraw упадёт
      return arr.filter((s) =>
        s && typeof s.type === "string" &&
        Array.isArray(s.pts) && s.pts.length &&
        s.pts.every((p) => p && typeof p.price === "number")
      );
    } catch (_) { return []; }
  }
  function save() {
    if (!storeKey) return;
    try {
      if (shapes.length) localStorage.setItem(storeKey, JSON.stringify(shapes));
      else localStorage.removeItem(storeKey);
    } catch (_) {}
  }

  // ── координаты: данные ⇄ пиксели ──────────────────────────────────────────
  function ts() { return chart.timeScale(); }
  function lastIdx() { return Math.max(0, barCount - 1); }

  function anchorX(a) {
    if (a.time != null) {
      const x = ts().timeToCoordinate(a.time);
      if (x != null) return x;
    }
    return ts().logicalToCoordinate(lastIdx() + (a.off || 0));
  }
  function priceY(p) { return series.priceToCoordinate(p); }

  // создать якорь из пиксельных координат (привязка к свече/цене)
  function makeAnchor(x, y) {
    const price = series.coordinateToPrice(y);
    const logical = ts().coordinateToLogical(x);
    const a = { price };
    const last = lastIdx();
    if (logical != null && logical <= last + 0.5) {
      const t = ts().coordinateToTime(x);
      if (t != null) { a.time = t; return a; }
    }
    a.off = logical == null ? 0 : Math.round(logical - last);
    return a;
  }

  function screenPts(s) {
    return (s.pts || []).map((a) => ({ x: anchorX(a), y: priceY(a.price) }));
  }

  // ── размеры/DPR ───────────────────────────────────────────────────────────
  function resize() {
    if (!canvas || !container) return;
    const w = container.clientWidth || 800;
    const h = container.clientHeight || 360;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    redraw();
  }
  function W() { return canvas.width / (window.devicePixelRatio || 1); }
  function H() { return canvas.height / (window.devicePixelRatio || 1); }

  // ── отрисовка ─────────────────────────────────────────────────────────────
  function redraw() {
    if (!ctx || !canvas) return;
    ctx.clearRect(0, 0, W(), H());
    // фигуры видны всегда; выделение/ручки — только в режиме редактирования
    shapes.forEach((s, i) => drawShape(s, editing && i === selected));
    if (draft) drawShape(draft, false);
  }

  function stroke(p, col, w, dash) {
    ctx.save();
    ctx.strokeStyle = col; ctx.lineWidth = w || 2; ctx.lineCap = "round";
    ctx.setLineDash(dash || []);
    p(); ctx.restore();
  }

  function drawShape(s, sel) {
    const col = s.color || color, w = s.width || lineWidth;
    const pts = screenPts(s);

    if (s.type === "hline") {
      const y = priceY(s.pts[0].price);
      if (y == null) return;
      stroke(() => { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W(), y); ctx.stroke(); }, col, w);
      priceTag(s.pts[0].price, y, col);
    } else if (s.type === "trend") {
      const [a, b] = pts; if (!a || !b) return;
      stroke(() => { ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }, col, w);
    } else if (s.type === "ray") {
      const [a, b] = pts; if (!a || !b) return;
      const e = extend(a, b);
      stroke(() => { ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(e.x, e.y); ctx.stroke(); }, col, w);
    } else if (s.type === "rect") {
      const [a, b] = pts; if (!a || !b) return;
      const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y);
      const rw = Math.abs(b.x - a.x), rh = Math.abs(b.y - a.y);
      ctx.save();
      ctx.fillStyle = hexA(col, 0.12); ctx.fillRect(x, y, rw, rh);
      ctx.strokeStyle = col; ctx.lineWidth = w; ctx.strokeRect(x, y, rw, rh);
      ctx.restore();
    } else if (s.type === "fib") {
      const [a, b] = pts; if (!a || !b) return;
      const p0 = s.pts[0].price, p1 = s.pts[1].price;
      const xL = Math.min(a.x, b.x), xR = Math.max(a.x, b.x);
      stroke(() => { ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }, hexA(col, 0.5), 1, [4, 4]);
      FIB_LEVELS.forEach((lv) => {
        const price = p0 + (p1 - p0) * lv;
        const y = priceY(price); if (y == null) return;
        stroke(() => { ctx.beginPath(); ctx.moveTo(xL, y); ctx.lineTo(Math.max(xR, W() - 4), y); ctx.stroke(); }, col, 1, lv === 0 || lv === 1 ? [] : [2, 3]);
        ctx.save();
        ctx.fillStyle = col; ctx.font = "10px ui-monospace,monospace";
        ctx.fillText(lv.toFixed(3) + "  " + fmt(price), xL + 3, y - 2);
        ctx.restore();
      });
    } else if (s.type === "brush") {
      if (pts.length < 2) return;
      stroke(() => {
        ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
        for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
        ctx.stroke();
      }, col, w);
    }

    if (sel) drawHandles(s, pts);
  }

  function drawHandles(s, pts) {
    let hs = [];
    if (s.type === "hline") {
      const y = priceY(s.pts[0].price);
      hs = [{ x: W() / 2, y }];
    } else if (s.type === "brush") {
      hs = [];
    } else {
      hs = pts;
    }
    ctx.save();
    ctx.fillStyle = "#fff"; ctx.strokeStyle = "#6366f1"; ctx.lineWidth = 1.5;
    hs.forEach((p) => {
      if (p.x == null || p.y == null) return;
      ctx.beginPath(); ctx.rect(p.x - HANDLE, p.y - HANDLE, HANDLE * 2, HANDLE * 2);
      ctx.fill(); ctx.stroke();
    });
    ctx.restore();
  }

  function priceTag(price, y, col) {
    ctx.save();
    const txt = fmt(price);
    ctx.font = "10px ui-monospace,monospace";
    const w = ctx.measureText(txt).width + 8;
    ctx.fillStyle = col;
    ctx.fillRect(W() - w - 2, y - 7, w, 14);
    ctx.fillStyle = "#fff";
    ctx.fillText(txt, W() - w + 2, y + 3);
    ctx.restore();
  }

  function extend(a, b) {
    // продлить луч от a через b до края канвы
    let dx = b.x - a.x, dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    dx /= len; dy /= len;
    const far = Math.hypot(W(), H()) * 2;
    return { x: b.x + dx * far, y: b.y + dy * far };
  }

  function fmt(v) {
    if (v == null) return "";
    const a = Math.abs(v);
    const d = a >= 1000 ? 1 : a >= 1 ? 2 : a >= 0.01 ? 4 : 6;
    return v.toFixed(d);
  }
  function hexA(hex, a) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
    if (!m) return hex;
    const n = parseInt(m[1], 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }

  // ── попадание ─────────────────────────────────────────────────────────────
  function distSeg(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1, dy = y2 - y1, l2 = dx * dx + dy * dy;
    if (!l2) return Math.hypot(px - x1, py - y1);
    let t = ((px - x1) * dx + (py - y1) * dy) / l2;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
  }

  function hitShape(s, mx, my) {
    if (s.type === "hline") {
      const y = priceY(s.pts[0].price);
      return y != null && Math.abs(my - y) <= HIT;
    }
    const pts = screenPts(s);
    if (s.type === "trend" || s.type === "rect") {
      const [a, b] = pts; if (!a || !b) return false;
      if (s.type === "rect") {
        const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y);
        const rw = Math.abs(b.x - a.x), rh = Math.abs(b.y - a.y);
        const near = (v, e) => Math.abs(v - e) <= HIT;
        const inX = mx >= x - HIT && mx <= x + rw + HIT;
        const inY = my >= y - HIT && my <= y + rh + HIT;
        return (inX && (near(my, y) || near(my, y + rh))) || (inY && (near(mx, x) || near(mx, x + rw)));
      }
      return distSeg(mx, my, a.x, a.y, b.x, b.y) <= HIT;
    }
    if (s.type === "ray") {
      const [a, b] = pts; if (!a || !b) return false;
      const e = extend(a, b);
      return distSeg(mx, my, a.x, a.y, e.x, e.y) <= HIT;
    }
    if (s.type === "fib") {
      const p0 = s.pts[0].price, p1 = s.pts[1].price;
      return FIB_LEVELS.some((lv) => {
        const y = priceY(p0 + (p1 - p0) * lv);
        return y != null && Math.abs(my - y) <= HIT;
      });
    }
    if (s.type === "brush") {
      for (let i = 1; i < pts.length; i++) {
        if (distSeg(mx, my, pts[i - 1].x, pts[i - 1].y, pts[i].x, pts[i].y) <= HIT) return true;
      }
    }
    return false;
  }

  function hitHandle(s, mx, my) {
    let hs = [];
    if (s.type === "hline") { const y = priceY(s.pts[0].price); hs = [{ x: W() / 2, y, idx: 0 }]; }
    else if (s.type === "brush") return -1;
    else hs = screenPts(s).map((p, i) => ({ ...p, idx: i }));
    for (const p of hs) {
      if (p.x != null && p.y != null && Math.abs(mx - p.x) <= HANDLE + 3 && Math.abs(my - p.y) <= HANDLE + 3)
        return p.idx;
    }
    return -1;
  }

  // ── ввод ──────────────────────────────────────────────────────────────────
  function pos(e) {
    const r = canvas.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return { x: t.clientX - r.left, y: t.clientY - r.top };
  }

  function bindCanvas() {
    canvas.addEventListener("mousedown", onDown);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    canvas.addEventListener("touchstart", onDown, { passive: false });
    window.addEventListener("touchmove", onMove, { passive: false });
    window.addEventListener("touchend", onUp);
  }

  function onDown(e) {
    if (!interactive()) return;
    const p = pos(e); e.preventDefault();

    if (tool === "cursor") {
      // выбор/редактирование существующей фигуры
      if (selected >= 0) {
        const hi = hitHandle(shapes[selected], p.x, p.y);
        if (hi >= 0) { drag = { mode: "handle", idx: hi, last: p }; return; }
      }
      let hit = -1;
      for (let i = shapes.length - 1; i >= 0; i--) {
        if (hitShape(shapes[i], p.x, p.y)) { hit = i; break; }
      }
      selected = hit;
      if (hit >= 0) drag = { mode: "move", last: p };
      redraw();
      return;
    }

    // создание новой фигуры
    if (tool === "brush") {
      draft = { type: "brush", color, width: lineWidth, pts: [makeAnchor(p.x, p.y)] };
    } else {
      const a = makeAnchor(p.x, p.y);
      const type = tool === "hline" ? "hline" : tool;
      draft = { type, color, width: lineWidth, pts: type === "hline" ? [a] : [a, makeAnchor(p.x, p.y)] };
      if (type === "hline") { commit(); return; }
      drag = { mode: "create", last: p };
    }
  }

  function onMove(e) {
    if (!interactive() || !drag) return;
    const p = pos(e); e.preventDefault();

    if (drag.mode === "create" && draft) {
      if (draft.type === "brush") draft.pts.push(makeAnchor(p.x, p.y));
      else draft.pts[1] = makeAnchor(p.x, p.y);
      redraw();
    } else if (drag.mode === "handle" && selected >= 0) {
      const s = shapes[selected];
      s.pts[drag.idx] = makeAnchor(p.x, p.y);
      redraw();
    } else if (drag.mode === "move" && selected >= 0) {
      const s = shapes[selected];
      const dPrice = (series.coordinateToPrice(p.y) || 0) - (series.coordinateToPrice(drag.last.y) || 0);
      const dLog = (ts().coordinateToLogical(p.x) || 0) - (ts().coordinateToLogical(drag.last.x) || 0);
      s.pts.forEach((a) => {
        a.price += dPrice;
        if (a.time != null) {
          const x = ts().timeToCoordinate(a.time);
          if (x != null) { const na = makeAnchor(x + (p.x - drag.last.x), priceY(a.price)); a.time = na.time; a.off = na.off; }
        } else {
          a.off = (a.off || 0) + dLog;
        }
      });
      drag.last = p;
      redraw();
    }
  }

  function onUp() {
    if (drag && drag.mode === "create" && draft) commit();
    else if (drag && (drag.mode === "move" || drag.mode === "handle")) save();
    drag = null;
  }

  function isDegenerate(s) {
    if (s.type === "hline") return false;
    if (s.type === "brush") return s.pts.length < 2;
    // двухточечные: клик без протяжки → обе точки совпали (нулевая фигура)
    const p = screenPts(s);
    if (p.length < 2 || p.some((q) => q.x == null || q.y == null)) return true;
    return Math.hypot(p[1].x - p[0].x, p[1].y - p[0].y) < 4;
  }

  function commit() {
    if (draft) {
      if (isDegenerate(draft)) { draft = null; redraw(); return; }
      shapes.push(draft);
      selected = shapes.length - 1;
      draft = null;
      save();
    }
    // инструмент НЕ сбрасываем — пользователь может рисовать ещё (как кисть/линия в TV).
    // Для выделения/перемещения он сам выберет «Курсор».
    redraw();
  }

  function onKey(e) {
    if (!editing) return;
    if ((e.key === "Delete" || e.key === "Backspace") && selected >= 0) {
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      shapes.splice(selected, 1); selected = -1; save(); redraw();
    } else if (e.key === "Escape") {
      draft = null; drag = null; setTool("cursor"); redraw();
    }
  }

  function interactive() { return editing; }

  // ── панель инструментов ───────────────────────────────────────────────────
  const TOOLS = [
    { id: "cursor", icon: "🖱", t: "Курсор / выбор (перетаскивать график)" },
    { id: "trend", icon: "╱", t: "Трендовая линия" },
    { id: "ray", icon: "→", t: "Луч (продлевается)" },
    { id: "hline", icon: "─", t: "Горизонтальный уровень" },
    { id: "fib", icon: "𝑭", t: "Уровни Фибоначчи" },
    { id: "rect", icon: "▭", t: "Прямоугольник / зона" },
    { id: "brush", icon: "✎", t: "Кисть (от руки)" },
  ];

  function buildPalette() {
    if (palette || !container || !container.parentElement) return;
    palette = document.createElement("div");
    palette.className = "draw-palette hidden";
    TOOLS.forEach((tl) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "draw-tool"; b.dataset.tool = tl.id;
      b.title = tl.t; b.textContent = tl.icon;
      b.addEventListener("click", () => setTool(tl.id));
      palette.appendChild(b);
    });
    // цвет
    const ci = document.createElement("input");
    ci.type = "color"; ci.value = color; ci.className = "draw-color"; ci.title = "Цвет линии";
    ci.addEventListener("input", () => {
      color = ci.value;
      if (selected >= 0) { shapes[selected].color = color; save(); redraw(); }
    });
    palette.appendChild(ci);
    // удалить выбранное
    const del = document.createElement("button");
    del.type = "button"; del.className = "draw-tool draw-del"; del.title = "Удалить выбранное (Del)";
    del.textContent = "🗑";
    del.addEventListener("click", () => {
      if (selected >= 0) { shapes.splice(selected, 1); selected = -1; save(); redraw(); }
    });
    palette.appendChild(del);
    // очистить всё
    const clr = document.createElement("button");
    clr.type = "button"; clr.className = "draw-tool draw-clear"; clr.title = "Очистить всё";
    clr.textContent = "🧹";
    clr.addEventListener("click", clearAll);
    palette.appendChild(clr);

    container.parentElement.appendChild(palette);

    hint = document.createElement("div");
    hint.className = "draw-hint hidden";
    container.parentElement.appendChild(hint);

    syncPalette();
  }

  function setTool(id) {
    tool = id;
    if (id !== "cursor") lastTool = id;
    // в режиме редактирования канва всегда ловит указатель (выбор/создание);
    // вне редактирования — прозрачна, график панорамируется
    canvas.style.pointerEvents = editing ? "auto" : "none";
    canvas.style.cursor = id === "cursor" ? "default" : "crosshair";
    syncPalette();
    if (editing) showHint();
  }

  function syncPalette() {
    if (!palette) return;
    palette.querySelectorAll(".draw-tool").forEach((b) => {
      if (b.dataset.tool) b.classList.toggle("active", b.dataset.tool === tool);
    });
  }

  function showHint() {
    if (!hint || !editing) return;
    const map = {
      cursor: "Курсор: клик по линии — выбрать, тянуть ручки — менять, Del — удалить.",
      trend: "Трендовая: зажми и протяни от точки до точки.",
      ray: "Луч: протяни — линия продлится до края.",
      hline: "Горизонталь: клик на нужном уровне цены.",
      fib: "Фибоначчи: протяни от минимума к максимуму свинга.",
      rect: "Прямоугольник: протяни рамку зоны.",
      brush: "Кисть: рисуй от руки, зажав кнопку.",
    };
    hint.textContent = map[tool] || "";
    hint.classList.remove("hidden");
    clearTimeout(showHint._t);
    showHint._t = setTimeout(() => hint && hint.classList.add("hidden"), 3500);
  }

  function toggle(on) {
    editing = on == null ? !editing : !!on;
    if (palette) palette.classList.toggle("hidden", !editing);
    if (!editing) {
      selected = -1; draft = null; drag = null;
      if (hint) hint.classList.add("hidden");
      setTool("cursor");
    } else {
      // при включении сразу даём рабочий инструмент рисования — иначе перетаскивание
      // в режиме «курсор» ничего не рисует и кажется, что рисовать нельзя
      setTool(lastTool || "trend");
    }
    redraw();
    return editing;
  }

  function clearAll() {
    shapes = []; selected = -1; draft = null; save(); redraw();
  }

  return { attach, setBars, setPair, redraw, resize, toggle, clearAll, isEditing: () => editing };
})();
window.ChartDraw = ChartDraw;
