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
