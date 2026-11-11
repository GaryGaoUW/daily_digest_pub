# Daily Intelligence Digest

A Python service that emails me a personalized morning briefing every day at 7:30 AM (Toronto time): world and tech news, US/Canadian market moves, upcoming earnings, and a short English reading lesson. It runs entirely on GitHub Actions and uses the DeepSeek LLM API for summarization.

## What it does

- **News**: pulls RSS feeds (BBC, NPR, TechCrunch, Hacker News, Ars Technica, CNBC) and has the LLM pick and summarize the top stories, plus a 3-bullet "Today" overview.
- **Markets**: previous-close quotes for a fixed watchlist, plus daily extras chosen from tickers mentioned in today's news or picked at random from a pool. Also shows the earnings calendar for the next 7 days.
- **English reading**: selects a 120-200 word passage from *The Conversation*, then gives a plain-English paraphrase, a grammar breakdown of the hardest sentences, and key phrases.
- **Delivery**: a mobile-friendly HTML email with a plain-text fallback, sent through Gmail SMTP.

## Tech stack

| Area | Tools |
|---|---|
| Language | Python 3.11+ with full type hints |
| Data collection | `requests`, `feedparser`, Finnhub API, `yfinance` |
| LLM | DeepSeek API via the `openai` SDK, JSON output mode, `tenacity` for retries |
| Rendering | `Jinja2` templates with inline CSS |
| Delivery | `smtplib` (Gmail SMTP, app password) |
| Scheduling | GitHub Actions cron, with secrets for API keys |

## How it works

```
collectors/  ->  processor/  ->  renderer/  ->  sender/
 (fetch)         (LLM)          (HTML)         (email)
                    main.py orchestrates
```

- **Layered design**: each folder has one job and does not import the others. `main.py` only wires them together, so a new data source is just a new `BaseCollector` subclass plus a config entry.
- **Config-driven**: feeds, tickers, prompts and model settings all live in `config.yaml`. Nothing is hardcoded.
- **Structured LLM output**: every prompt asks for JSON, and the response is checked against a required-keys schema. If the JSON is invalid the call is retried once, and if it still fails that section is skipped.
- **Graceful degradation**: a failing feed, ticker or LLM call logs a warning and is skipped. The email still goes out, with a "Not available today" placeholder for that section.
- **Debug flags**: `--dry-run` renders `output.html` without sending, and `--mock-llm` uses built-in fake LLM responses so the whole pipeline can be tested for free without API keys.

## Challenges and how I solved them

1. **LLM hallucination**: models can invent links, numbers or causes.
   - News items are sent with numeric IDs. The model returns only the ID, and the code attaches the real URL.
   - Stock prices are rendered straight from the market API; the LLM only writes commentary.
   - Prompts forbid stating a cause unless a headline says so.
2. **Inconsistent output format**: free-form Markdown looked different every day. I switched to JSON mode with schema validation and a fixed template, so the layout is identical every day.
3. **Unreliable market data**: `yfinance` scrapes Yahoo and gets rate-limited on shared CI IPs. I use Finnhub (official API) as the primary source, fall back to `yfinance` per ticker, and route TSX tickers straight to `yfinance` since Finnhub's free tier doesn't cover them.
4. **Daylight saving time**: GitHub cron only runs in UTC, so 7:30 AM Toronto moves between 11:30 and 12:30 UTC. The workflow schedules both, and a guard step checks the current Toronto UTC offset and lets only the matching run continue.
5. **Email client quirks**:
   - Gmail strips `<style>` tags, so all CSS is written inline.
   - Mail apps auto-linked TSX tickers like `XEQT.TO` as `.to` domains, so the `.TO` suffix is removed when rendering.
   - I checked the layout at phone width with headless Chrome.
6. **Model deprecation**: DeepSeek retired its legacy model names partway through the project. I moved to the current model, with thinking mode disabled for speed and cost.

## What I learned

- **Designing around an LLM**: treat it as an unreliable component, constrain its output with schemas, and keep facts like prices and URLs outside its control.
- **Resilience patterns**: retries with exponential backoff, primary/fallback data providers, and per-section error isolation.
- **Prompt engineering for structured data**: few-shot JSON examples, explicit constraints and validation loops.
- **Practical CI/CD**: secrets management, cron scheduling and its UTC/DST pitfalls, and artifact uploads for debugging.
- **HTML email development**: inline styles, table layouts and testing at mobile widths.

## Run locally

```bash
pip install -r requirements.txt

# No keys needed: mock LLM, writes output.html, sends nothing
python main.py --dry-run --mock-llm

# Real run
export DEEPSEEK_API_KEY=... FINNHUB_API_KEY=...
export GMAIL_USER=... GMAIL_APP_PASSWORD=... RECIPIENT_EMAIL=...
python main.py
```

To deploy, add the five variables above as GitHub repository secrets. The workflow in `.github/workflows/daily_run.yml` then runs every morning automatically.
