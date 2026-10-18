# jobs-digest

Score remote job postings against a small YAML profile of what you want (and what you avoid), remember what you have already seen in SQLite, and send only the **new** matches to **Telegram** or **email** every morning.

Checking job boards is a daily routine that a script can own end to end. This is the second project in my portfolio: the first one, [remote-jobs-scraper](https://github.com/alexanderimanuel/remote-jobs-scraper), collects the postings; this one turns them into a ranked digest that arrives on its own, with a store so the same posting never shows up twice and a dry-run mode so you can tune the profile before anything is sent.

[![tests](https://github.com/alexanderimanuel/jobs-digest/actions/workflows/ci.yml/badge.svg)](https://github.com/alexanderimanuel/jobs-digest/actions/workflows/ci.yml)

## Run it in three commands

```bash
git clone https://github.com/alexanderimanuel/jobs-digest.git && cd jobs-digest
pip install -e .
python -m jobs_digest --dry-run
```

Without a `config.yaml` the example config is used: it runs the scraper against RemoteOK, Remotive and We Work Remotely, scores the last two weeks of postings, and prints the digest instead of sending it. This is the real output from 18 October 2026:

```
Jobs digest 2026-10-18: 5 new matches (47 postings scanned, 5 matched your profile)

 1. Senior Python Developer (CRM - AI/LLM)
    Emerging Travel Group · weworkremotely · 2026-10-15 · Anywhere in the World
    score 15: python (title) +6, automation +3, llm (title) +4, ai (title) +2
    https://weworkremotely.com/remote-jobs/emerging-travel-group-senior-python-developer-crm-ai-llm

 2. Remote AI Trainers (Generalist and Python Coding Experts)
    AITrainers · weworkremotely · 2026-10-14 · Anywhere in the World
    score 9: python (title) +6, ai (title) +2, contract +1
    https://weworkremotely.com/remote-jobs/aitrainers-remote-ai-trainers-generalist-and-python-coding-experts

 3. APAC Python
    Kodland · remoteok · 2026-10-16 · Worldwide
    score 6: python (title) +6
    https://remoteOK.com/remote-jobs/remote-apac-python-kodland-1137534

 4. Software Engineer AI Coding Tasks
    Askable · remoteok · 2026-10-17 · Worldwide · $10,000
    score 5: python +3, ai (title) +2
    https://remoteOK.com/remote-jobs/remote-software-engineer-ai-coding-tasks-askable-1137538

 5. Senior Software Engineer II Applied AI
    Wrapbook · remoteok · 2026-10-15 · Worldwide
    score 5: python +3, ai (title) +2
    https://remoteOK.com/remote-jobs/remote-senior-software-engineer-ii-applied-ai-wrapbook-1137527

[dry run] nothing sent, store digest.sqlite untouched; channels: telegram
```

Every line of the score is explained, so tuning the profile is a matter of reading the digest and adjusting weights. The `daily digest` workflow refreshes [`data/latest-digest.txt`](data/latest-digest.txt) every morning. On Telegram the same digest arrives as a message with the titles as links; the email version has a plain-text body and an HTML alternative.

## Sending it for real

1. Copy `config.example.yaml` to `config.yaml` and edit the profile.
2. Copy `.env.example` to `.env` and fill in the secrets for the channels you enabled. Secrets are only ever read from environment variables; `config.yaml` and `.env` are git-ignored.
3. Run `python -m jobs_digest`.

```
telegram: sent 5 new posting(s)
```

Run it again and nothing is sent: the store (`digest.sqlite`) remembers what each channel has already received. A posting is identified by its canonical URL, so the same job seen through a tracking link or a trailing slash is still the same job. If a send fails the postings stay unsent and the next run retries them, and the process exits with code 2 so a scheduler notices.

**Telegram**: create a bot with [@BotFather](https://t.me/BotFather), send it any message, then read your chat id from `https://api.telegram.org/bot<TOKEN>/getUpdates`. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

**Email**: any SMTP server with STARTTLS. For Gmail use `smtp.gmail.com`, port 587 and an app password. Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` and the recipient in `channels.email.to`.

**Schedule it.** The simplest way is to fork this repo and add the two Telegram secrets to the fork: the `daily digest` workflow then sends the digest every morning at 08:30 WIB and keeps the SQLite store between runs with the Actions cache. On a machine of your own, one cron line does the same:

```
30 8 * * *  cd /path/to/jobs-digest && python -m jobs_digest >> digest.log 2>&1
```

## Config reference

`config.yaml` has four sections. Everything is optional except `input` and `profile.keywords`.

| key                           | meaning                                                                                        | default         |
|-------------------------------|------------------------------------------------------------------------------------------------|-----------------|
| `input.scraper`               | run remote-jobs-scraper in-process; keys `keywords`, `sources`, `since_days`, `title_only`     |                 |
| `input.path`                  | instead: a local CSV or JSON written by `python -m remote_jobs -o jobs.json`                    |                 |
| `input.url`                   | instead: an http(s) URL to such a file                                                           |                 |
| `profile.keywords`            | `term: weight`. A term is counted once per posting; title hits count `title_multiplier` times  | required        |
| `profile.title_multiplier`    | how much more a hit in the title is worth than one in tags, company, location or description    | `2`             |
| `profile.must_have`           | if not empty, at least one of these terms must appear somewhere                                 | `[]`            |
| `profile.avoid`               | any of these terms anywhere drops the posting (title, tags, location, description)              | `[]`            |
| `profile.min_score`           | postings below this score are dropped                                                            | `1`             |
| `profile.max_age_days`        | postings older than this are dropped; postings with no date are kept; `0` disables              | `7`             |
| `profile.max_items`           | maximum postings per digest; the rest wait for the next run                                      | `10`            |
| `store`                       | path of the SQLite file                                                                          | `digest.sqlite` |
| `channels.telegram.enabled`   | needs `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`; optional `chat_id` override                      | `false`         |
| `channels.email.enabled`      | needs `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`; options `to`, `from`, `subject`, `starttls` | `false` |

Terms match at the start of a word, case-insensitively: `ai` hits "AI-powered" but not "retail", and `technical writer` hits "Senior Technical Writer" but not "Technical Support Writer".

The pipeline is: age filter, avoid terms, must-have terms, keyword score, minimum score, then the store filter and the `max_items` cap, with the best score first and newer postings winning ties.

## Options

```
python -m jobs_digest --help

  -c, --config FILE      YAML config (default: config.yaml, falling back to config.example.yaml)
  --input FILE_OR_URL    read postings from this CSV/JSON file or URL instead of what the config says
  --store FILE           SQLite store path (overrides config)
  --dry-run              print the digest instead of sending it; reads the store but never writes it
  --max-items N          cap the digest at N postings (overrides config)
  --env-file FILE        load KEY=VALUE secrets from this file if it exists (default: .env)
  -v, --verbose          log every dropped posting with the reason, plus per-step counts
```

Exit codes: `0` ok, `1` configuration problem (missing file, bad YAML, missing secret), `2` at least one channel failed to send.

Examples:

```bash
# Tune the profile: see why each posting was dropped
python -m jobs_digest --dry-run -v

# Score a file the scraper wrote earlier, without running the scraper
python -m remote_jobs -k ai -k automation --since-days 7 --no-preview -o jobs.json
python -m jobs_digest --input jobs.json --dry-run

# Score the scraper's daily snapshot straight from GitHub
python -m jobs_digest --input https://raw.githubusercontent.com/alexanderimanuel/remote-jobs-scraper/main/data/latest.json --dry-run
```

## How it works

```
jobs_digest/
  cli.py          argparse entry point; run() is the pipeline: load -> score -> store filter -> send
  config.py       YAML -> dataclasses with validation; .env loader; secrets only from the environment
  models.py       Posting: the nine columns remote-jobs-scraper writes, plus the canonical-URL key
  sources.py      load postings from a file, a URL, or remote-jobs-scraper called as a library
  scoring.py      keyword / must-have / avoid / age rules; every point comes with a reason string
  store.py        SQLite: postings seen, and (posting, channel) pairs already sent
  digest.py       the Digest and its renderers: plain text, Telegram HTML, email HTML; 4096-char chunking
  channels/
    base.py       Channel interface and ChannelError
    telegram.py   Bot API sendMessage, one call per chunk
    email.py      SMTP with STARTTLS, text + HTML alternative
```

Design choices:

- **Idempotent by construction.** The store records `(posting, channel)` pairs, not "the digest was sent". A posting goes to each channel exactly once, a failed channel is retried next run without re-sending to the channel that worked, and `max_items` only delays the overflow instead of losing it.
- **Dry run is read-only.** It reads the store to show what a real run would send, but never writes, so it is safe to run as often as you like while tuning.
- **Fail before doing work.** Channels are built and their secrets checked before any posting is fetched, so a typo in `.env` is reported immediately rather than after a 20-second scrape.
- **Explainable scores.** Each posting carries the list of reasons that produced its score. The digest prints them, and `-v` prints the reason every other posting was dropped.
- **Tests run offline.** Fixtures in `tests/fixtures/` are real-shaped postings; Telegram and SMTP are exercised through small fakes.

## Adding a channel

1. Create `jobs_digest/channels/<name>.py` with a `Channel` subclass: set `name`, read your secrets in `__init__` with `require_env(...)` so a missing one raises `ConfigError` before any send, and implement `send(self, digest)` raising `ChannelError` on failure. Use `format_text`, `format_telegram` or `format_email_html` from `digest.py`, or write your own renderer.
2. Register the class in `jobs_digest/channels/__init__.py` under `CHANNELS`.
3. Add a `channels.<name>` block to `config.example.yaml` and the variables to `.env.example`.
4. Add a test with a fake transport, like the ones in `tests/test_channels.py`.

A Slack or Discord webhook channel is about 25 lines.

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

## Author

Alexander Imanuel Widjanarko, Malang, Indonesia. AI engineer and researcher; I build scrapers, automations and integrations that replace manual work, plus the documentation to go with them.
[alexiw.my.id](https://alexiw.my.id) · [LinkedIn](https://www.linkedin.com/in/alexander-imanuel-widjanarko) · [Google Scholar](https://scholar.google.com/citations?user=t97LgJ4AAAAJ&hl=en)

MIT License.
