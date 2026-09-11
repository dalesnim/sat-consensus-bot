# SAT Verbal Consensus Bot — Operator Guide

Everything you need to set this up under your own accounts and run it day to day.

Read `KNOWN-ISSUES.md` alongside this. It is an honest list of what is unfinished and what will bite you. Nothing in it is hidden or downplayed.

---

## 1. What this bot does

A student sends a photo of **one** SAT Reading & Writing question. The bot sends that identical image to **seven independent frontier AI models at once**, then reports what each model chose and why.

The point is the *agreement*, not the answer. The bot never claims to know the correct answer — it reports what the models converged on and how strongly. When they all agree, that is a strong signal. When they split, the student sees the split instead of a confident guess.

This is deliberate and it is the whole product. A bot that confidently states a plausible wrong answer is worse than no bot. Keep that property if you change anything.

**Measured on 17 labeled questions:** 88% correct by majority vote, and **11 out of 11 correct whenever all models agreed**. That second number is the one that matters.

---

## 2. What you need before you start

| Thing | Where | Cost |
|---|---|---|
| A Telegram account | you already have one | free |
| Your own Telegram bot | @BotFather | free |
| An OpenRouter account with credit | openrouter.ai | **you fund this** |
| A computer or server that stays on | your laptop, or a VPS | $0–15/yr |
| Python 3.12 | python.org | free |

> **Important:** Python must be **3.12**. The project pins `>=3.12,<3.13`. Newer versions such as 3.13 or 3.14 will not install.

---

## 3. Create your own bot

1. In Telegram, message **@BotFather**.
2. Send `/newbot`.
3. Choose a display name (e.g. `SAT Consensus`) and a username ending in `bot` (e.g. `my_sat_bot`).
4. BotFather replies with a **token** that looks like `8123456789:AAH...`. Copy it. **This token is a password — anyone who has it controls your bot.**

Optional but worth doing:
- `/setdescription` — what the bot does, shown before a user presses Start.
- `/setuserpic` — an icon.
- `/setprivacy` → **Disable** is not needed; leave the default.

---

## 4. Create your OpenRouter account

1. Sign up at **https://openrouter.ai**.
2. Add credit at **https://openrouter.ai/settings/credits**. Start with **$10–20**.
3. Create a key at **https://openrouter.ai/settings/keys**. Copy it (starts with `sk-or-v1-`).

**All seven models bill through this one account.** You do not need separate OpenAI, Anthropic, or Google accounts.

---

## 5. Find your Telegram numeric ID

You need this so the bot knows you are the owner.

Message **@userinfobot** in Telegram. It replies with your numeric ID, e.g. `123456789`. Do the same for each student you want to give access to — ask them to message that bot and send you the number.

---

## 6. Install

```bash
# from inside the project folder
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Then create your config file:

```bash
cp .env.example .env
```

Open `.env` and fill in **four** values. Leave everything else at its default:

```ini
OWNER_ID=123456789              # your numeric Telegram ID from step 5
TELEGRAM_BOT_TOKEN=8123...      # from BotFather
OPENROUTER_API_KEY=sk-or-v1-... # from OpenRouter
DAILY_SPEND_CAP_USD=5           # see the warning below
```

> ### ⚠ Set a real spend cap before you go live
>
> `DAILY_SPEND_CAP_USD` ships at **1000**, which effectively means *no limit*. That placeholder exists because the previous owner never chose a budget. **Change it.** At roughly $0.25 a question, `5` gives you about 20 questions a day, `20` gives you about 80. Pick a number you would not mind losing to a bug or an abusive user.

`.env` is git-ignored and must never be committed or shared.

---

## 7. Check it works before spending anything

```bash
PYTHONPATH=src .venv/bin/python -m bot --validate-only
```

This checks every model ID against OpenRouter's public catalog. **It is free** — it makes no inference calls.

Expected output:

```
roster ok: 7 models, 5 labs
```

If it names a model instead, that model has been removed from OpenRouter since this was built. See *Model IDs drift* in `KNOWN-ISSUES.md`.

Also run the test suite — also free, no network:

```bash
.venv/bin/pytest -q
```

Expected: **246 passed**.

---

## 8. Start the bot

```bash
./bot.sh start     # start in the background
./bot.sh stop      # stop it
./bot.sh restart   # stop then start
./bot.sh status    # is it running?
./bot.sh logs      # follow the log
```

Logs are written to `bot.log`.

**Edit the greeting in `bot.sh`** — line 27 still prints the previous owner's bot handle `@mb1600SATBot`. Cosmetic only, but confusing.

### Running with Docker instead

```bash
docker compose up -d --build
docker compose logs -f bot
```

The database lives in a named Docker volume, so `docker compose down` (without `-v`) keeps your data.

---

## 9. Giving students access

The bot is **invite-only**. There is no sign-up, no payment integration, no access codes. You add people by hand. Anyone not on the list gets:

> This bot is invite-only. If you've paid for access, message the owner with your Telegram ID.

To add someone, send this to your bot as the owner:

```
/adduser 987654321
```

You can also pre-load the list before first start by putting comma-separated IDs in `ALLOWED_USER_IDS` in `.env`.

Each student is capped at **40 questions per day** (`PER_USER_DAILY_CAP`), resetting at midnight UTC.

---

## 10. Owner commands

These work only for the Telegram ID in `OWNER_ID`. Everyone else gets the generic refusal and learns nothing.

| Command | What it does |
|---|---|
| `/adduser <id>` | Grant a student access |
| `/cost` | Spend today, this week, per question, and cache hit rate |
| `/pause` | Stop accepting questions without killing the process |
| `/resume` | Start accepting again |
| `/status` | Is the bot paused, and basic health |

`/cost` is your business dashboard. Check it daily at first — it is the first place a broken cost path shows up.

---

## 11. What it costs to run

| Item | Cost |
|---|---|
| One question, all 7 models | **≈ $0.247** |
| A repeat of an image already asked | **$0.00** (served from cache) |
| A full SAT R&W practice test (~54 questions) | ≈ $13 |
| Hosting on a cheap VPS | $10–15/year |

Costs are billed per token, so these are averages, not fixed prices. `/cost` shows your real numbers.

**The cache is your biggest lever on margin.** Students work through the same official practice sets, so repeat images are common. An exact re-send of the same image costs nothing and answers in about a second.

---

## 12. How students use it

Tell them:

1. Send **one question at a time**. The bot rejects images with multiple questions.
2. Send it as a **file/document** rather than a photo when possible — Telegram compresses photos, and compression costs accuracy.
3. Make sure the whole question *and all four answer choices* are in frame, in focus, and well lit. Blurry images are rejected before any money is spent.
4. The bot does **not** tell you the correct answer. It tells you what seven AI models chose. When they all agree, trust it. When they split, the split is the information — ask a teacher.

There is currently **no `/help` command** to tell them any of this. See `KNOWN-ISSUES.md`.

---

## 13. Where things are

```
src/bot/
  main.py            startup, polling, wiring
  pipeline.py        the ordered flow: size check -> quality gate -> cache -> models -> reply
  config.py          settings and roster loading
  orchestrator/      the parallel calls to the 7 models, JSON contract, vote tallying
  images/            quality grading, perceptual hash, base64 encoding
  db/                SQLite: questions, attempts, users, spend
  cost/              spend cap policy and the /cost report
  formatting/        how replies are built
  handlers/          Telegram message and command handling
  middleware/        allowlist and per-user cap enforcement

models.yaml          which 7 models, their costs, the reduced set
.env                 your secrets (never commit)
data/bot.db          the database
tests/               246 tests, all offline
```

**`models.yaml` — do not casually change the model list.** The seven were chosen by measuring accuracy against 17 labeled questions. Several obvious-looking candidates were removed for scoring badly: `mistral-large` (53%), `kimi-k2.6` (41%), and three others that never returned valid JSON at all. Swapping in a cheaper model will quietly cost you accuracy, which is the entire product.

---

## 14. Daily operation

- **Check `/cost`** once a day at first.
- **Watch `bot.log`** if anything seems wrong: `./bot.sh logs`.
- **After changing `.env` or any code, restart** — `./bot.sh restart`. The bot does not reload configuration on its own.
- **Back up `data/bot.db`** periodically. It holds every question, every model answer, and your user list.

---

## 15. Legal — read this

The previous owner flagged this and it now applies to you.

**"SAT" is a registered trademark of the College Board**, and their practice questions are copyrighted. This tool is built around processing those questions, and you intend to charge for it. That is a real commercial exposure, not a theoretical one.

Get advice from someone qualified before you sell access publicly. At minimum, do not use "SAT" in your bot's name or marketing in a way that implies College Board endorsement.
