import html
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import feedparser
import requests

from collectors.base import BaseCollector, Item

logger = logging.getLogger(__name__)

_INLINE_TAG_RE = re.compile(r"</?(?:a|em|strong|i|b|span|abbr|cite|code|sup|sub|mark|small)\b[^>]*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_html(text: str) -> str:
    # Inline tags are removed without a space so "<em>word</em>." stays "word."
    text = _TAG_RE.sub(" ", _INLINE_TAG_RE.sub("", text))
    return _WS_RE.sub(" ", html.unescape(text)).strip()


def _entry_text(entry: Any) -> str:
    contents = entry.get("content") or []
    if contents and contents[0].get("value"):
        return str(contents[0]["value"])
    return str(entry.get("summary", ""))


def _entry_timestamp(entry: Any) -> str:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


class RSSCollector(BaseCollector):
    def __init__(
        self,
        sources: List[Dict[str, str]],
        rss_cfg: Dict[str, Any],
        max_items_per_source: int,
        max_chars_per_item: int,
    ) -> None:
        self.sources = sources
        self.timeout = float(rss_cfg.get("timeout_seconds", 10))
        self.retries = int(rss_cfg.get("retries", 2))
        self.headers = {"User-Agent": rss_cfg.get("user_agent", "DailyDigestBot/1.0")}
        self.max_items = max_items_per_source
        self.max_chars = max_chars_per_item

    def _download(self, url: str) -> Optional[bytes]:
        for attempt in range(self.retries + 1):
            try:
                resp = requests.get(url, headers=self.headers, timeout=self.timeout)
            except (requests.Timeout, requests.ConnectionError) as exc:
                logger.warning("RSS %s attempt %d failed: %s", url, attempt + 1, type(exc).__name__)
            else:
                if resp.status_code < 400:
                    return resp.content
                if resp.status_code < 500:
                    logger.warning("RSS %s returned HTTP %d, skipping", url, resp.status_code)
                    return None
                logger.warning("RSS %s attempt %d returned HTTP %d", url, attempt + 1, resp.status_code)
            if attempt < self.retries:
                time.sleep(2**attempt)
        return None

    def _collect_source(self, source: Dict[str, str]) -> List[Item]:
        content = self._download(source["url"])
        if content is None:
            return []
        feed = feedparser.parse(content)
        if feed.bozo and not feed.entries:
            logger.warning("RSS %s could not be parsed: %s", source["name"], feed.get("bozo_exception"))
            return []
        items: List[Item] = []
        for entry in feed.entries[: self.max_items]:
            title = clean_html(str(entry.get("title", ""))).strip()
            if not title:
                continue
            items.append(
                Item(
                    title=title,
                    source=source["name"],
                    raw_text=clean_html(_entry_text(entry))[: self.max_chars],
                    timestamp=_entry_timestamp(entry),
                    url=str(entry.get("link", "")),
                    category=source.get("category", ""),
                )
            )
        return items

    def collect(self) -> List[Item]:
        items: List[Item] = []
        for source in self.sources:
            try:
                fetched = self._collect_source(source)
            except Exception:
                logger.warning("RSS source %s failed unexpectedly", source.get("name"), exc_info=True)
                continue
            logger.info("RSS %s: %d items", source["name"], len(fetched))
            items.extend(fetched)
        return items
