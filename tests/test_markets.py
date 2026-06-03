"""Тесты роутинга рынков и нормализации тикеров (чистая логика, без сети)."""

from __future__ import annotations

from tis.core.markets import detect_market, normalize_pair, to_tradingview_symbol
from tis.data.market_data import _crypto_to_yf, _is_moex


class TestDetectMarket:
    def test_explicit_market_wins(self):
        assert detect_market("ЧТОУГОДНО", "forex") == "forex"
        assert detect_market("BTCUSDT", "stock") == "stock"

    def test_crypto_pair(self):
        assert detect_market("BTC/USDT") == "crypto"
        assert detect_market("ETHUSDT") == "crypto"

    def test_forex_pair(self):
        assert detect_market("EUR/USD") == "forex"
        assert detect_market("EURUSD") == "forex"
        assert detect_market("USDJPY") == "forex"

    def test_moex_suffix_is_stock(self):
        assert detect_market("SBER.ME") == "stock"
        assert detect_market("gazp.me") == "stock"

    def test_short_alpha_is_stock(self):
        assert detect_market("AAPL") == "stock"
        assert detect_market("NVDA") == "stock"


class TestIsMoex:
    def test_me_suffix_only_for_stock(self):
        assert _is_moex("SBER.ME", "stock") is True
        assert _is_moex("sber.me", "stock") is True

    def test_not_moex_for_other_markets(self):
        assert _is_moex("SBER.ME", "crypto") is False
        assert _is_moex("AAPL", "stock") is False


class TestCryptoToYf:
    def test_strips_usdt_quote(self):
        assert _crypto_to_yf("BTCUSDT") == "BTC-USD"
        assert _crypto_to_yf("ETHUSDT") == "ETH-USD"

    def test_other_stablecoin_quotes(self):
        assert _crypto_to_yf("SOLUSDC") == "SOL-USD"
        assert _crypto_to_yf("BNBFDUSD") == "BNB-USD"

    def test_no_known_quote_appends_usd(self):
        assert _crypto_to_yf("DOGE") == "DOGE-USD"


class TestNormalizePair:
    def test_crypto_display_has_slash(self):
        sym, display = normalize_pair("BTC/USDT", "crypto")
        assert sym == "BTCUSDT"
        assert "/" in display

    def test_forex_builds_yahoo_symbol(self):
        sym, display = normalize_pair("EUR/USD", "forex")
        assert sym == "EURUSD=X"
        assert display == "EUR/USD"

    def test_stock_passthrough(self):
        sym, display = normalize_pair("AAPL", "stock")
        assert "AAPL" in sym.upper()


class TestTradingViewSymbol:
    def test_returns_nonempty_string(self):
        assert isinstance(to_tradingview_symbol("BTCUSDT", "crypto"), str)
        assert to_tradingview_symbol("AAPL", "stock")
