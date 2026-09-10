# Stack Research

**Domain:** Async Python Telegram bot fanning one image out to six vision LLMs via OpenRouter, strict JSON contract, SQLite persistence
**Researched:** 2026-09-10
**Confidence:** HIGH on library versions and OpenRouter mechanics (live-verified); MEDIUM on latency/cost figures (derived from Artificial Analysis third-party benchmarks + OpenRouter live pricing, not a benchmark run of this exact prompt shape)

## Highest-Value Finding #1: OpenRouter Model ID Verdicts

Checked live against `GET https://openrouter.ai/api/v1/models` (436 models, fetched 2026-09-10). Every configured ID was checked for existence AND for `image` in `architecture.input_modalities`.

| Configured ID | Verdict | Correct ID to use | Vision? | Notes |
|---|---|---|---|---|
| `anthropic/claude-opus-5` | **EXISTS** | `anthropic/claude-opus-5` | Yes (`text`, `image`, `file`) | Exact string is correct as configured. 1M context, $5/M in, $25/M out. |
| `anthropic/claude-sonnet-5` | **EXISTS** | `anthropic/claude-sonnet-5` | Yes (`text`, `image`, `file`) | Exact string is correct as configured. 1M context, $2/M in, $10/M out. |
| `openai/gpt-6-astra` | **EXISTS** | `openai/gpt-6-astra` | Yes (`file`, `image`, `text`) | Exact string is correct as configured. $10/M in, $50/M out (below 272k-token tier; doubles above it). |
| `openai/gpt-5.6-sol` | **EXISTS** | `openai/gpt-5.6-sol` | Yes (`file`, `image`, `text`) | Exact string is correct as configured. $2/M in, $10/M out (below 272k-token tier). |
| `google/gemini-3.7-flash` | **EXISTS** | `google/gemini-3.7-flash` | Yes (`text`, `image`, `video`, `file`, `audio`) | Exact string is correct as configured. $0.75/M in, $3.75/M out — cheapest of the five verified frontier IDs. |
| `deepseek/deepseek-v4` | **DOES NOT EXIST** | `deepseek/deepseek-v4.1-flash` | Yes (`text`, `image`) | See below. |

**Confidence: HIGH** — verified directly against the live catalog response, not training data or search results.

### DeepSeek substitution: does DeepSeek ship a vision model on OpenRouter?

Yes, but not under the bare `deepseek-v4` string, and not as the primary (largest) model in the family. As of this research date, DeepSeek's V4-generation lineup on OpenRouter is text-only by default:

- `deepseek/deepseek-v4-pro`, `deepseek/deepseek-v4-pro-0813`, `deepseek/deepseek-v4-flash`, `deepseek/deepseek-v4-flash-0731` — all **text-only** (`input_modalities: ['text']`).
- `deepseek/deepseek-v4-flash-vision-exp` — vision-capable, but explicitly labeled **experimental**, described as "an experimental vision-enabled version of DeepSeek V4 Flash 0731."
- `deepseek/deepseek-v4.1-flash` — vision-capable (`text`, `image`), **not** tagged experimental, described by DeepSeek as exceeding V4 Pro "on performance, speed, and task" — this is the newer, more stable release.

**Recommendation: `deepseek/deepseek-v4.1-flash`.** Prefer it over `deepseek-v4-flash-vision-exp` because "-exp" suffixed OpenRouter listings are routinely deprecated/withdrawn without notice, which is a bad property for a boot-time-validated model roster that must not silently disappear. `v4.1-flash` is also the cheapest of all six models by a wide margin ($0.15-0.30/M in, $0.60-1.20/M out, with day/hour-of-week pricing tiers) and supports `structured_outputs`.

**Confidence: HIGH** on existence/modality (live catalog). **MEDIUM** on "exp tags get deprecated" being the deciding factor — that is an OpenRouter ecosystem pattern observed generally, not a documented guarantee for this specific listing.

### All six final IDs support structured outputs

Verified `supported_parameters` for the final six live in the catalog — every one includes both `response_format` and `structured_outputs`:

```
anthropic/claude-opus-5        -> response_format, structured_outputs  (+ reasoning, reasoning_effort)
anthropic/claude-sonnet-5      -> response_format, structured_outputs  (+ reasoning, reasoning_effort)
openai/gpt-6-astra             -> response_format, structured_outputs  (+ reasoning, reasoning_effort)
openai/gpt-5.6-sol             -> response_format, structured_outputs  (+ reasoning, reasoning_effort)
google/gemini-3.7-flash        -> response_format, structured_outputs  (+ reasoning, reasoning_effort)
deepseek/deepseek-v4.1-flash   -> response_format, structured_outputs  (+ reasoning, reasoning_effort)
```

All six are also **reasoning-capable models with a variable effort dial** — this is the single most important fact for hitting the 30s budget (see Finding #2).

## Highest-Value Finding #2: Latency & Cost for Six Parallel Vision Calls

### The 30-second budget is achievable, but only if reasoning effort is forced low on every call. Left at defaults it is not achievable.

All six candidate models are 2026-generation reasoning models with a controllable "thinking" dial. Per OpenRouter's reasoning-tokens documentation, the request-level knob is:

```json
{
  "reasoning": {
    "effort": "low"      // OpenAI / Google models: "none" | "minimal" | "low" | "medium" | "high" | "max"/"xhigh"
  }
}
```

Anthropic models (Opus 5, Sonnet 5) do **not** use `effort` strings — they take `reasoning.max_tokens` directly, with a **documented minimum of 1024 tokens** once extended thinking is enabled. If your 2000-token completion cap must hold transcription + 4 elimination verdicts + a final letter, reserving 1024 tokens to thinking leaves ~1000 for the actual answer — tight but workable. The safer move for latency is to leave Anthropic's `reasoning` field entirely unset (thinking off) rather than set a minimal budget, since Opus 5/Sonnet 5 with thinking disabled behave like conventional non-reasoning single-pass models.

Third-party independent benchmarks (Artificial Analysis, cross-checked against provider self-reported numbers, MEDIUM confidence — these are general-purpose text benchmarks, not vision+long-output specific) show just how large the effort-level swing is:

| Model | TTFT, low/min effort | TTFT, high/max effort | Output speed (low effort) |
|---|---|---|---|
| Claude Opus 5 | 2.67s | 44.75s | ~50.8 tok/s |
| Claude Sonnet 5 | 1.38s (Anthropic first-party); independent bench 1.7s | 182.6s (max) | 60-230 tok/s (wide provider variance) |
| GPT-6 Astra | 2.69s | not directly measured — GPT-5.6 Sol's max-effort figure (131s) is the closest analog in the same family | up to 54 tok/s |
| GPT-5.6 Sol | 2.47s (low), 4.58s (medium) | 16.31s (high), 131.3s (max) | not separately reported |
| Gemini 3.7 Flash | 0.74s (low effort) | 8.9-9.83s median (high), p95 49.5s | 292.5 tok/s (high effort) |
| DeepSeek V4 Flash family | ~1.1-1.9s TTFT | not applicable (non-reasoning-heavy tier) | ~103-120 tok/s |

**Reading these numbers for this workload:** at forced low/minimal effort, TTFT across all six sits in the 0.7-2.7s range. The dominant cost is then generation time for however many completion tokens the model actually emits. For an SAT R&W question (100-180 word passage, 4 short answer choices, an elimination verdict per choice), a well-behaved response is realistically **600-1200 completion tokens**, not the full 2000-token cap. At the slowest observed low-effort throughput in this list (Opus 5, ~50 tok/s), 1200 tokens takes ~24s of pure generation, plus ~3s TTFT = **~27s** — inside budget but with very little margin. At worse throughput or if a model ignores the effort hint and reasons anyway, it blows straight through 30s (the high/max-effort TTFT figures alone — 16s, 44s, 131s — make that failure mode concrete and severe).

**Verdict: 30s end-to-end for all six is achievable only with all of the following mitigations in place simultaneously:**

1. **Force minimal/no reasoning on every request.** `reasoning.effort: "none"` or `"minimal"` for OpenAI/Google/DeepSeek; omit `reasoning` entirely for Anthropic (do not enable extended thinking at all). This is not optional — it is the difference between ~2s and ~45-130s of TTFT alone.
2. **Cap `max_tokens` below 2000 if quality holds.** 1200-1400 is likely sufficient for transcription + 4 verdicts + letter; test empirically, but do not default to 2000 for every model — it only raises the ceiling on how long a verbose model can run.
3. **Per-model hard timeout with abstention, not a global one.** Wrap each `httpx` call in `asyncio.wait_for(..., timeout=25)` (leaving ~5s headroom inside a 30s wall-clock budget for image encode + tally + Telegram round trip). A model that times out abstains for that question rather than blocking the other five — this is already the product's stated design (one repair retry, then abstain), so the mechanism is reused, not new.
4. **`asyncio.gather` with `return_exceptions=True`**, never sequential awaits — six calls must be concurrent, not summed.
5. **Streaming is not a latency fix here and should not be used for this feature.** Streaming reduces perceived TTFT but does not reduce total generation time, and this workload requires the complete, valid JSON object before it can be parsed/validated — there is nothing useful to show the user mid-stream. Skip it; it adds complexity (SSE parsing, partial-JSON handling) for no benefit against a hard total-latency budget.
6. **Prompt trimming helps marginally, not decisively.** Image tokens (the passage/choices as pixels) dominate input cost far more than a lean vs. verbose system prompt. Trimming instructions saves cost, not much wall-clock time, since TTFT is reasoning-effort-driven, not input-length-driven, for these models.

**Confidence: MEDIUM.** The mitigations and mechanism (reasoning effort → TTFT) are HIGH confidence (directly from OpenRouter's own docs). The specific 24-27s worked example is MEDIUM — it interpolates third-party general-benchmark throughput numbers onto an estimated (not measured) completion-token count for this exact prompt shape. Recommend an early Phase 1 spike that fires all six models once with the real prompt and logs actual `usage.completion_tokens` and wall-clock time before committing to a 2000 (or any) max_tokens value.

### Cost per question (all six fired)

Using live OpenRouter pricing and an estimated 2500 input tokens (image + system + passage instructions) / 1200 output tokens per model:

| Model | Input cost | Output cost | Total |
|---|---|---|---|
| Claude Opus 5 | $0.0125 | $0.0300 | **$0.0425** |
| Claude Sonnet 5 | $0.0050 | $0.0120 | **$0.0170** |
| GPT-6 Astra | $0.0250 | $0.0600 | **$0.0850** |
| GPT-5.6 Sol | $0.0050 | $0.0120 | **$0.0170** |
| Gemini 3.7 Flash | $0.0019 | $0.0045 | **$0.0064** |
| DeepSeek V4.1 Flash | $0.0004-0.0008 | $0.0007-0.0014 | **$0.0011-0.0022** |
| **Total per question** | | | **≈ $0.17** |

At the stated per-user daily cap of 40 questions and a 10-40 person study group, a single heavy day (40 users x 40 questions, unrealistic ceiling) would be ~$272; realistic usage (a handful of questions per active user per day) is more like $1-5/day. GPT-6 Astra alone is roughly half the per-question spend — it is the natural first model to drop in the "reduced cheaper model set" degraded mode described in the spend-cap requirement.

**Confidence: MEDIUM** — pricing is live-verified (HIGH), token-count assumptions are estimated (MEDIUM), so treat the total as directionally correct, not exact. Log real `usage.cost` (OpenRouter returns this per-response, see below) from the first real questions and recalibrate.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 | Runtime | Locked constraint. Current aiogram/httpx/pydantic all target 3.10-3.13; 3.12 is inside every library's supported range. |
| aiogram | 3.31.0 | Telegram bot framework | Latest on PyPI as of this research. Requires `pydantic>=2.4.1,<2.14` — this pins your pydantic ceiling (see Version Compatibility). Fully async, native `ChatActionSender`, native `Formatting`/entity-based MarkdownV2 helpers. |
| httpx | 0.28.1 | Async HTTP client for OpenRouter calls | Locked constraint. Native `async`/`await`, connection pooling, per-request timeout control — exactly what fan-out to 6 endpoints needs. Use `httpx.AsyncClient` with a shared connection pool across the 6 calls, not 6 fresh clients. |
| aiosqlite | 0.22.1 | Async SQLite persistence | Locked constraint. Thin async wrapper over stdlib `sqlite3` running in a thread executor — see concurrency caveats below. |
| pydantic | 2.13.5 (but pin `<2.14,>=2.4.1` for aiogram compat) | JSON contract validation | Locked constraint. v2's `model_validate_json` + `ValidationError.errors()` is the natural fit for "parse, and on failure, feed the errors back to the model for one repair retry." |
| imagehash | 4.3.2 | Perceptual hash cache key | Locked constraint. See dedicated section below for hash function choice. |
| Ruff | 0.16.6 | Lint + format | Locked constraint. Single tool replaces flake8+isort+black; fast enough to run as a pre-commit/CI gate on every diff. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Pillow | 12.3.0 | Image decode for imagehash, JPEG re-encode before base64 | `imagehash` requires a `PIL.Image`, so this is a hard transitive need even though not explicitly locked. Also useful to downscale/re-encode oversized Telegram photos before base64-encoding for OpenRouter (smaller payload, same enough resolution for OCR). |
| python-dotenv | 1.2.3 | Load `.env` in local dev | Constraint requires secrets from env only; dotenv is the standard way to populate `os.environ` locally without leaking into the Docker image. In the container, rely on `docker-compose`'s `env_file:`/`environment:` instead of dotenv loading at runtime. |
| pydantic-settings | latest (2.x, track pydantic core version) | Typed env-var loading | Optional but recommended: gives you a typed, validated `Settings` object (model IDs, caps, allowlist) instead of raw `os.getenv` scattered through the codebase. Not in the locked list — flag as a suggestion, not a requirement. |
| tenacity | latest (9.x) | Retry/backoff for the OpenRouter repair-retry and 429/5xx handling | Not locked, but implementing exponential backoff with jitter by hand for "retry once on 429, honor `Retry-After`" is exactly tenacity's job and keeps the httpx call sites small. Optional — a 5-line manual retry is also fine given "no orchestration framework" spirit; use judgment. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Ruff | Lint + format | Configure `line-length`, `target-version = "py312"`, enable `I` (isort) and `UP` (pyupgrade) rule sets at minimum. |
| mypy or Pyright | Static type checking | Not explicitly locked, but "full type hints" as a constraint is toothless without a checker enforcing it in CI. Pyright is faster and has better async/Protocol inference; mypy has better pydantic plugin support. Either is reasonable — flag as a decision for Phase 1 setup. |

## Installation

```bash
# Core (locked stack)
pip install "aiogram==3.31.0" "httpx==0.28.1" "aiosqlite==0.22.1" \
            "pydantic>=2.4.1,<2.14" "ImageHash==4.3.2" "Pillow==12.3.0"

# Supporting
pip install python-dotenv tenacity

# Dev dependencies
pip install ruff pyright
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| `deepseek/deepseek-v4.1-flash` as 4th-lab vision model | `deepseek/deepseek-v4-flash-vision-exp` | Only if v4.1-flash is ever pulled from the catalog or fails boot-time validation — it is the fallback, not the primary, because "-exp" listings churn. |
| `httpx.AsyncClient` shared across all 6 calls | 6 independent `httpx.AsyncClient` instances | Never for this project — shared client reuses the connection pool and avoids 6x TLS handshake overhead per question. |
| No streaming (`stream: false`) | SSE streaming (`stream: true`) | Only if a future feature needs to show live per-model progress in the Telegram UI; not useful for the "wait for valid JSON, then tally" flow this bot has. |
| `reasoning.effort: "none"/"minimal"` forced on every call | Default (unset) reasoning | Never for this project at the current 30s budget — default effort risks 16-130s TTFT on the reasoning-heavy models per the benchmarks above. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| LangChain / LlamaIndex / any agent framework | Explicitly out of scope per project constraints; six direct, identical, parallel calls to one OpenAI-compatible endpoint is not an orchestration problem — it's an `asyncio.gather` problem. | Direct `httpx` calls against `https://openrouter.ai/api/v1/chat/completions`. |
| `requests` (sync) for OpenRouter calls | Blocks the event loop; would force 6 sequential calls or a thread pool workaround, defeating the point of async fan-out. | `httpx.AsyncClient`. |
| `sqlite3` used directly from async handlers without `aiosqlite` | Blocks the event loop on every query; fine for true single-writer scripts, wrong for a bot serving concurrent Telegram updates. | `aiosqlite`, with WAL mode enabled (see below). |
| Bare `dict` fed straight to `response_format: {"type": "json_object"}` | OpenRouter's plain `"json"`/`"json_object"` mode (if a model accepts it at all) does not enforce field-level schema — it just guarantees syntactically valid JSON, not your contract's shape. Some providers behind OpenRouter may not support even that. | `response_format: {"type": "json_schema", "json_schema": {...}, "strict": true}` generated from the pydantic model via `model_json_schema()`, with the understanding that `strict: true` is "provider-dependent, not a hard guarantee" per OpenRouter's own docs — validate the response with pydantic regardless of what you asked for. |
| Trusting `strict: true` alone as your validation layer | OpenRouter's docs state explicitly that schema enforcement varies by provider — some "translate your schema into their own format or treat it as a strong hint." A model can return well-formed JSON that doesn't match your schema. | Always run the response through `YourModel.model_validate_json(...)` and catch `pydantic.ValidationError`; that's your actual contract enforcement, `response_format` is just a hint that improves the odds. |
| Default (full) `ahash` hash_size=8 for the perceptual cache key on text-heavy SAT question photos | SAT R&W questions share a near-identical visual template (boxed passage block + 4 lettered choices) across hundreds of *different* questions. A coarse 64-bit hash has too little discriminative power on this template-heavy content and risks false-positive cache hits — returning a cached result for the *wrong* question, which directly violates the "never confidently wrong" core value. | `imagehash.phash(img, hash_size=16)` (256-bit hash) — see dedicated section below. |
| Global request timeout shared across all 6 `httpx` calls (e.g., one `asyncio.wait_for` wrapping the whole `gather`) | One slow/stuck model (a reasoning model that ignored the effort hint) drags down or kills the entire batch, including the 5 models that already finished. | Per-call `asyncio.wait_for(call_model(...), timeout=25)` inside the `gather`, so a straggler abstains without affecting its siblings. |

## Stack Patterns by Variant

**Image ingestion — Telegram photo vs. document:**
```python
from aiogram import types

async def get_image_bytes(message: types.Message) -> bytes:
    if message.photo:
        # Telegram re-compresses photos; largest PhotoSize is last in the list
        file = message.photo[-1]
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        file = message.document  # raw bytes, no Telegram re-compression
    else:
        raise ValueError("no image in message")
    buf = await message.bot.download(file.file_id)  # returns io.BytesIO by default
    return buf.read()
```
Tell users to prefer document upload (per your own requirement) precisely because `message.photo` sizes are Telegram-recompressed JPEGs — the largest `PhotoSize` is still lossier than the original the user took.

**Typing indicator during inference:**
```python
from aiogram.utils.chat_action import ChatActionSender

async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
    results = await asyncio.gather(*(call_model(m, image_bytes) for m in MODEL_IDS), return_exceptions=True)
```
`ChatActionSender` runs a background loop re-sending the `typing` action every ~5s (Telegram actions expire after ~5s) for the duration of the `async with` block — exactly matches "typing action displayed while inference runs."

**MarkdownV2 spoiler for the consensus letter — use the `Formatting` module, not hand-escaped strings:**
```python
from aiogram.utils.formatting import Text, Spoiler, Bold

content = Text(Bold("Consensus: "), Spoiler("B"))
await message.answer(**content.as_kwargs())  # handles entities + escaping together
```
MarkdownV2 has 18 characters (`_ * [ ] ( ) ~ \` > # + - = | { } . !`) that must be backslash-escaped outside formatting markers — including inside spoiler text itself. Hand-escaping is the single most common aiogram bug report (unescaped `.`/`-`/`!` in model-generated reasoning text breaks the whole message with a `can't parse entities` 400 from Telegram). Building the message via `Text`/`Spoiler`/`Bold` and calling `.as_kwargs()` sidesteps manual escaping entirely — since model output is untrusted/arbitrary text, this matters more here than in a typical bot.

**Inline keyboard with callback data:**
```python
from aiogram.utils.keyboard import InlineKeyboardBuilder

kb = InlineKeyboardBuilder()
kb.button(text="Full breakdown", callback_data=f"breakdown:{question_id}")
kb.button(text="Wrong answer", callback_data=f"correct:{question_id}")
await message.answer("...", reply_markup=kb.as_markup())
```
Telegram caps `callback_data` at 64 bytes — pass IDs, not payloads; look up the question/attempt row from SQLite in the callback handler.

**OpenRouter request shape (per model call):**
```python
payload = {
    "model": model_id,
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": USER_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
        ]},
    ],
    "response_format": {"type": "json_schema", "json_schema": {"name": "verdict", "strict": True, "schema": VerdictModel.model_json_schema()}},
    "max_tokens": 1200,
    "reasoning": {"effort": "minimal"},  # omit entirely for Anthropic models; see Finding #2
}
```
Use base64 data URLs (`data:image/jpeg;base64,...`), not hosted URLs — the image is a user-submitted Telegram file with no public URL, so base64 is the only option here (OpenRouter's own docs describe URL-based images as an optimization for *already-hosted* files, not applicable to this flow).

**Pydantic v2 contract + one repair retry:**
```python
from pydantic import BaseModel, ValidationError

class Verdict(BaseModel):
    is_sat_verbal: bool
    passage_transcription: str
    choice_transcriptions: list[str]
    eliminations: list[str]
    answer: str | None

def parse_or_none(raw: str) -> Verdict | None:
    try:
        return Verdict.model_validate_json(raw)
    except ValidationError:
        return None

# call site
verdict = parse_or_none(first_response)
if verdict is None:
    repaired = await call_model(model_id, image_bytes, repair_context=first_response_errors)
    verdict = parse_or_none(repaired)
    if verdict is None:
        verdict = None  # abstain — do not retry a second time
```
Feed the actual `ValidationError.errors()` list back into the repair prompt ("your previous response failed validation: <errors>; return corrected JSON only") rather than just re-asking blind — this measurably improves repair success rate over a bare retry.

**aiosqlite under `asyncio.gather` — the concurrency caveat that bites people:**
SQLite allows only one writer at a time regardless of async wrapper. Six models finishing concurrently and all writing an `attempt` row is a write-contention scenario, not a read scenario. Mitigations:
```python
# On connection open, once, before any concurrent load:
await db.execute("PRAGMA journal_mode=WAL")
await db.execute("PRAGMA busy_timeout=5000")
```
WAL mode allows concurrent readers alongside a single writer and removes most `database is locked` errors under moderate concurrency; `busy_timeout` makes aiosqlite retry-and-wait instead of raising immediately on the rare remaining contention. For this bot's actual write pattern — buffer all six model results in memory, then do one batch `executemany`/transaction after `gather` completes, rather than six independent concurrent writes — contention mostly disappears by construction. Prefer that pattern over writing from inside each parallel call.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| `aiogram==3.31.0` | `pydantic>=2.4.1,<2.14` | **Hard constraint from aiogram's own dependency spec.** Latest standalone pydantic (2.13.5) fits inside this range today, but do not `pip install -U pydantic` blindly in this project — 2.14+ will break aiogram installs until aiogram bumps its ceiling. Pin pydantic explicitly rather than letting it float. |
| `imagehash==4.3.2` | Pillow (any recent 9.x-12.x) | No pinned Pillow requirement upstream; 12.3.0 (current) is fine. |
| `httpx==0.28.1` | Python `>=3.8` | No conflict with 3.12. |
| `aiosqlite==0.22.1` | Python `>=3.9` | No conflict with 3.12. |

## Perceptual Hash Choice for SAT Question Photos

**Recommendation: `imagehash.phash(img, hash_size=16)`, Hamming distance threshold ≤ 8-10 (out of 256 bits) for a cache hit.**

Rationale:
- **pHash (DCT-based) over aHash/dHash:** pHash is the most robust of the four to the exact distortions phone photos introduce — uneven lighting, mild rotation/perspective, JPEG recompression. aHash (mean threshold) is the weakest — it's sensitive to lighting/exposure shifts common in phone photos of a printed page. dHash (gradient-based) is fast and decent for general near-duplicate detection (product photos, screenshots) but less robust than pHash to the lighting variance specific to photographed (not screenshotted) paper.
- **Why `hash_size=16` instead of the library default of 8:** the default produces a 64-bit hash (8x8 DCT block). SAT R&W questions across hundreds of distinct items share the same visual template — a boxed/lined passage followed by 4 lettered choices in the same font and layout. A 64-bit hash has too little entropy to reliably distinguish *content* when *layout* is near-constant across the whole question bank, risking a false-positive cache hit that serves the wrong question's answer — a direct violation of the "never confidently wrong" core value. Doubling to `hash_size=16` (256-bit hash, 16x16 DCT block) retains far more of the actual text/content signal and sharply reduces same-template collisions.
- **Threshold:** could not verify an authoritative published threshold for this specific hash_size/domain combination (no primary source found for "SAT question photo dedup" specifically) — this is a **LOW confidence, needs-validation** figure, extrapolated from the general perceptual-hashing literature's rule of thumb (~3-10% of hash bits as the near-duplicate cutoff) rather than measured against real SAT photos. Treat ≤8-10 (out of 256) as a starting point and tune it empirically in Phase 1/2 against real user-submitted retake photos of the same question — err toward a *tighter* threshold (fewer false cache hits) given the cost asymmetry: a missed cache hit costs one extra inference round (~$0.17, ~25s); a false cache hit silently serves a wrong answer to a different question, which is the exact failure this whole product exists to prevent.

## Docker / docker-compose

Minimal single-VPS layout with a persistent SQLite volume:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "bot"]
```

```yaml
services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - sqlite_data:/app/data   # SQLite file lives at /app/data/bot.db
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  sqlite_data:
```

Key points:
- **Named volume, not a bind mount, for the SQLite file** — avoids host filesystem UID/permission mismatches inside the container; `docker-compose down` (without `-v`) preserves it across redeploys.
- **`restart: unless-stopped`**, not `always` — lets you `docker compose stop` for maintenance without Docker fighting you on restart.
- **No `depends_on`/multi-service orchestration needed** — this is a single-process bot with an embedded database, not a service mesh. Resist the urge to add a separate `db` container; SQLite-in-the-app-container is correct for a 10-40 person tool on one VPS.
- **Long-polling vs. webhook:** nothing in the constraints mandates a webhook, and a single VPS with no reverse proxy already provisioned makes aiogram's built-in long-polling (`dp.start_polling(bot)`) the simpler correct default — no public HTTPS endpoint, no TLS cert management, no webhook signature verification surface. Revisit only if inbound latency from polling becomes a measured problem, which is unlikely at this scale.

## Sources

- `https://openrouter.ai/api/v1/models` — live catalog fetch, 2026-09-10, HIGH confidence, primary source for all model ID/modality/pricing verdicts in this document
- `https://openrouter.ai/docs/features/structured-outputs` — WebFetch, HIGH confidence, response_format/json_schema mechanics and provider-dependent enforcement
- `https://openrouter.ai/docs/api-reference/overview` — WebFetch, HIGH confidence, image input encoding, usage/cost fields
- `https://openrouter.ai/docs/api-reference/limits` — WebFetch, HIGH confidence, rate limit and error code semantics
- `https://openrouter.ai/docs/use-cases/reasoning-tokens` — WebFetch, HIGH confidence, reasoning.effort/reasoning.max_tokens mechanics — this is the load-bearing source for the latency mitigation strategy
- `https://openrouter.ai/docs/features/images-and-pdfs` — WebFetch, partial (detail parameter/token counting not found in fetched excerpt) — MEDIUM confidence, flagged gap
- `https://artificialanalysis.ai/models/{claude-opus-5,claude-sonnet-5,gpt-6-astra,gpt-5-6-sol,gemini-3-7-flash,deepseek-v4-flash}/providers` — WebSearch-surfaced, MEDIUM confidence, third-party independent benchmarks used for the latency table; not a benchmark of this project's exact prompt shape
- PyPI JSON API (`pypi.org/pypi/<package>/json`) for aiogram, httpx, aiosqlite, pydantic, ImageHash, ruff, pillow, python-dotenv — HIGH confidence, live version + `requires_dist` lookup, 2026-09-10
- `https://docs.aiogram.dev/en/latest/utils/formatting.html` — WebFetch, HIGH confidence, Spoiler/Text formatting API
- `https://docs.aiogram.dev/en/latest/utils/chat_action.html` — WebSearch-surfaced doc summary, MEDIUM confidence (not directly WebFetched, but consistent across multiple version-specific doc mirrors)
- General perceptual-hashing literature (aHash/dHash/pHash/wHash comparison articles) — WebSearch, LOW-MEDIUM confidence, no primary source specific to "photographed SAT question dedup" was found; threshold recommendation flagged as needing empirical validation

---
*Stack research for: async Python Telegram bot, six-model OpenRouter vision fan-out, strict JSON contract, SQLite persistence*
*Researched: 2026-09-10*
