"""Конфигурация торгового анализатора."""

BINANCE_SPOT_URL = "https://api.binance.com"
BINANCE_FUTURES_URL = "https://fapi.binance.com"

DEFAULT_QUOTE = "USDT"
DEFAULT_TIMEFRAMES = ["1h", "4h", "1d"]
SCALP_TIMEFRAMES = ["5m", "15m"]

POPULAR_CRYPTO = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "DOGE/USDT",
]

POPULAR_STOCKS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "AMZN",
    "GOOGL",
    "META",
    "AMD",
]

POPULAR_FOREX = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "AUD/USD",
    "EUR/GBP",
]

POPULAR_PAIRS = POPULAR_CRYPTO

MARKET_LABELS = {
    "crypto": "Крипто",
    "stock": "Акции",
    "forex": "Валюта",
}
