# Architecture Research

**Domain:** Single-VPS Dockerized Telegram bot with parallel multi-LLM fan-out (aiogram 3.x + OpenRouter + SQLite)
**Researched:** 2026-09-10
**Confidence:** HIGH (aiogram router patterns, asyncio.gather/wait_for semantics, aiosqlite single-writer behavior — all confirmed against current docs); MEDIUM (OpenRouter `/models` capability fields — confirmed field names exist, exact JSON shape should be spot-checked against a live response during Phase 1 boot-validation implementation)

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Telegram / aiogram 3.x                       │
├──────────────────────────────────────────────────────────────────────┤
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌────────────────┐    │
│  │ photo      │  │ callback  │  │ owner      │  │ middleware:    │    │
│  │ handler    │  │ handlers  │  │ commands   │  │ allowlist,     │    │
│  │ (ingest)   │  │ (buttons) │  │ (/cost etc)│  │ daily cap      │    │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └────────────────┘    │
├────────┴──────────────┴──────────────┴────────────────────────────────┤
│                          Orchestration layer                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐  │
│  │ image utils   │→ │ cache lookup  │→ │ fan-out orchestrator      │  │
│  │ (bytes, phash)│   │ (SQLite)      │   │ (asyncio.gather, 6 calls)│  │
│  └──────────────┘   └──────────────┘   └─────────────┬────────────┘  │
│                                                        │               │
│                        ┌───────────────────────────────┘              │
│                        ▼                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐  │
│  │ per-model     │   │ response      │   │ consensus tallying /      │  │
│  │ client        │ → │ validation    │ → │ reply formatting          │  │
│  │ (httpx call)  │   │ (pydantic +   │   │ (MarkdownV2, spoiler)     │  │
│  │               │   │  repair retry)│   │                            │  │
│  └──────────────┘   └──────────────┘   └──────────────────────────┘  │
├──────────────────────────────────────────────────────────────────────┤
│                    Config / boot-time validation                      │
│  ┌───────────────────┐   ┌──────────────────────────────────────┐    │
│  │ models.yaml loader │→ │ OpenRouter /models cross-check +       │    │
│  │ (pydantic settings)│   │ lab-diversity assertion (fail loudly) │    │
│  └───────────────────┘   └──────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────────┤
│                            Persistence (SQLite)                       │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌───────────────────┐    │
│  │ questions │  │ attempts  │  │ users     │  │ spend / cost roll- │   │
│  │  table    │  │  table    │  │  table    │  │ up (view or query) │   │
│  └──────────┘  └───────────┘  └──────────┘  └───────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| aiogram handlers | Translate Telegram updates into domain calls; no business logic | `aiogram.Router` per concern (ingestion, buttons, owner commands) |
| middleware | Allowlist gate, per-user daily cap, typing-action indicator | `aiogram` outer middleware, runs before handler body |
| image utils | Extract bytes (photo vs document), compute perceptual hash | `imagehash` + `Pillow`, pure functions, no I/O beyond decode |
| cache layer | Look up phash in `questions` table; short-circuit fan-out on hit | Plain SQL `SELECT` through the shared aiosqlite connection |
| fan-out orchestrator | Own the six-way `asyncio.gather`, apply the 30s wall-clock budget, own the degraded-mode subset decision | One `async def run_round(...)` function — no framework |
| per-model client | Single OpenRouter HTTP call for one model, one image, one prompt | `httpx.AsyncClient`, per-call `timeout=`, returns raw text or raises |
| response validation | Parse JSON, validate against pydantic contract, trigger the one repair retry, else mark abstain | `pydantic.BaseModel.model_validate_json`, wraps client call |
| consensus tallying | Pure function: six validated (or abstained) results → vote counts → confidence tier | No I/O; easily unit-tested |
| reply formatting | Vote tier + reasoning → Telegram MarkdownV2 text + inline keyboard | Pure function, isolated from aiogram objects where possible |
| config loader | Parse `models.yaml` + env into typed settings | `pydantic-settings`, loaded once at process start |
| boot-time validation | Confirm every model ID exists on OpenRouter, supports image input, and labs ≥ 4 distinct — before the bot starts polling/webhook | Runs in `main()` before `dp.start_polling(...)`; raises and exits nonzero on failure |
| persistence | Own all SQL; single shared aiosqlite connection; owns migrations | `aiosqlite.connect(..., isolation_level=None)` + hand-written `schema.sql` |
| cost accounting | Per-attempt token/cost row; daily aggregate query; cap check before each round | Derived from `attempts` table, no separate ledger table needed |

## Recommended Project Structure

```
src/
├── bot/
│   ├── __init__.py
│   ├── main.py                # entrypoint: load config, boot-validate, start dispatcher
│   ├── config.py               # pydantic-settings: env + models.yaml → typed Settings
│   ├── handlers/
│   │   ├── ingest.py           # photo/document handler → orchestrator → reply
│   │   ├── buttons.py          # "Full breakdown", "Wrong answer" callback handlers
│   │   └── owner.py            # /adduser, /cost
│   ├── middleware/
│   │   ├── allowlist.py        # rejects non-allowlisted users
│   │   └── rate_limit.py       # per-user daily cap
│   ├── orchestrator/
│   │   ├── fanout.py           # run_round(): asyncio.gather over 6 models, timeout budget
│   │   ├── client.py           # call_model(): one httpx call to OpenRouter for one model
│   │   ├── contract.py         # pydantic models: ModelResponse, EliminationReason, etc.
│   │   └── consensus.py        # tally(): pure function, vote counts → confidence tier
│   ├── formatting/
│   │   └── reply.py            # build_reply_text(), build_keyboard()
│   ├── images/
│   │   └── extract.py          # get_image_bytes(), compute_phash()
│   ├── validation/
│   │   └── boot.py             # validate_models_against_openrouter(), lab-diversity check
│   ├── db/
│   │   ├── connection.py       # single shared aiosqlite connection, WAL pragma
│   │   ├── schema.sql           # questions / attempts / users DDL
│   │   ├── migrations.py       # ordered list of ALTER statements, applied at boot
│   │   ├── questions.py        # CRUD for questions table (incl. phash lookup)
│   │   ├── attempts.py         # CRUD for attempts table (incl. cost aggregates)
│   │   └── users.py            # CRUD for users table
│   └── cost/
│       └── guard.py            # check_daily_cap(), pick_model_subset() for degraded mode
├── models.yaml                  # the six model IDs, labs, per-model price, fallback subset
├── schema.sql                   # (or under db/, pick one — don't duplicate)
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── pyproject.toml
```

### Structure Rationale

- **Flat, not layered-by-framework.** No `services/`, `repositories/`, `dto/` ceremony — the user explicitly wants minimal diffs and no orchestration frameworks. Each top-level folder is a single concern with 1-4 files; nothing needs a subpackage of its own yet.
- **`orchestrator/` is the heart of the system** and is kept separate from `handlers/` on purpose: `fanout.py` must be callable and testable without a Telegram `Message` object, since it's the single riskiest piece of logic (parallel calls, timeouts, partial failure) and needs isolated tests.
- **`contract.py` lives inside `orchestrator/`**, not a shared `models/` package, because the JSON contract is *only* consumed by the fan-out/validation path — no other component needs it, and colocating avoids a premature "shared types" folder.
- **`db/` owns all SQL.** Every other module calls into `db/*.py` functions; no component runs raw SQL against the connection directly. This is the seam that makes SQLite swappable later without touching orchestrator or handler code, even though nothing else is planned right now.
- **`cost/guard.py` is separate from `db/attempts.py`** because it encodes a policy decision (cap → degraded subset), not a data access pattern. `fanout.py` calls `guard.py` before firing, `guard.py` calls `db/attempts.py` to read the day's spend.
- **`validation/boot.py` is separate from `config.py`.** `config.py` only parses and type-checks `models.yaml`/env (no I/O). `boot.py` makes network calls to OpenRouter and enforces domain rules (lab diversity, ID existence). Splitting these means config parsing stays unit-testable without network mocking.

## Architectural Patterns

### Pattern 1: Bounded parallel fan-out with per-call isolation

**What:** Fire all six model calls concurrently; no single call's failure, timeout, or bad JSON can cancel or corrupt the others. The round always produces exactly six outcomes: a valid answer or an abstain, never an exception propagating out of `run_round`.

**When to use:** Any time you fan out to N independent external services and want partial-success semantics rather than all-or-nothing.

**Trade-offs:** `asyncio.gather(..., return_exceptions=True)` is simpler than `asyncio.wait`/`TaskGroup` variants but requires the caller to manually inspect each result for `isinstance(r, Exception)`. `asyncio.TaskGroup` (3.11+) cancels siblings on first unhandled exception by default, which is the *wrong* default here — must catch inside each task instead of letting exceptions escape to the group.

**Example:**
```python
# orchestrator/fanout.py
import asyncio
import time

ROUND_BUDGET_SECONDS = 30
PER_MODEL_TIMEOUT_SECONDS = 25  # leaves headroom for tally + reply formatting

async def call_one_model(model: ModelConfig, image_bytes: bytes, prompt: str) -> AttemptResult:
    """Never raises. Always returns an AttemptResult, valid or abstained."""
    started = time.monotonic()
    try:
        raw = await asyncio.wait_for(
            client.call_model(model, image_bytes, prompt),
            timeout=PER_MODEL_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, httpx.HTTPError) as exc:
        return AttemptResult.abstain(model, reason=f"transport_error:{exc}", latency=time.monotonic() - started)

    parsed = contract.try_parse(raw)
    if parsed is None:
        # one repair retry: re-ask with the same image + a "your JSON was invalid, retry" prefix
        try:
            repaired_raw = await asyncio.wait_for(
                client.call_model(model, image_bytes, prompt, repair_of=raw),
                timeout=PER_MODEL_TIMEOUT_SECONDS,
            )
            parsed = contract.try_parse(repaired_raw)
        except (asyncio.TimeoutError, httpx.HTTPError):
            parsed = None
        if parsed is None:
            return AttemptResult.abstain(model, reason="unparseable_after_repair", latency=time.monotonic() - started)

    return AttemptResult.ok(model, parsed, latency=time.monotonic() - started)


async def run_round(models: list[ModelConfig], image_bytes: bytes, prompt: str) -> list[AttemptResult]:
    tasks = [call_one_model(m, image_bytes, prompt) for m in models]
    try:
        # Outer wait_for is the hard 30s ceiling; call_one_model already self-bounds
        # to PER_MODEL_TIMEOUT_SECONDS so this outer timeout should rarely fire —
        # it exists as a last-resort circuit breaker, not the primary control.
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=ROUND_BUDGET_SECONDS,
        )
    except asyncio.TimeoutError:
        # Extremely defensive path: gather itself didn't finish in time.
        # Any task still pending here is cancelled; treat unfinished models as abstains.
        results = [AttemptResult.abstain(m, reason="round_timeout") for m in models]

    # call_one_model never raises, but guard anyway in case of a programming bug
    return [
        r if isinstance(r, AttemptResult) else AttemptResult.abstain(m, reason=f"unexpected:{r}")
        for m, r in zip(models, results)
    ]
```

Key correctness points, verified against current asyncio semantics:
- `asyncio.gather(..., return_exceptions=True)` lets all six coroutines run to completion even if some raise — but because `call_one_model` already catches everything internally, `return_exceptions=True` is a defensive backstop, not the primary error-handling mechanism. **Catch inside each task**, don't rely on `gather` to catch for you — this is what makes per-model isolation actually correct rather than accidental.
- The per-model timeout (`asyncio.wait_for` around the individual `httpx` call) is what actually bounds a single slow model; the outer `wait_for` around `gather` is a ceiling, not the mechanism that stops one model from blocking the others.
- Set `PER_MODEL_TIMEOUT_SECONDS` below `ROUND_BUDGET_SECONDS` with margin for tally + Telegram reply send (network + MarkdownV2 formatting), not equal to it.

### Pattern 2: Repair-retry-then-abstain as a decision inside the client wrapper, not the orchestrator

**What:** Malformed JSON triggers exactly one retry with a "fix your JSON" nudge; a second failure converts that model's slot into an explicit abstain rather than an exception or a missing row.

**When to use:** Any LLM-JSON-contract system where you cannot fully trust structured output compliance, especially across models from different labs with different JSON-mode reliability.

**Trade-offs:** Doing the retry inside `call_one_model` (Pattern 1) rather than as a separate orchestrator-level pass keeps `run_round` simple (always exactly one round-trip per model conceptually) at the cost of variable per-model latency — which is already accounted for by the per-model timeout.

### Pattern 3: Perceptual-hash cache as a read-through gate in front of the orchestrator, not inside it

**What:** Compute the phash before touching the orchestrator at all. On hit, skip `run_round` entirely and reuse the stored six attempts + tally. On miss, run the round, then persist a new `questions` row keyed by the phash.

**When to use:** Whenever the identical input (bit-similar image) is likely to recur — here, students re-photographing the same practice question, or forwarding it to each other.

**Trade-offs:** Perceptual hash tolerates minor compression/crop differences (which is the point — Telegram photo compression is the dominant failure mode called out in PROJECT.md), but that same tolerance means near-duplicate-but-different questions could theoretically collide. Use a documented Hamming-distance threshold (not exact match) and store the phash as an indexed column so lookup stays O(log n) via a normal SQLite index — no need for a specialized index structure at this scale (tens of students, low thousands of questions).

```python
# images/extract.py
import imagehash
from PIL import Image
import io

def compute_phash(image_bytes: bytes) -> str:
    return str(imagehash.phash(Image.open(io.BytesIO(image_bytes))))

# db/questions.py
async def find_cached(conn, phash: str, max_distance: int = 4) -> QuestionRow | None:
    # SQLite has no native Hamming distance; simplest correct approach at this scale
    # is exact-match on phash first (handles the common "same image resent" case),
    # falling back to a small in-Python scan over recent phashes only if you need
    # fuzzy matching later. Do not build a fuzzy index for a 10-40 user bot.
    row = await conn.execute_fetchone(
        "SELECT * FROM questions WHERE phash = ? LIMIT 1", (phash,)
    )
    return QuestionRow(**row) if row else None
```

**Recommendation:** ship exact-phash-match caching in the first pass; defer Hamming-distance fuzzy matching entirely. Exact match already captures "same photo re-sent," the dominant real case, and avoids a whole class of "why did it cache-hit on a different question" bug reports.

## Data Flow

### Request Flow

```
Telegram photo/document update
    ↓
handlers/ingest.py: extract largest PhotoSize or document bytes
    ↓
images/extract.py: compute_phash(bytes)
    ↓
db/questions.py: find_cached(phash)
    │
    ├─ HIT ──────────────────────────────────────────────┐
    │                                                     ↓
    │                                     db/attempts.py: load six stored attempts
    │                                                     ↓
    │                                     formatting/reply.py: build reply from stored tally
    │                                                     ↓
    │                                     send reply (no new inference, no new cost)
    │
    └─ MISS
        ↓
    cost/guard.py: check_daily_cap() → full 6-model set OR degraded subset
        ↓
    orchestrator/fanout.py: run_round(models, image_bytes, prompt)
        │
        ├─ per model: orchestrator/client.py: call_model() [httpx → OpenRouter]
        │       ├─ success + valid JSON → AttemptResult.ok
        │       ├─ timeout / HTTP error → AttemptResult.abstain("transport_error")
        │       ├─ invalid JSON → one repair retry
        │       │       ├─ repair succeeds → AttemptResult.ok
        │       │       └─ repair fails/times out → AttemptResult.abstain("unparseable")
        ↓
    six AttemptResult objects (some ok, some abstain)
        ↓
    orchestrator/consensus.py: tally() → vote counts, confidence tier, abstain count
        ↓
    db/questions.py: insert questions row (phash, image ref, type, is_sat_verbal)
    db/attempts.py: insert six attempts rows (model, verdict, reasoning, tokens, cost, latency, error)
        ↓
    formatting/reply.py: build_reply_text(tally) + build_keyboard()
        ↓
    send reply to user (MarkdownV2, spoiler around final letter)
```

### Failure Branches (explicit)

| Failure point | Detection | Handling | User-visible effect |
|---|---|---|---|
| Non-SAT-verbal image | `is_sat_verbal` flag in every model's own JSON response — **not** a separate classification call | If the majority of *non-abstaining* models flag `is_sat_verbal: false`, short-circuit to a rejection reply before persisting an `attempts` row per PROJECT.md contract | "This doesn't look like an SAT verbal question" |
| Single model timeout | `asyncio.wait_for` in `call_one_model` | That model's slot becomes `AttemptResult.abstain("transport_error")`; round continues | Reflected only in "Full breakdown"; header tally treats it as an abstain |
| Single model malformed JSON | `pydantic.ValidationError` on parse | One repair retry, then abstain | Same as above |
| Entire round exceeds 30s | Outer `asyncio.wait_for(gather(...), timeout=30)` | Any still-pending tasks cancelled; unfinished models forced to abstain; round always returns | Reply sent late-ish but always sent; degraded confidence noted if ≥2 abstains |
| Daily global spend cap exceeded | `cost/guard.py` checked *before* firing, using `db/attempts.py` cost sum for today | Swap in degraded cheaper model subset from `models.yaml`; note this in the reply text | Reply includes a line like "using reduced model set due to daily budget" |
| OpenRouter model ID doesn't exist / no image support | `validation/boot.py` at process start | Process exits nonzero with the offending model ID named in the log line | Bot never starts; visible only in `docker compose logs` / restart-loop |
| Lab diversity < 4 at boot | `validation/boot.py` at process start | Same as above — fail loudly, name the labs present | Same as above |
| Non-allowlisted user | `middleware/allowlist.py` | Silent ignore or polite rejection, no DB write, no model calls | "You're not authorized to use this bot" (or configurable silence) |
| Per-user daily cap exceeded | `middleware/rate_limit.py`, reads `attempts` count for user+day | Reject before orchestrator is invoked — zero cost incurred | "You've hit today's question limit" |

## Scaling Considerations

Given the fixed scope (10-40 allowlisted students, single VPS, no growth ambitions stated in PROJECT.md), classic scaling tables don't apply. What matters instead is **concurrency correctness at small N**, not throughput at large N.

| Concern | At current scale (10-40 users) | If it somehow grew (100s of users) |
|---|---|---|
| SQLite writes | Single shared `aiosqlite` connection with WAL mode; writes serialize naturally, never a bottleneck at this question rate | Would need a write queue or move to Postgres — not needed now, don't build for it |
| OpenRouter concurrency | 6 calls per question, questions arrive one at a time in practice for a study group | httpx connection pooling (default `AsyncClient` limits) would need tuning; still not urgent |
| Telegram long-polling vs webhook | Long-polling is simplest for single-VPS Docker Compose, no public HTTPS endpoint required | Webhook would reduce latency slightly but adds reverse-proxy/TLS complexity — not worth it here |

### Scaling Priorities

1. **Not a bottleneck concern for this project.** The realistic ceiling is "several students photograph questions during a study session," well within what a single shared SQLite connection and six parallel httpx calls handle without any special design.
2. **The actual constraint is the 30-second latency budget per question**, driven by the slowest of six models, not by concurrent user load. Architecture should optimize for *bounding worst-case single-round latency* (Pattern 1), not for horizontal scale.

## Anti-Patterns

### Anti-Pattern 1: Letting `asyncio.gather()` without `return_exceptions=True` (or without internal try/except) fail the whole round on one model's error

**What people do:** `results = await asyncio.gather(*[call(m) for m in models])` with no exception handling anywhere.
**Why it's wrong:** The first model to raise (timeout, HTTP 5xx, connection reset) cancels the entire gather from the caller's perspective — one flaky model takes down all six, defeating the entire point of an ensemble that's supposed to tolerate per-model failure.
**Instead:** Catch inside each per-model coroutine (Pattern 1) so nothing ever escapes to `gather`; use `return_exceptions=True` only as a defensive backstop, never as the primary error-handling strategy.

### Anti-Pattern 2: A separate polling/classification pre-pass to check `is_sat_verbal` before running the ensemble

**What people do:** Add a "router" LLM call that classifies the image first, then only fans out to the six models if it passes.
**Why it's wrong:** Doubles latency (adds a whole extra round-trip against the 30s budget) and adds a seventh model whose failure modes now need separate handling — for a check that the six ensemble models can answer as a field in their existing structured JSON output at zero extra cost. This is also explicitly what PROJECT.md's Key Decisions log rejected in spirit (no cascade, no extra tiers).
**Instead:** Bake `is_sat_verbal` into the same JSON contract every model already returns; derive the rejection decision from the tally of that field across the six real responses.

### Anti-Pattern 3: Per-request SQLite connections

**What people do:** `async with aiosqlite.connect(db_path) as conn:` inside every handler or every DB helper function.
**Why it's wrong:** SQLite is single-writer; opening a fresh connection per request adds needless connect/pragma overhead and increases the chance of "database is locked" errors under any concurrent write, especially without WAL mode being reliably set per-connection.
**Instead:** Open one `aiosqlite.Connection` at process start, store it on the aiogram `Dispatcher`'s workflow data (or a module-level singleton), set `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON` once, and pass/inject that single connection everywhere. This matches aiosqlite's own internal model (one connection = one serializing background thread), so a single shared connection is not a false economy — it's the grain the library is built for.

### Anti-Pattern 4: Validating models.yaml only against local YAML schema, skipping the live OpenRouter check

**What people do:** Use pydantic to validate `models.yaml` shape (strings, required fields) and call it "boot validation."
**Why it's wrong:** PROJECT.md explicitly flags model ID drift as a known risk — "several may not exist under the exact strings specified." Shape validation alone would let the bot start, then fail on the very first real question when OpenRouter 404s on a stale model ID, which is a worse failure mode than refusing to boot.
**Instead:** After shape validation, call `GET https://openrouter.ai/api/v1/models` once at startup, build a lookup by ID, and assert every configured ID is present *and* its `architecture.input_modalities` (or equivalent field — verify exact key against a live response during implementation) includes `"image"`. Fail the process with the specific offending ID(s) named in the exception message, not a generic "config invalid."

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Telegram Bot API | `aiogram.Bot` + long-polling `Dispatcher.start_polling` | No public HTTPS needed; simplest fit for single-VPS Docker Compose with no reverse proxy required |
| OpenRouter (chat completions) | Direct `httpx.AsyncClient` POST to `/api/v1/chat/completions`, OpenAI-compatible schema, one API key | Response includes per-request `usage` (prompt/completion tokens) — this is the hook point for cost accounting per attempt; verify the exact cost field (`usage.cost` or compute from token counts × `models.yaml` price) against a live response in Phase 1 |
| OpenRouter (`/models` listing) | Single `GET` at boot, no auth required for the public listing endpoint per OpenRouter docs | Used only for boot-time ID + modality validation, not called per-request — cache nothing, it's a one-shot startup check |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| handlers ↔ orchestrator | Direct async function call (`await run_round(...)`) | No queue, no event bus — synchronous-looking await chain is correct at this scale and matches "no orchestration framework" constraint |
| orchestrator ↔ db | Orchestrator calls `db/*.py` functions to persist; never holds SQL itself | Keeps SQL centralized for the eventual migration/eval-harness work deferred to v2 |
| orchestrator ↔ cost guard | `fanout.py` calls `cost/guard.check_daily_cap()` before building the model list, and `client.py` reports token usage back for `db/attempts.py` to log after each call | Cap check must happen before firing calls, not after, or the cap can be exceeded by the round already in flight |
| handlers ↔ formatting | Handler calls `formatting/reply.py` pure functions, then does the actual `message.answer(...)` / `message.edit_text(...)` itself | Keeps `formatting/` free of any aiogram/Telegram-object dependency, so it's independently testable |

## Build Order (dependency-ordered, tuned for a 2-3 phase roadmap)

**Phase-independent, buildable in parallel from day one** (no dependency on each other or on live credentials):
- `orchestrator/contract.py` (pydantic JSON contract) — pure typing, can be written and unit-tested against fixture JSON before any real model call exists
- `orchestrator/consensus.py` (tally logic) — pure function, unit-testable against hand-written `AttemptResult` fixtures
- `images/extract.py` (phash) — pure function, testable against any local image file
- `db/schema.sql` + `db/connection.py` — schema is already fixed in PROJECT.md, no upstream dependency
- `formatting/reply.py` — pure function once `consensus.py`'s output shape is agreed, testable against fixture tallies

**Hard dependency chain** (must exist in this order before the next link works end-to-end):
1. **Credentials + `config.py`** (OpenRouter key, bot token, `models.yaml` parsed) — nothing else can run without this
2. **`validation/boot.py`** — depends on (1); must pass before the bot is allowed to serve traffic at all, since it's the gate against model ID drift and lab-diversity violation called out as top risks in PROJECT.md
3. **`orchestrator/client.py`** (single real OpenRouter call) — depends on (1); this is the highest-uncertainty piece (real latency, real JSON compliance per model) and should be proven with one model before wiring all six
4. **`orchestrator/fanout.py`** (six-way gather + timeout budget) — depends on (3) working for at least one model, plus `contract.py` and `consensus.py` already existing
5. **`handlers/ingest.py`** (Telegram photo → orchestrator → reply) — depends on (4), `images/extract.py`, `db/questions.py`, `db/attempts.py`, `formatting/reply.py` all being wired together
6. **Cache short-circuit** (`db/questions.py: find_cached`) — depends on (5) already working end-to-end without cache, since caching is an optimization layer on top of a working round, not a prerequisite for one
7. **Cost accounting + degraded mode** (`cost/guard.py`) — depends on (4) emitting real token/cost data per attempt, since the cap check needs real cost numbers to compare against
8. **Buttons, `/cost`, `/adduser`, allowlist middleware** — depend on (5) and a populated `attempts`/`users` schema, but are otherwise independent of each other and can be built in any order once the core round works

**Suggested 2-3 phase grouping**, matching PROJECT.md's stated preference for minimal phases and the Context section's call-out that latency risk "wants research before Phase 1 planning":

- **Phase 1 — Prove the core round.** Credentials, `config.py`, `validation/boot.py`, `client.py` (single model), `fanout.py` (all six), `contract.py`, `consensus.py`, minimal `handlers/ingest.py` and `formatting/reply.py`, bare persistence writes. Goal: one photo in, one correct six-model tallied reply out, within 30s, with per-model failure isolation proven. This phase absorbs essentially all of the technical risk (latency, JSON compliance, boot validation, lab diversity) called out in PROJECT.md.
- **Phase 2 — Persistence depth, caching, cost control, access control.** Full `questions`/`attempts`/`users` schema usage, phash cache short-circuit, `cost/guard.py` + degraded mode, allowlist + per-user daily cap middleware, `/cost` and `/adduser`.
- **Phase 3 (if needed) — Interaction polish.** "Full breakdown" and "Wrong answer" inline buttons, typing-action indicator, MarkdownV2 spoiler formatting refinement, any remaining reply-format nuance (4/2 vs 3/3 wording, etc.). This phase is mostly UI/reply-text work with no new architectural risk — could plausibly be folded into Phase 2 if the roadmap wants exactly 2 phases.

## Sources

- [aiogram Router documentation (dev-3.x)](https://docs.aiogram.dev/en/dev-3.x/dispatcher/router.html) — router/handler structure, confirmed current
- [aiogram 3.x guide: routers, multi-file structure](https://mastergroosha.github.io/aiogram-3-guide/routers/) — community-standard project layout, cross-checked against official docs
- [aiosqlite documentation](https://aiosqlite.omnilib.dev/) — single shared-thread-per-connection model, confirms single-connection pattern is correct, not a workaround
- [SQLite WAL mode concurrency limits (Sling Academy)](https://www.slingacademy.com/article/concurrency-challenges-in-sqlite-and-how-to-overcome-them/) — confirms WAL decouples reads from writes but does not enable concurrent writers; single-writer assumption in this architecture is correct
- [Waiting in asyncio (hynek.me)](https://hynek.me/articles/waiting-in-asyncio/) and [Asyncio gather() Handle Exceptions (SuperFastPython)](https://superfastpython.com/asyncio-gather-exception/) — confirm `return_exceptions=True` semantics and the wrap-with-`wait_for` timeout pattern used in Pattern 1
- [OpenRouter Models overview](https://openrouter.ai/docs/guides/overview/models) and [OpenRouter Unified Image API announcement](https://openrouter.ai/blog/announcements/image-api/) — confirm `/models` listing returns `input_modalities`/capability fields usable for boot-time image-support validation; exact JSON key should be spot-checked live during Phase 1 since blog/docs phrasing varies slightly across OpenRouter's own pages (MEDIUM confidence on exact field name only)
- `.planning/PROJECT.md` — locked stack, schema, constraints, and risk log this architecture is derived from

---
*Architecture research for: single-VPS Dockerized aiogram 3.x + OpenRouter parallel-vision-LLM-ensemble Telegram bot*
*Researched: 2026-09-10*
