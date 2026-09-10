# SAT Verbal Consensus Bot

A Telegram bot for SAT Reading & Writing practice. A user sends a photo of one SAT verbal
question and the bot sends that identical image to six independent frontier models in
parallel, in an honest attempt to build a confidence signal instead of a single guessed
answer. When the models agree, that agreement is the confidence signal; when they split, the
bot reports the split with each side's reasoning rather than fabricating a single answer.

## Prerequisites

- Python 3.12 (the project pins `>=3.12,<3.13`)
- An OpenRouter account with a funded balance and an API key
  (https://openrouter.ai/settings/keys)
- A Telegram bot token from BotFather (`/newbot` in a chat with `@BotFather`)

## Setup

```bash
cp .env.example .env
```

Fill in `OPENROUTER_API_KEY` and `TELEGRAM_BOT_TOKEN` in `.env`. Every other value has a
working default. **`.env` is git-ignored and must never be committed** — it is the only
place either secret is ever written to disk.

```bash
pip install -e ".[dev]"
```

## Run the tests

```bash
pytest -q
```

## Validate the roster against the live OpenRouter catalog

Confirms all six configured model IDs still exist, accept image input, and support
structured outputs — no credentials required.

```bash
python -m bot --validate-only
```

## Measure real per-model latency (the latency spike)

Fires all six configured models once against a real SAT question photo and records actual
wall-clock time and completion tokens per model. Requires `OPENROUTER_API_KEY` to be set.

```bash
python scripts/latency_spike.py --image <path/to/question.jpg>
```

## Run the bot locally

```bash
python -m bot
```

## Run the bot in Docker

```bash
docker compose up -d --build
docker compose logs -f bot
```

## Operations

### Environment variables

| Variable | Purpose |
|----------|---------|
| `OWNER_ID` | Numeric Telegram user id of the bot owner. Gates `/adduser`, `/cost`, `/pause`, `/resume`, and `/status`. Unset disables all owner commands for everyone (fails closed, never open). |
| `ALLOWED_USER_IDS` | Comma-separated Telegram user ids seeded into the allowlist at startup. Optional — buyers can also be added live with `/adduser`. |
| `PER_USER_DAILY_CAP` | Max questions a single allowlisted user can ask per UTC day. Default `40`. |
| `DAILY_SPEND_CAP_USD` | Global daily spend cap in USD, UTC day boundary. Above it, the bot answers with a reduced, cheaper model set and discloses the downgrade in the reply. |
| `ROUND_COST_SAFETY_MULTIPLIER` | Multiplier applied to a round's cost estimate when reserving budget, covering a possible JSON-repair retry without a second reservation. |
| `DB_PATH` | Path to the SQLite database file. |

### Owner commands

- `/adduser <telegram_id>` — grants a Telegram user access. Owner-only.
- `/cost` — reports today's spend, the cap, the last 7 days, question and cache-hit counts,
  and cost per question (today and all time). Owner-only; a non-owner gets the generic
  invite-only refusal with no figures. All daily boundaries are UTC.

### Database

The SQLite database lives on the `sqlite_data` Docker volume and survives
`docker compose down` (without `-v`) across redeploys.

To audit cache-served rows (a cache hit has no error state, so querying is the only way to
spot a phash collision):

```bash
sqlite3 data/bot.db "SELECT id, created_at, source_question_id FROM questions WHERE served_from_cache = 1"
```
