# Daily Intelligence Digest

A Python app that emails me a short briefing every morning at 7:30 (Toronto time): top news, US and Canadian stocks, upcoming earnings, and a short English reading lesson. It runs on GitHub Actions and uses the DeepSeek API to write the summaries.

## What's in the email

- **News**: top stories from BBC, NPR, TechCrunch, Hacker News, Ars Technica and CNBC, plus a 3-line "Today" summary.
- **Markets**: yesterday's close for my watchlist, a few extra stocks picked from today's news, and earnings coming up this week.
- **English reading**: a short passage from *The Conversation*, with each sentence rewritten in simpler English, the grammar of the hardest sentences broken down, and key phrases explained.

## Tech stack

Python, `requests` + `feedparser` (RSS), Finnhub API + `yfinance` (stock prices), DeepSeek API through the `openai` SDK, `Jinja2` (HTML email), `smtplib` (Gmail), and GitHub Actions + cron-job.org (scheduling).

## How it works

```
collectors/  ->  processor/  ->  renderer/  ->  sender/
 (fetch)         (AI)            (HTML)         (email)
```

- Each folder does one job, and `main.py` connects them.
- Feeds, tickers and prompts are kept in `config.yaml`, not in the code.
- If one part fails (a feed, a stock, an AI call), it is skipped and the rest of the email still goes out.
- `--dry-run` saves the email as a file instead of sending it. `--mock-llm` uses fake AI answers, so you can test without API keys.

## Challenges

1. **The AI can make things up.** It only gets to pick stories by ID number, so the real links and stock prices come straight from the source, not from the AI.
2. **The output looked different every day.** I made the AI return JSON, checked that every required field was there, and filled a fixed template. If the JSON comes back broken, the code asks one more time.
3. **Stock data was unreliable.** `yfinance` often gets blocked on GitHub's servers, so I use Finnhub first and fall back to `yfinance`.
4. **GitHub's scheduler ran up to 8 hours late.** Now a free service (cron-job.org) starts the job at exactly 7:30. GitHub's own schedule stays as a backup, and it skips itself if the email was already sent that day.
5. **Daylight saving time.** GitHub schedules only use UTC, so the backup has two times set and only runs the one that matches Toronto's current clock.
6. **Email apps are picky.** Gmail ignores `<style>` tags, so all styling is inline. Tickers like `XEQT.TO` were turned into web links, so the `.TO` is hidden in the email.

## What I learned

- Treat AI output as something to check, not something to trust. Keep facts like prices and links out of its hands.
- Plan for failure: retries, a backup data source, and letting each part fail on its own.
- Free schedulers aren't always on time, so it's worth having a backup.
- HTML email is its own world: inline styles, table layouts, and testing on a phone-sized screen.

## Run it

```bash
pip install -r requirements.txt
python main.py --dry-run --mock-llm   # no keys needed, writes output.html
```

For a real run, set `DEEPSEEK_API_KEY`, `FINNHUB_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD` and `RECIPIENT_EMAIL` as environment variables (or as GitHub Secrets for the scheduled job).
