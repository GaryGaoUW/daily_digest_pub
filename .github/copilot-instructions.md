# Project rules: digest_engine

Python 3.11+ daily email digest (news, US/CA market, English reading) using DeepSeek + Gmail.

## Architecture (keep layers decoupled)
- `collectors/` → fetch data only. Every collector subclasses `BaseCollector` and returns `List[Item]` (`title`, `source`, `raw_text`, `timestamp`; optional `url`, `category`, `data`).
- `processor/` → LLM only. DeepSeek is called in JSON mode; every task has a required-keys schema in `processor/prompts.py`.
- `renderer/` → Jinja2 templates only (`template.html` with inline styles, `template.txt` plain-text fallback). Never put LLM output into HTML without autoescape.
- `sender/` → SMTP delivery only.
- `main.py` → orchestration only; no fetching/parsing/formatting logic beyond glue.
- Layers never import each other except `main.py` importing all, and `processor` importing the `Item` type.

## Rules
- Graceful degradation: a failing source/ticker/LLM task logs a WARNING and is skipped. Never let an exception escape a collector or a section in `main.py`. Missing sections render as "Not available today".
- No hardcoded URLs, tickers, prompts or model params in code — add them to `config.yaml`.
- Secrets only from environment variables: `DEEPSEEK_API_KEY`, `FINNHUB_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `RECIPIENT_EMAIL`. Never log them.
- Market numbers are rendered from collector data, never from LLM output.
- Full type hints on all functions. Comments in English, one short line, only when the code cannot explain itself.
- Adding a data source = new `BaseCollector` subclass + config entry + wiring in `main.py`.

## Verify changes
`python main.py --dry-run --mock-llm` must produce `output.html` without network keys.
