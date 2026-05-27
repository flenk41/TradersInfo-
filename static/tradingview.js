/**
 * TradingView — iframe embed (надёжнее динамического script).
 */
const TradingViewWidget = (() => {
  let container = null;
  let currentSymbol = "BINANCE:ETHUSDT";
  let currentInterval = "60";

  // Индикаторы по умолчанию в расширенном графике. Пользователь может добавить
  // другие через кнопку «Индикаторы» в верхней панели виджета.
  const STUDIES = [
    "Volume@tv-basicstudies",
    "RSI@tv-basicstudies",
    "MACD@tv-basicstudies",
    "MAExp@tv-basicstudies",
    "BB@tv-basicstudies",
  ];

  function embedUrl(symbol, interval) {
    const p = new URLSearchParams({
      symbol: symbol || "BINANCE:ETHUSDT",
      interval: String(interval || "60"),
      theme: "dark",
      style: "1",
      locale: "ru",
      timezone: "Europe/Moscow",
      hidesidetoolbar: "0",
      hidetoptoolbar: "0",
      withdateranges: "1",
      details: "1",
      studies_overrides: "{}",
      saveimage: "0",
    });
    STUDIES.forEach((s) => p.append("studies", s));
    return `https://s.tradingview.com/widgetembed/?frameElementId=tv_chart&${p.toString()}`;
  }

  function mount(symbol, interval) {
    if (!container) return;
    currentSymbol = symbol || currentSymbol;
    currentInterval = interval || currentInterval;
    const url = embedUrl(currentSymbol, currentInterval);
    container.innerHTML = `<iframe
      title="TradingView"
      src="${url}"
      allow="fullscreen"
      loading="lazy"
    ></iframe>`;
  }

  function init(el) {
    container = el;
    mount(currentSymbol, currentInterval);
  }

  function setSymbol(symbol, interval) {
    if (!symbol) return;
    mount(symbol, interval || currentInterval);
  }

  function setInterval(interval) {
    if (!interval) return;
    mount(currentSymbol, interval);
  }

  function getSymbol() {
    return currentSymbol;
  }

  return { init, setSymbol, setInterval, getSymbol, mount };
})();
