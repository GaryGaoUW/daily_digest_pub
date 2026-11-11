import logging
import random
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Protocol, Tuple

import requests
import yfinance as yf

from collectors.base import BaseCollector, Item

logger = logging.getLogger(__name__)

_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}([.-][A-Z]{1,2})?$")


def pick_extras(fixed: List[str], news: List[str], pool: List[str], count: int, seed: str) -> List[Tuple[str, str]]:
    """News-mentioned symbols first, then a date-seeded random fill; returns (symbol, tag)."""
    picked: List[Tuple[str, str]] = []
    seen = set(fixed)
    for symbol in news:
        if len(picked) < count and symbol not in seen:
            picked.append((symbol, "news"))
            seen.add(symbol)
    candidates = [s for s in pool if s not in seen]
    random.Random(seed).shuffle(candidates)
    picked += [(s, "random") for s in candidates[: count - len(picked)]]
    return picked


@dataclass
class Quote:
    symbol: str
    price: float
    prev_close: float
    change: float
    change_pct: float
    as_of: str
    provider: str


@dataclass
class Earnings:
    symbol: str
    date: str
    hour: str
    eps_estimate: Optional[float]


class QuoteProvider(Protocol):
    name: str

    def quote(self, symbol: str) -> Quote: ...


class FinnhubProvider:
    name = "Finnhub"

    def __init__(self, api_key: str, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Token goes in a header so it never appears in URLs or exception messages
        self.headers = {"X-Finnhub-Token": api_key}

    def _get(self, path: str, params: Dict[str, str]) -> Any:
        resp = requests.get(f"{self.base_url}{path}", params=params, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def quote(self, symbol: str) -> Quote:
        data = self._get("/quote", {"symbol": symbol})
        price, prev = float(data.get("c") or 0), float(data.get("pc") or 0)
        if price <= 0 or prev <= 0:
            raise ValueError(f"empty quote for {symbol}")
        as_of = datetime.fromtimestamp(int(data.get("t") or 0), tz=timezone.utc).date().isoformat()
        change = price - prev
        return Quote(symbol, price, prev, change, change / prev * 100, as_of, self.name)

    def earnings(self, symbols: List[str], start: date, end: date) -> List[Earnings]:
        data = self._get("/calendar/earnings", {"from": start.isoformat(), "to": end.isoformat()})
        wanted = set(symbols)
        result: List[Earnings] = []
        for row in data.get("earningsCalendar") or []:
            if row.get("symbol") in wanted:
                eps = row.get("epsEstimate")
                result.append(
                    Earnings(row["symbol"], str(row.get("date", "")), str(row.get("hour") or ""), float(eps) if eps is not None else None)
                )
        return result


class YFinanceProvider:
    name = "yfinance"

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    def quote(self, symbol: str) -> Quote:
        hist = yf.Ticker(symbol).history(period="5d", auto_adjust=False, timeout=self.timeout)
        closes = hist["Close"].dropna() if "Close" in hist else []
        if len(closes) < 2:
            raise ValueError(f"not enough history for {symbol}")
        price, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
        change = price - prev
        return Quote(symbol, price, prev, change, change / prev * 100, closes.index[-1].date().isoformat(), self.name)

    def earnings(self, symbol: str, start: date, end: date) -> List[Earnings]:
        calendar = yf.Ticker(symbol).calendar
        if not isinstance(calendar, dict):
            return []
        eps = calendar.get("Earnings Average")
        result: List[Earnings] = []
        for day in calendar.get("Earnings Date") or []:
            day = day.date() if isinstance(day, datetime) else day
            if isinstance(day, date) and start <= day <= end:
                result.append(Earnings(symbol, day.isoformat(), "", float(eps) if eps is not None else None))
        return result


class MarketCollector(BaseCollector):
    def __init__(self, market_cfg: Dict[str, Any], finnhub_key: Optional[str], news_symbols: Optional[List[str]] = None) -> None:
        timeout = float(market_cfg.get("timeout_seconds", 10))
        stocks = market_cfg.get("stocks", {})
        extras = market_cfg.get("extras", {})
        news = [s.strip().upper() for s in news_symbols or [] if isinstance(s, str)]
        news = [s for s in news if _SYMBOL_RE.match(s)]
        seed = datetime.now(timezone.utc).date().isoformat()
        self.tags: Dict[str, str] = {}
        self.us: List[str] = list(stocks.get("us", []))
        self.ca: List[str] = list(stocks.get("ca", []))
        for market, fixed, is_market in (("us", self.us, lambda s: not s.endswith(".TO")),
                                         ("ca", self.ca, lambda s: s.endswith(".TO"))):
            cfg = extras.get(market, {})
            for symbol, tag in pick_extras(fixed, [s for s in news if is_market(s)], list(cfg.get("pool", [])),
                                           int(cfg.get("count", 0)), f"{seed}-{market}"):
                fixed.append(symbol)
                self.tags[symbol] = tag
        self.lookahead = int(market_cfg.get("earnings_lookahead_days", 7))
        self.yfinance = YFinanceProvider(timeout)
        self.finnhub: Optional[FinnhubProvider] = None
        if finnhub_key:
            self.finnhub = FinnhubProvider(finnhub_key, market_cfg["finnhub_base_url"], timeout)
        elif self.us:
            logger.warning("FINNHUB_API_KEY not set, US quotes will use yfinance only")

    def _quote(self, symbol: str, providers: List[QuoteProvider]) -> Optional[Quote]:
        for provider in providers:
            try:
                return provider.quote(symbol)
            except Exception as exc:
                logger.warning("%s quote failed for %s: %s", provider.name, symbol, type(exc).__name__)
        return None

    def _quote_items(self, symbols: List[str], providers: List[QuoteProvider], market: str) -> List[Item]:
        items: List[Item] = []
        now = datetime.now(timezone.utc).isoformat()
        for symbol in symbols:
            quote = self._quote(symbol, providers)
            tag = self.tags.get(symbol, "")
            if quote is None:
                # Dynamic picks may be bad LLM guesses; drop them instead of showing a gap
                if tag:
                    continue
                items.append(Item(title=symbol, source="none", raw_text=f"{symbol}: data unavailable",
                                  timestamp=now, category=market, data={"symbol": symbol, "error": True}))
                continue
            text = (f"{symbol}: close {quote.price:.2f}, change {quote.change:+.2f} "
                    f"({quote.change_pct:+.2f}%), as of {quote.as_of}")
            items.append(Item(title=symbol, source=quote.provider, raw_text=text,
                              timestamp=quote.as_of, category=market, data={**asdict(quote), "tag": tag}))
        return items

    def _earnings(self, start: date, end: date) -> List[Earnings]:
        found: List[Earnings] = []
        yf_symbols = list(self.ca)
        if self.finnhub and self.us:
            try:
                found.extend(self.finnhub.earnings(self.us, start, end))
            except Exception as exc:
                logger.warning("Finnhub earnings calendar failed: %s, falling back to yfinance", type(exc).__name__)
                yf_symbols = self.us + yf_symbols
        else:
            yf_symbols = self.us + yf_symbols
        for symbol in yf_symbols:
            try:
                found.extend(self.yfinance.earnings(symbol, start, end))
            except Exception:
                # ETFs have no earnings calendar; not worth a warning
                logger.debug("No earnings calendar for %s", symbol)
        return sorted(found, key=lambda e: (e.date, e.symbol))

    def collect(self) -> List[Item]:
        us_providers: List[QuoteProvider] = [p for p in (self.finnhub, self.yfinance) if p is not None]
        items = self._quote_items(self.us, us_providers, "us")
        items += self._quote_items(self.ca, [self.yfinance], "ca")

        today = datetime.now(timezone.utc).date()
        try:
            earnings = self._earnings(today, today + timedelta(days=self.lookahead))
        except Exception:
            logger.warning("Earnings calendar failed unexpectedly", exc_info=True)
            earnings = []
        for e in earnings:
            text = f"{e.symbol} reports earnings on {e.date} {e.hour}".strip()
            if e.eps_estimate is not None:
                text += f", EPS estimate {e.eps_estimate:.2f}"
            items.append(Item(title=e.symbol, source="earnings", raw_text=text,
                              timestamp=e.date, category="earnings", data=asdict(e)))
        ok = sum(1 for i in items if i.get("category") in ("us", "ca") and not i.get("data", {}).get("error"))
        logger.info("Market: %d/%d quotes, %d earnings events", ok, len(self.us) + len(self.ca), len(earnings))
        return items
