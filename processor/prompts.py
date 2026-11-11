from typing import Dict, List, Optional

from collectors.base import Item

# Output contract between the LLM and the renderer
REQUIRED_KEYS: Dict[str, Dict[str, type]] = {
    "news": {"items": list},
    "market": {"overview": str, "highlights": list},
    "reading": {"title": str, "passage": str, "sentences": list, "skeleton": list, "collocations": list},
}


def format_news(items: List[Item]) -> str:
    return "\n\n".join(
        f"[{i}] ({item.get('category', '')} | {item['source']}) {item['title']}\n{item['raw_text']}"
        for i, item in enumerate(items)
    )


def format_market(market_items: List[Item], finance_news: List[Item]) -> str:
    quotes = [i["raw_text"] for i in market_items if i.get("category") in ("us", "ca")]
    earnings = [i["raw_text"] for i in market_items if i.get("category") == "earnings"]
    headlines = [f"- {i['title']}" for i in finance_news]
    return (
        "## Quotes (previous trading day)\n" + "\n".join(quotes or ["(none)"])
        + "\n\n## Upcoming earnings\n" + "\n".join(earnings or ["(none)"])
        + "\n\n## Finance headlines\n" + "\n".join(headlines or ["(none)"])
    )


def format_reading(item: Optional[Item]) -> str:
    if item is None:
        return ""
    return f"Title: {item['title']}\nSource: {item['source']}\n\n{item['raw_text']}"


def build_messages(prompt_cfg: Dict[str, str], materials: str) -> List[Dict[str, str]]:
    # str.replace instead of format(): prompt templates contain literal JSON braces
    return [
        {"role": "system", "content": prompt_cfg["system"]},
        {"role": "user", "content": prompt_cfg["user"].replace("{materials}", materials)},
    ]
