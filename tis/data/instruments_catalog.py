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


def _stock_icon_ru(ticker: str) -> str:
    # Надёжного бесплатного CDN логотипов MOEX нет (Т-Инвестиции отдают 403),
    # поэтому для РФ-акций используем цветной монограмм-бейдж с тикером (фронтенд).
    return ""


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
    Instrument("TRX/USDT", "TRON", "crypto", _crypto_icon("TRX"), subtitle="TRX"),
    Instrument("NEAR/USDT", "NEAR Protocol", "crypto", _crypto_icon("near"), subtitle="NEAR"),
    Instrument("APT/USDT", "Aptos", "crypto", _crypto_icon("apt"), subtitle="APT"),
    Instrument("ARB/USDT", "Arbitrum", "crypto", _crypto_icon("arb"), subtitle="ARB"),
    Instrument("OP/USDT", "Optimism", "crypto", _crypto_icon("op"), subtitle="OP"),
    Instrument("SUI/USDT", "Sui", "crypto", _crypto_icon("sui"), subtitle="SUI"),
    Instrument("SHIB/USDT", "Shiba Inu", "crypto", _crypto_icon("shib"), subtitle="SHIB"),
    Instrument("PEPE/USDT", "Pepe", "crypto", _crypto_icon("pepe"), subtitle="PEPE"),
    Instrument("FIL/USDT", "Filecoin", "crypto", _crypto_icon("FIL"), subtitle="FIL"),
    Instrument("ICP/USDT", "Internet Computer", "crypto", _crypto_icon("icp"), subtitle="ICP"),
    Instrument("INJ/USDT", "Injective", "crypto", _crypto_icon("inj"), subtitle="INJ"),
    Instrument("SEI/USDT", "Sei", "crypto", _crypto_icon("sei"), subtitle="SEI"),
    Instrument("TIA/USDT", "Celestia", "crypto", _crypto_icon("tia"), subtitle="TIA"),
    Instrument("FET/USDT", "Fetch.ai", "crypto", _crypto_icon("fet"), subtitle="FET"),
    Instrument("AAVE/USDT", "Aave", "crypto", _crypto_icon("AAVE"), subtitle="AAVE"),
    Instrument("ETC/USDT", "Ethereum Classic", "crypto", _crypto_icon("ETC"), subtitle="ETC"),
    Instrument("XLM/USDT", "Stellar", "crypto", _crypto_icon("XLM"), subtitle="XLM"),
    Instrument("ALGO/USDT", "Algorand", "crypto", _crypto_icon("ALGO"), subtitle="ALGO"),
    Instrument("SAND/USDT", "The Sandbox", "crypto", _crypto_icon("sand"), subtitle="SAND"),
    Instrument("MANA/USDT", "Decentraland", "crypto", _crypto_icon("MANA"), subtitle="MANA"),
    Instrument("GALA/USDT", "Gala", "crypto", _crypto_icon("gala"), subtitle="GALA"),
    Instrument("RENDER/USDT", "Render", "crypto", _crypto_icon("render"), subtitle="RENDER"),
    Instrument("WIF/USDT", "dogwifhat", "crypto", _crypto_icon("wif"), subtitle="WIF"),
    Instrument("BONK/USDT", "Bonk", "crypto", _crypto_icon("bonk"), subtitle="BONK"),
    Instrument("ENA/USDT", "Ethena", "crypto", _crypto_icon("ena"), subtitle="ENA"),
    Instrument("JUP/USDT", "Jupiter", "crypto", _crypto_icon("jup"), subtitle="JUP"),
    Instrument("PYTH/USDT", "Pyth Network", "crypto", _crypto_icon("pyth"), subtitle="PYTH"),
    Instrument("STX/USDT", "Stacks", "crypto", _crypto_icon("stx"), subtitle="STX"),
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
    Instrument("GOOG", "Alphabet C", "stock", _stock_icon_us("GOOG"), "us", "GOOG", "NASDAQ", "США"),
    Instrument("AVGO", "Broadcom", "stock", _stock_icon_us("AVGO"), "us", "AVGO", "NASDAQ", "США"),
    Instrument("ADBE", "Adobe", "stock", _stock_icon_us("ADBE"), "us", "ADBE", "NASDAQ", "США"),
    Instrument("PYPL", "PayPal", "stock", _stock_icon_us("PYPL"), "us", "PYPL", "NASDAQ", "США"),
    Instrument("COIN", "Coinbase", "stock", _stock_icon_us("COIN"), "us", "COIN", "NASDAQ", "США"),
    Instrument("PLTR", "Palantir", "stock", _stock_icon_us("PLTR"), "us", "PLTR", "NASDAQ", "США"),
    Instrument("PEP", "PepsiCo", "stock", _stock_icon_us("PEP"), "us", "PEP", "NASDAQ", "США"),
    Instrument("MU", "Micron", "stock", _stock_icon_us("MU"), "us", "MU", "NASDAQ", "США"),
    Instrument("QCOM", "Qualcomm", "stock", _stock_icon_us("QCOM"), "us", "QCOM", "NASDAQ", "США"),
    Instrument("SMCI", "Super Micro", "stock", _stock_icon_us("SMCI"), "us", "SMCI", "NASDAQ", "США"),
    Instrument("TSM", "TSMC", "stock", _stock_icon_us("TSM"), "us", "TSM", "NYSE", "США"),
    Instrument("ORCL", "Oracle", "stock", _stock_icon_us("ORCL"), "us", "ORCL", "NYSE", "США"),
    Instrument("CRM", "Salesforce", "stock", _stock_icon_us("CRM"), "us", "CRM", "NYSE", "США"),
    Instrument("UBER", "Uber", "stock", _stock_icon_us("UBER"), "us", "UBER", "NYSE", "США"),
    Instrument("BABA", "Alibaba", "stock", _stock_icon_us("BABA"), "us", "BABA", "NYSE", "США"),
    Instrument("DIS", "Disney", "stock", _stock_icon_us("DIS"), "us", "DIS", "NYSE", "США"),
    Instrument("BA", "Boeing", "stock", _stock_icon_us("BA"), "us", "BA", "NYSE", "США"),
    Instrument("JPM", "JPMorgan", "stock", _stock_icon_us("JPM"), "us", "JPM", "NYSE", "США"),
    Instrument("V", "Visa", "stock", _stock_icon_us("V"), "us", "V", "NYSE", "США"),
    Instrument("MA", "Mastercard", "stock", _stock_icon_us("MA"), "us", "MA", "NYSE", "США"),
    Instrument("WMT", "Walmart", "stock", _stock_icon_us("WMT"), "us", "WMT", "NYSE", "США"),
    Instrument("KO", "Coca-Cola", "stock", _stock_icon_us("KO"), "us", "KO", "NYSE", "США"),
    Instrument("MCD", "McDonald's", "stock", _stock_icon_us("MCD"), "us", "MCD", "NYSE", "США"),
    Instrument("SHOP", "Shopify", "stock", _stock_icon_us("SHOP"), "us", "SHOP", "NYSE", "США"),
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
    Instrument("YDEX.ME", "Яндекс", "stock", "", "ru", "YDEX.ME", "MOEX", "Россия"),
    Instrument("MOEX.ME", "Мосбиржа", "stock", "", "ru", "MOEX.ME", "MOEX", "Россия"),
    Instrument("T.ME", "Т-Технологии", "stock", "", "ru", "T.ME", "MOEX", "Россия"),
    Instrument("OZON.ME", "Ozon", "stock", "", "ru", "OZON.ME", "MOEX", "Россия"),
    Instrument("VKCO.ME", "VK", "stock", "", "ru", "VKCO.ME", "MOEX", "Россия"),
    Instrument("POSI.ME", "Positive Technologies", "stock", "", "ru", "POSI.ME", "MOEX", "Россия"),
    Instrument("SNGS.ME", "Сургутнефтегаз", "stock", "", "ru", "SNGS.ME", "MOEX", "Россия"),
    Instrument("SNGSP.ME", "Сургутнефтегаз ап", "stock", "", "ru", "SNGSP.ME", "MOEX", "Россия"),
    Instrument("SBERP.ME", "Сбербанк ап", "stock", "", "ru", "SBERP.ME", "MOEX", "Россия"),
    Instrument("TATNP.ME", "Татнефть ап", "stock", "", "ru", "TATNP.ME", "MOEX", "Россия"),
    Instrument("TRNFP.ME", "Транснефть ап", "stock", "", "ru", "TRNFP.ME", "MOEX", "Россия"),
    Instrument("RUAL.ME", "РУСАЛ", "stock", "", "ru", "RUAL.ME", "MOEX", "Россия"),
    Instrument("PHOR.ME", "ФосАгро", "stock", "", "ru", "PHOR.ME", "MOEX", "Россия"),
    Instrument("MAGN.ME", "ММК", "stock", "", "ru", "MAGN.ME", "MOEX", "Россия"),
    Instrument("NLMK.ME", "НЛМК", "stock", "", "ru", "NLMK.ME", "MOEX", "Россия"),
    Instrument("AFLT.ME", "Аэрофлот", "stock", "", "ru", "AFLT.ME", "MOEX", "Россия"),
    Instrument("AFKS.ME", "АФК Система", "stock", "", "ru", "AFKS.ME", "MOEX", "Россия"),
    Instrument("HYDR.ME", "РусГидро", "stock", "", "ru", "HYDR.ME", "MOEX", "Россия"),
    Instrument("IRAO.ME", "Интер РАО", "stock", "", "ru", "IRAO.ME", "MOEX", "Россия"),
    Instrument("PIKK.ME", "ПИК", "stock", "", "ru", "PIKK.ME", "MOEX", "Россия"),
    Instrument("SMLT.ME", "Самолёт", "stock", "", "ru", "SMLT.ME", "MOEX", "Россия"),
    Instrument("BSPB.ME", "Банк СПб", "stock", "", "ru", "BSPB.ME", "MOEX", "Россия"),
    Instrument("SELG.ME", "Селигдар", "stock", "", "ru", "SELG.ME", "MOEX", "Россия"),
    Instrument("UPRO.ME", "Юнипро", "stock", "", "ru", "UPRO.ME", "MOEX", "Россия"),
    Instrument("RTKM.ME", "Ростелеком", "stock", "", "ru", "RTKM.ME", "MOEX", "Россия"),
    Instrument("FLOT.ME", "Совкомфлот", "stock", "", "ru", "FLOT.ME", "MOEX", "Россия"),
]

FOREX_LIST: list[Instrument] = [
    Instrument("EUR/USD", "Евро / Доллар", "forex", "", "", "", "", "FX"),
    Instrument("GBP/USD", "Фунт / Доллар", "forex", "", "", "", "", "FX"),
    Instrument("USD/JPY", "Доллар / Иена", "forex", "", "", "", "", "FX"),
    Instrument("USD/CHF", "Доллар / Франк", "forex", "", "", "", "", "FX"),
    Instrument("AUD/USD", "Австралийский / USD", "forex", "", "", "", "", "FX"),
    Instrument("EUR/GBP", "Евро / Фунт", "forex", "", "", "", "", "FX"),
    Instrument("USD/CNH", "Доллар / Юань", "forex", "", "", "USDCNH=X", "", "FX"),
    Instrument("NZD/USD", "Новозеландский / USD", "forex", "", "", "", "", "FX"),
    Instrument("USD/CAD", "Доллар / Канадский", "forex", "", "", "", "", "FX"),
    Instrument("EUR/JPY", "Евро / Иена", "forex", "", "", "", "", "FX"),
    Instrument("GBP/JPY", "Фунт / Иена", "forex", "", "", "", "", "FX"),
    Instrument("AUD/JPY", "Австралийский / Иена", "forex", "", "", "", "", "FX"),
    Instrument("EUR/CHF", "Евро / Франк", "forex", "", "", "", "", "FX"),
    Instrument("GBP/CHF", "Фунт / Франк", "forex", "", "", "", "", "FX"),
    Instrument("EUR/AUD", "Евро / Австралийский", "forex", "", "", "", "", "FX"),
    Instrument("NZD/JPY", "Новозеландский / Иена", "forex", "", "", "", "", "FX"),
    Instrument("CAD/JPY", "Канадский / Иена", "forex", "", "", "", "", "FX"),
    Instrument("USD/TRY", "Доллар / Лира", "forex", "", "", "", "", "FX"),
    Instrument("USD/MXN", "Доллар / Песо", "forex", "", "", "", "", "FX"),
    Instrument("USD/SGD", "Доллар / Сингапурский", "forex", "", "", "", "", "FX"),
    Instrument("USD/ZAR", "Доллар / Рэнд", "forex", "", "", "", "", "FX"),
]

# Логотипы для российских акций (CDN Т-Инвестиций).
for _ru in STOCKS_RU:
    if not _ru.icon_url:
        _ru.icon_url = _stock_icon_ru(_ru.id)

# Расширение списка акций США (популярные тикеры разных секторов).
STOCKS_US += [
    Instrument(t, n, "stock", _stock_icon_us(t), "us", t, ex, "США")
    for t, n, ex in [
        ("JNJ", "Johnson & Johnson", "NYSE"), ("UNH", "UnitedHealth", "NYSE"),
        ("XOM", "Exxon Mobil", "NYSE"), ("CVX", "Chevron", "NYSE"),
        ("LLY", "Eli Lilly", "NYSE"), ("PFE", "Pfizer", "NYSE"),
        ("MRK", "Merck", "NYSE"), ("ABBV", "AbbVie", "NYSE"),
        ("COST", "Costco", "NASDAQ"), ("HD", "Home Depot", "NYSE"),
        ("NKE", "Nike", "NYSE"), ("SBUX", "Starbucks", "NASDAQ"),
        ("CAT", "Caterpillar", "NYSE"), ("GS", "Goldman Sachs", "NYSE"),
        ("MS", "Morgan Stanley", "NYSE"), ("BAC", "Bank of America", "NYSE"),
        ("WFC", "Wells Fargo", "NYSE"), ("C", "Citigroup", "NYSE"),
        ("AXP", "American Express", "NYSE"), ("IBM", "IBM", "NYSE"),
        ("CSCO", "Cisco", "NASDAQ"), ("TXN", "Texas Instruments", "NASDAQ"),
        ("HON", "Honeywell", "NASDAQ"), ("GE", "GE Aerospace", "NYSE"),
        ("F", "Ford", "NYSE"), ("GM", "General Motors", "NYSE"),
        ("T", "AT&T", "NYSE"), ("VZ", "Verizon", "NYSE"),
        ("MRNA", "Moderna", "NASDAQ"), ("GILD", "Gilead", "NASDAQ"),
        ("AMGN", "Amgen", "NASDAQ"), ("ABNB", "Airbnb", "NASDAQ"),
        ("RBLX", "Roblox", "NYSE"), ("SOFI", "SoFi", "NASDAQ"),
        ("RIVN", "Rivian", "NASDAQ"), ("LCID", "Lucid", "NASDAQ"),
        ("SNAP", "Snap", "NYSE"), ("SPOT", "Spotify", "NYSE"),
        ("PINS", "Pinterest", "NYSE"), ("ZM", "Zoom", "NASDAQ"),
    ]
]

# Расширение списка валютных пар (мажоры, кроссы, экзотика).
FOREX_LIST += [
    Instrument(p, p, "forex", "", "", "", "", "FX")
    for p in [
        "USD/NOK", "USD/SEK", "USD/DKK", "USD/PLN", "USD/HUF", "USD/CZK",
        "USD/HKD", "USD/INR", "USD/THB", "USD/ILS", "EUR/CAD", "EUR/NZD",
        "EUR/SEK", "EUR/NOK", "EUR/PLN", "EUR/TRY", "EUR/CNH", "GBP/AUD",
        "GBP/CAD", "GBP/NZD", "AUD/CAD", "AUD/CHF", "AUD/NZD", "CAD/CHF",
        "CHF/JPY", "NZD/CAD", "NZD/CHF", "AUD/CNH", "GBP/SGD", "EUR/SGD",
    ]
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
