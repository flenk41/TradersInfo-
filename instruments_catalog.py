"""Каталог инструментов: крипто, акции (РФ / США), валюта."""

from __future__ import annotations

from dataclasses import asdict, dataclass

CRYPTO_ICON_BASE = "https://assets.coincap.io/assets/icons"


@dataclass
class Instrument:
    id: str
    name: str
    market: str
    icon_url: str
    region: str = ""
    yf_symbol: str = ""
    tv_exchange: str = ""
    subtitle: str = ""


def _crypto_icon(symbol: str) -> str:
    base = symbol.split("/")[0].lower()
    return f"{CRYPTO_ICON_BASE}/{base}@2x.png"


def _stock_icon_us(ticker: str) -> str:
    return f"https://financialmodelingprep.com/image-stock/{ticker}.png"


CRYPTO_LIST: list[Instrument] = [
    Instrument("BTC/USDT", "Bitcoin", "crypto", _crypto_icon("BTC"), subtitle="BTC"),
    Instrument("ETH/USDT", "Ethereum", "crypto", _crypto_icon("ETH"), subtitle="ETH"),
    Instrument("SOL/USDT", "Solana", "crypto", _crypto_icon("SOL"), subtitle="SOL"),
    Instrument("BNB/USDT", "BNB", "crypto", _crypto_icon("BNB"), subtitle="BNB"),
    Instrument("XRP/USDT", "XRP", "crypto", _crypto_icon("XRP"), subtitle="XRP"),
    Instrument("DOGE/USDT", "Dogecoin", "crypto", _crypto_icon("DOGE"), subtitle="DOGE"),
    Instrument("ADA/USDT", "Cardano", "crypto", _crypto_icon("ADA"), subtitle="ADA"),
    Instrument("AVAX/USDT", "Avalanche", "crypto", _crypto_icon("AVAX"), subtitle="AVAX"),
    Instrument("LINK/USDT", "Chainlink", "crypto", _crypto_icon("LINK"), subtitle="LINK"),
    Instrument("DOT/USDT", "Polkadot", "crypto", _crypto_icon("DOT"), subtitle="DOT"),
    Instrument("MATIC/USDT", "Polygon", "crypto", _crypto_icon("matic"), subtitle="MATIC"),
    Instrument("LTC/USDT", "Litecoin", "crypto", _crypto_icon("LTC"), subtitle="LTC"),
    Instrument("ATOM/USDT", "Cosmos", "crypto", _crypto_icon("ATOM"), subtitle="ATOM"),
    Instrument("UNI/USDT", "Uniswap", "crypto", _crypto_icon("UNI"), subtitle="UNI"),
    Instrument("TON/USDT", "Toncoin", "crypto", _crypto_icon("ton"), subtitle="TON"),
]

STOCKS_US: list[Instrument] = [
    Instrument("AAPL", "Apple", "stock", _stock_icon_us("AAPL"), "us", "AAPL", "NASDAQ", "США"),
    Instrument("MSFT", "Microsoft", "stock", _stock_icon_us("MSFT"), "us", "MSFT", "NASDAQ", "США"),
    Instrument("NVDA", "NVIDIA", "stock", _stock_icon_us("NVDA"), "us", "NVDA", "NASDAQ", "США"),
    Instrument("TSLA", "Tesla", "stock", _stock_icon_us("TSLA"), "us", "TSLA", "NASDAQ", "США"),
    Instrument("AMZN", "Amazon", "stock", _stock_icon_us("AMZN"), "us", "AMZN", "NASDAQ", "США"),
    Instrument("GOOGL", "Alphabet", "stock", _stock_icon_us("GOOGL"), "us", "GOOGL", "NASDAQ", "США"),
    Instrument("META", "Meta", "stock", _stock_icon_us("META"), "us", "META", "NASDAQ", "США"),
    Instrument("AMD", "AMD", "stock", _stock_icon_us("AMD"), "us", "AMD", "NASDAQ", "США"),
    Instrument("NFLX", "Netflix", "stock", _stock_icon_us("NFLX"), "us", "NFLX", "NASDAQ", "США"),
    Instrument("INTC", "Intel", "stock", _stock_icon_us("INTC"), "us", "INTC", "NASDAQ", "США"),
]

STOCKS_RU: list[Instrument] = [
    Instrument("SBER.ME", "Сбербанк", "stock", "", "ru", "SBER.ME", "MOEX", "Россия"),
    Instrument("GAZP.ME", "Газпром", "stock", "", "ru", "GAZP.ME", "MOEX", "Россия"),
    Instrument("LKOH.ME", "Лукойл", "stock", "", "ru", "LKOH.ME", "MOEX", "Россия"),
    Instrument("GMKN.ME", "Норникель", "stock", "", "ru", "GMKN.ME", "MOEX", "Россия"),
    Instrument("ROSN.ME", "Роснефть", "stock", "", "ru", "ROSN.ME", "MOEX", "Россия"),
    Instrument("NVTK.ME", "Новатэк", "stock", "", "ru", "NVTK.ME", "MOEX", "Россия"),
    Instrument("MTSS.ME", "МТС", "stock", "", "ru", "MTSS.ME", "MOEX", "Россия"),
    Instrument("VTBR.ME", "ВТБ", "stock", "", "ru", "VTBR.ME", "MOEX", "Россия"),
    Instrument("TATN.ME", "Татнефть", "stock", "", "ru", "TATN.ME", "MOEX", "Россия"),
    Instrument("PLZL.ME", "Полюс", "stock", "", "ru", "PLZL.ME", "MOEX", "Россия"),
    Instrument("MGNT.ME", "Магнит", "stock", "", "ru", "MGNT.ME", "MOEX", "Россия"),
    Instrument("ALRS.ME", "АЛРОСА", "stock", "", "ru", "ALRS.ME", "MOEX", "Россия"),
    Instrument("CHMF.ME", "Северсталь", "stock", "", "ru", "CHMF.ME", "MOEX", "Россия"),
    Instrument("YNDX.ME", "Яндекс", "stock", "", "ru", "YNDX.ME", "MOEX", "Россия"),
    Instrument("MOEX.ME", "Мосбиржа", "stock", "", "ru", "MOEX.ME", "MOEX", "Россия"),
]

FOREX_LIST: list[Instrument] = [
    Instrument("EUR/USD", "Евро / Доллар", "forex", "", "", "", "", "FX"),
    Instrument("GBP/USD", "Фунт / Доллар", "forex", "", "", "", "", "FX"),
    Instrument("USD/JPY", "Доллар / Иена", "forex", "", "", "", "", "FX"),
    Instrument("USD/CHF", "Доллар / Франк", "forex", "", "", "", "", "FX"),
    Instrument("AUD/USD", "Австралийский / USD", "forex", "", "", "", "", "FX"),
    Instrument("EUR/GBP", "Евро / Фунт", "forex", "", "", "", "", "FX"),
    Instrument("USD/CNH", "Доллар / Юань", "forex", "", "", "USDCNH=X", "", "FX"),
]

_ALL = {i.id: i for i in CRYPTO_LIST + STOCKS_US + STOCKS_RU + FOREX_LIST}


def get_instrument(pair: str, market: str | None = None) -> Instrument | None:
    key = pair.strip().upper()
    if key in _ALL:
        return _ALL[key]
    if market == "stock" or key.endswith(".ME"):
        ru = _ALL.get(f"{key}.ME") if not key.endswith(".ME") else _ALL.get(key)
        if ru:
            return ru
    return None


def resolve_yf_symbol(pair: str, market: str | None = None) -> str:
    inst = get_instrument(pair, market)
    if inst and inst.yf_symbol:
        return inst.yf_symbol
    if inst and inst.market == "stock":
        return inst.id
    return pair.strip().upper().replace("/", "")


def list_instruments(market: str, region: str = "all") -> list[dict]:
    if market == "crypto":
        items = CRYPTO_LIST
    elif market == "stock":
        if region == "ru":
            items = STOCKS_RU
        elif region == "us":
            items = STOCKS_US
        else:
            items = STOCKS_RU + STOCKS_US
    elif market == "forex":
        items = FOREX_LIST
    else:
        items = []
    return [asdict(i) for i in items]


def catalog_for_frontend() -> dict:
    return {
        "crypto": [asdict(i) for i in CRYPTO_LIST],
        "stock": {
            "regions": [
                {"id": "ru", "label": "🇷🇺 Россия", "items": [asdict(i) for i in STOCKS_RU]},
                {"id": "us", "label": "🇺🇸 США", "items": [asdict(i) for i in STOCKS_US]},
            ],
        },
        "forex": [asdict(i) for i in FOREX_LIST],
    }
