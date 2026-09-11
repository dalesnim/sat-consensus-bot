# Known Issues

An honest inventory of what is unfinished, broken, or risky, as of **2026-09-11**.

Nothing here is hidden or softened. Each item says what is wrong, what you will actually see when it happens, and how to fix it. Ordered by how urgently it needs your attention.

The last section lists decisions that **look** like bugs but are deliberate. Read it before you "improve" anything.

---

## Fix before you go live

### 1. The spend cap is effectively disabled

**Severity:** high — this is how you lose money
**Where:** `.env` → `DAILY_SPEND_CAP_USD`

The cap mechanism is fully built and tested, but ships set to `1000`, which means no practical limit. The previous owner never chose a budget, so the placeholder stayed.

**What happens:** a bug, an abusive user, or a burst of questions can drain your OpenRouter balance with nothing stopping it.

**Fix:** set a real number in `.env` and restart. At ~$0.25/question, `5` ≈ 20 questions/day. Once you set it, the behavior is already correct and tested: above the cap the bot drops to a cheaper 5-model set and says so in the reply; if even that will not fit, it refuses rather than overspending.

---

### 2. New users get no explanation — there is no `/help` or `/start`

**Severity:** high — this is the first thing every new student hits
**Where:** no handler exists for either command

**What happens:** a student who has been granted access sends `/start`, and **nothing comes back**. There is no onboarding at all. They do not learn to send one question at a time, to prefer files over photos, or — most importantly — that the bot deliberately does not state a correct answer.

**Fix:** add a `/help` handler. `src/bot/handlers/owner.py` is the pattern to copy, minus the owner check. Content to cover is drafted in `HANDOVER.md` §12. Also register the commands with @BotFather's `/setcommands` so they autocomplete.

This is the single highest-value thing you can build. It is maybe 40 lines.

---

### 3. It is not deployed anywhere — it runs on a laptop

**Severity:** high — the bot is offline whenever the machine sleeps

There is a working `Dockerfile` and `docker-compose.yml`, but no server was ever provisioned. The bot was run by hand on a MacBook via `./bot.sh start`.

**What happens:** close the laptop, the bot dies. No auto-restart on boot, no restart after a crash.

**Fix:** get a cheap VPS (RackNerd ~$10–15/yr, or Vultr ~$2.50/mo — both were researched and are adequate; Hetzner was rejected by the previous owner). Then `docker compose up -d --build`. The compose file already sets `restart: unless-stopped`, so Docker handles crash recovery for you.

> **Note for macOS:** do not try to set up auto-start with `launchd` if the project sits under `~/Desktop`, `~/Documents`, or `~/Downloads`. macOS TCC file protection blocks it and the service fails silently. This was attempted and abandoned. A Linux VPS has no such problem.

---

## Will bite you as you grow

### 4. It degrades badly when many students ask at once

**Severity:** medium — invisible at 3 users, ugly at 15
**Where:** `src/bot/main.py:47`

The HTTP client is created as `httpx.AsyncClient()` with **default limits** (`max_connections=100`), and there is **no semaphore** capping how many rounds run at once. Each question opens 7 connections.

| Simultaneous questions | Connections | Result |
|---|---|---|
| 1–8 | ≤56 | fine |
| ~14 | 98 | at the ceiling |
| 20+ | 140 | requests queue waiting for a socket |

**What happens — and why it is worse than it sounds:** queued requests still burn their 47-second timeout *while waiting for a connection that never frees up*. Models then "abstain", and the reply degrades to *"not enough models responded"*. To the student that reads as **the models disagreed**, when in fact the bot starved itself. Your core selling point — honest confidence signaling — silently inverts under load.

**Fix (~20 lines):**
1. Pass explicit limits: `httpx.AsyncClient(limits=httpx.Limits(max_connections=200, max_keepalive_connections=40))`
2. Wrap the round in a global `asyncio.Semaphore(8)` so the 9th concurrent question *waits its turn*. Students already see a typing indicator, so a few seconds of queueing is invisible — far better than eight people simultaneously getting a degraded answer.

**Note the underlying concurrency is otherwise sound.** Both the per-user daily cap and the global spend reservation are single atomic conditional `UPDATE` statements, so simultaneous questions genuinely cannot both slip past a limit. The database is fine. Only the connection pool is unbounded.

---

### 5. A very long reply can silently vanish

**Severity:** medium
**Where:** `src/bot/handlers/ingest.py:20-26`

Telegram rejects messages over **4096 characters**. Nothing in the code checks length before sending.

There is a fallback: if the formatted send raises `TelegramBadRequest`, it retries as plain text. **But that fallback resends the same too-long string**, so when the cause is length rather than formatting, it fails a second time and the student gets **nothing at all** — after you have already paid ~$0.25 for the answer.

**What happens:** rare today, because reasoning is capped at 4 bullets per position. It becomes likely on an unresolved 7-way split where every position prints its own reasoning block.

**Fix:** split the reply into chunks of ≤4096 characters at paragraph boundaries and send them in sequence. Alternatively make the fallback truncate rather than resend verbatim — a truncated answer beats a missing one.

> **Good news on a related point:** replies are built with aiogram's entity-based `Text()` API, which sends `entities` rather than a MarkdownV2 string. Special characters in model-generated text therefore **cannot** break the formatting. The roadmap lists "escaping" as unbuilt work; in practice the chosen API already prevents that class of failure. Length is the real remaining risk.

---

### 6. Phase 2 was never verified against the live bot

**Severity:** medium — the code is tested, the integration is not

The caching, spend cap, and `/cost` features have **246 passing automated tests**, but all of them mock the network. They were never exercised end-to-end against a real Telegram client and real OpenRouter traffic, because doing so costs money and the previous owner's balance was nearly gone.

**What this means:** the logic is well tested in isolation. Wiring bugs are still possible.

**Fix:** run the 10-step live checklist in `.planning/phases/02-persistence-caching-cost-control/02-05-SUMMARY.md` (section *"Outstanding: Task 3"*). It costs roughly **$1.00–1.25** total and takes 20 minutes. Do it once, early, on your own account. The two checks that matter most: **a repeated image really does come back free**, and **`/cost` figures match what OpenRouter's dashboard says you spent**.

---

## Unfinished features

These were planned and specified but never built. None of them break anything — the bot works without them.

### 7. No "Full breakdown" button

Students see merged reasoning for the winning answer and the runner-up, but cannot drill into what each individual model said per answer choice. **All the data is already persisted** in the `attempts` table — it needs a button and a formatter, not new inference.

### 8. No "Wrong answer" correction flow

**This is the more important gap of the two.** There is no way for a student to report that the consensus was wrong, and the `ground_truth` column in the database is never populated.

**Why it matters:** this was designed as the *only* mechanism for measuring real-world accuracy. Without it you have no feedback loop — you cannot tell whether the bot is at 88% or has quietly degraded to 60% because a model changed underneath you. The planned design is A/B/C/D buttons rather than free text, so the column cannot be polluted by malformed input.

### 9. No student-facing commands at all

Covered in issue #2. There is `/help`, and nothing else planned for students.

---

## Operational gaps

### 10. Model IDs drift out of OpenRouter's catalog

Providers retire models. If a configured ID disappears, the bot **refuses to start** rather than running a short roster — deliberate, so you cannot silently lose a model.

**Detection is free:** `PYTHONPATH=src .venv/bin/python -m bot --validate-only` checks the public catalog and makes no inference calls. Run it after any outage. If it names a model, replace that entry in `models.yaml` with a current vision-capable model from a different lab than the others, then re-run.

### 11. Nothing tells you when the bot goes down

No health check, no alerting. If it crashes you find out when a student complains.

**Fix:** Docker's `restart: unless-stopped` covers crashes. For anything more, a cron job that pings `/status` and messages you on failure is enough at this scale.

### 12. No backups

`data/bot.db` holds every question, every model answer, your entire user list, and all spend history. There is no backup of any kind.

**Fix:** a nightly `sqlite3 data/bot.db ".backup /somewhere/bot-$(date +%F).db"` in cron. It is one line and it is the difference between an inconvenience and losing your business records.

### 14. A bad OpenRouter key passes startup and only fails on the first real question

**Severity:** medium — costs you a confusing debugging session, not money
**Where:** `src/bot/validation/boot.py`

Boot validation checks every model ID against `https://openrouter.ai/api/v1/models`, which is a **public, unauthenticated** endpoint. It therefore proves the roster is valid but proves nothing about your API key.

**What happens:** the bot logs a confident `roster ok: 7 models, 5 labs` and starts polling normally. Then the first real question returns `401 Unauthorized` from all seven models at once, and the user gets "not enough models responded". Confirmed live during the first server deploy, where four characters had been lost from the key while pasting.

**Fix:** add an authenticated call to `https://openrouter.ai/api/v1/credits` during boot validation. It is free, requires the key, and also returns the remaining balance — so the same check can log a warning when credit is nearly exhausted. Fail startup on 401 the same way an invalid model ID does.

**Workaround until then:** after changing the key, verify its length and hash rather than eyeballing it:
```bash
K=$(grep -E '^OPENROUTER_API_KEY=' .env | cut -d= -f2- | tr -d '\r\n')
echo "length ${#K}  sha $(printf '%s' "$K" | sha256sum | cut -c1-16)"
```
Compare against a machine where the key is known to work.

---

### 13. `bot.sh` prints the previous owner's bot handle

Cosmetic. `bot.sh` line 27 echoes `@mb1600SATBot` on startup. Change it to yours.

---

## Do NOT "fix" these — they are deliberate

Each of these looks like a defect and is not. Changing them will make the product worse.

| Looks wrong | Why it is correct |
|---|---|
| **7 models is expensive — why not 1 or 2?** | Agreement across independent models *is* the product. One model gives you a confident guess with no confidence signal, which is what every free tool already does badly. Measured: 11/11 correct whenever all models agreed. |
| **`mistral-large` and `kimi-k2.6` are cheaper — swap them in** | Both were tested and removed for **accuracy**: 53% and 41% respectively. Three others (`glm-5v-turbo`, `nova-premier`, `ernie`) never returned valid JSON at all. The roster was chosen by measurement on 17 labeled questions, not by price. |
| **`deepseek` is missing and it is the cheapest option** | It was in the roster and was removed. It is persistently rate-limited (429) upstream on *image* payloads specifically, while text-only calls succeed. It silently dropped the live roster from 4 labs to 3, breaking the independence premise. |
| **Reasoning effort is forced to minimum — surely higher is smarter** | At default effort, some models take 16–130 seconds to first token. The round budget is 50 seconds. Raising it means models time out and abstain, which loses you far more accuracy than the extra reasoning gains. Note two models (`gpt-6-astra`, `gemini-3.7-flash`) *reject* effort `none` outright and must use `minimal`. |
| **The cache only hits on byte-identical images — make it fuzzy** | Deliberate, and important. SAT questions share a near-identical visual template, so a fuzzy match would eventually serve **the wrong question's answer** to a student. The cost asymmetry is stark: a missed cache hit costs $0.25; a false hit destroys the product's credibility. Exact 256-bit hash equality only. |
| **The bot never says which answer is correct** | This is the entire product thesis, not an oversight. It reports what models chose and how strongly they agreed. Keep it. |

---

## Quick reference

| | |
|---|---|
| Tests passing | **246** (all offline, no network) |
| Lint | Ruff clean |
| Cost per question | ≈ **$0.247** (7 models) |
| Repeat of a cached image | **$0.00** |
| Round wall time | 16–28 seconds |
| Measured accuracy | 88% by majority; 11/11 when unanimous |
| Python | **3.12 only** (`>=3.12,<3.13`) |
| Free health check | `python -m bot --validate-only` |
