import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar
from zoneinfo import ZoneInfo

import yaml

from collectors.base import Item
from collectors.market import MarketCollector
from collectors.rss import RSSCollector
from processor.deepseek import DeepSeekClient
from processor.prompts import build_messages, format_market, format_news, format_reading
from renderer.engine import Renderer
from sender.gmail import load_credentials, send_email

BASE_DIR = Path(__file__).resolve().parent
T = TypeVar("T")

logger = logging.getLogger("digest")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily Intelligence Digest")
    parser.add_argument("--dry-run", action="store_true", help="render output.html and print, do not send email")
    parser.add_argument("--mock-llm", action="store_true", help="use built-in mock LLM output, no API calls")
    parser.add_argument("--config", type=Path, default=BASE_DIR / "config.yaml")
    return parser.parse_args()


def load_config(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def safe(section: str, fn: Callable[[], T]) -> Optional[T]:
    try:
        return fn()
    except Exception as exc:
        logger.warning("Section '%s' skipped: %s: %s", section, type(exc).__name__, exc)
        return None


def safe_url(url: str) -> str:
    return url if url.startswith(("http://", "https://")) else ""


def pick_reading(items: List[Item], min_chars: int) -> Optional[Item]:
    long_enough = [i for i in items if len(i["raw_text"]) >= min_chars]
    if long_enough:
        return long_enough[0]
    return max(items, key=lambda i: len(i["raw_text"]), default=None)


def build_news_groups(digest: Optional[Dict[str, Any]], items: List[Item], categories: Dict[str, str]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, str]]] = {key: [] for key in categories}
    for entry in (digest or {}).get("items", []):
        if not isinstance(entry, dict) or entry.get("category") not in groups:
            continue
        ref = entry.get("ref")
        src = items[ref] if isinstance(ref, int) and 0 <= ref < len(items) else None
        groups[entry["category"]].append({
            "headline": str(entry.get("headline", "")),
            "summary": str(entry.get("summary", "")),
            "source": src["source"] if src else "",
            "url": safe_url(src.get("url", "")) if src else "",
        })
    return [{"key": key, "label": label, "items": groups[key]} for key, label in categories.items()]


def build_market(market_items: List[Item], comment: Optional[Dict[str, Any]], market_cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    def quotes(market: str) -> List[Dict[str, Any]]:
        return [i.get("data", {}) for i in market_items if i.get("category") == market]

    def as_of(rows: List[Dict[str, Any]]) -> str:
        return max((r["as_of"] for r in rows if not r.get("error")), default="")

    us, ca = quotes("us"), quotes("ca")
    if not any(not r.get("error") for r in us + ca):
        return None
    by_symbol = {r["symbol"]: r for r in us + ca if not r.get("error")}
    return {
        "overview": (comment or {}).get("overview", ""),
        "highlights": [h for h in (comment or {}).get("highlights", []) if isinstance(h, dict)],
        "headline": [by_symbol[s] for s in market_cfg.get("headline_symbols", []) if s in by_symbol],
        "us": us, "ca": ca, "us_as_of": as_of(us), "ca_as_of": as_of(ca),
        "earnings": [i.get("data", {}) for i in market_items if i.get("category") == "earnings"],
        "lookahead": int(market_cfg.get("earnings_lookahead_days", 7)),
    }


def run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    now = datetime.now(ZoneInfo(cfg["timezone"]))
    rss_cfg = cfg.get("rss", {})

    news_limits, reading_limits = cfg["news_limits"], cfg["reading_limits"]
    news_items = safe("news-collect", lambda: RSSCollector(
        cfg["news_sources"], rss_cfg, news_limits["max_items_per_source"], news_limits["max_chars_per_item"]).collect()) or []
    reading_items = safe("reading-collect", lambda: RSSCollector(
        cfg["reading_sources"], rss_cfg, reading_limits["max_items_per_source"], reading_limits["max_chars_per_item"]).collect()) or []

    llm = safe("llm-init", lambda: DeepSeekClient(cfg["llm"], os.environ.get("DEEPSEEK_API_KEY"), mock=args.mock_llm))

    def ask(task: str, materials: str) -> Optional[Dict[str, Any]]:
        if llm is None or (not materials and not args.mock_llm):
            return None
        return safe(f"llm-{task}", lambda: llm.complete_json(task, build_messages(cfg["prompts"][task], materials)))

    news_digest = ask("news", format_news(news_items))

    # Market runs after the news LLM so news-mentioned tickers can join today's watchlist
    news_symbols = [s for s in (news_digest or {}).get("tickers", []) if isinstance(s, str)]
    market_items = safe("market-collect", lambda: MarketCollector(
        cfg["market"], os.environ.get("FINNHUB_API_KEY"), news_symbols).collect()) or []

    has_quotes = any(i.get("category") in ("us", "ca") and not i.get("data", {}).get("error") for i in market_items)
    finance_news = [i for i in news_items if i.get("category") == "finance"]
    market_comment = ask("market", format_market(market_items, finance_news) if has_quotes else "")

    reading_item = pick_reading(reading_items, int(reading_limits.get("min_chars", 0)))
    reading = ask("reading", format_reading(reading_item))
    if reading is not None and reading_item is not None:
        reading = {**reading, "title": reading.get("title") or reading_item["title"],
                   "source": reading_item["source"], "url": safe_url(reading_item.get("url", ""))}

    news_groups = build_news_groups(news_digest, news_items, cfg["news_categories"])
    market = build_market(market_items, market_comment, cfg["market"])
    highlights = [h for h in (news_digest or {}).get("top", []) if isinstance(h, str) and h.strip()][:3]
    missing = [name for name, ok in (("News", any(g["items"] for g in news_groups)),
                                     ("Markets", market is not None), ("Reading", reading is not None)) if not ok]
    if market is not None and market_comment is None:
        missing.append("Market commentary")

    title = cfg["email"]["subject_prefix"]
    context = {
        "title": title,
        "date_str": f"{now:%a, %b %d, %Y} · {cfg['timezone']}",
        "highlights": highlights,
        "news_groups": news_groups,
        "market": market,
        "reading": reading,
        "missing": missing,
    }
    html, text = Renderer().render(context)
    output = BASE_DIR / cfg.get("output_path", "output.html")
    output.write_text(html, encoding="utf-8")
    logger.info("Rendered %s (missing: %s)", output, ", ".join(missing) or "none")

    if args.dry_run:
        print(text)
        logger.info("Dry run: email not sent")
        return 0

    creds = load_credentials()
    send_email(f"{title} · {now:%Y-%m-%d}", html, text, creds, cfg["email"])
    logger.info("Email sent to %d recipient(s)", len(creds.recipients))
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # yfinance logs its own errors loudly; our collector already reports failures
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    try:
        return run(parse_args())
    except Exception:
        logger.exception("Digest run failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
