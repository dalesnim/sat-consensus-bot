<!-- GSD:project-start source:PROJECT.md -->

## ⚠ MONEY GUARD — read before running anything

The owner's OpenRouter balance is ~$10.32 and each question costs ~$0.247.

**Never run these unattended:** `scripts/model_bakeoff.py`,
`scripts/latency_spike.py`, or any code path that calls `/chat/completions`.
All tests must mock httpx at the transport layer.

`python -m bot --validate-only` is free (public model catalog) and is fine.

See `.planning/OVERNIGHT-HANDOFF.md` for full context, environment gotchas,
and the decisions already locked in.


## Project

**SAT Verbal Consensus Bot**

A Telegram bot for SAT Reading & Writing practice. A user sends a photo of one SAT verbal question; the bot sends that identical image to six independent frontier models in parallel and reports what each of them chose, along with elimination reasoning for all four answer choices. Agreement across independent models is the confidence signal — the bot never claims to know the correct answer, it reports what the models converged on and how strongly.

Built for a study group / class of roughly 10–40 allowlisted students.

**Core Value:** **Honest confidence signaling.** When the models unanimously agree, the user should be able to trust that. When they split, the user must see the split rather than a fabricated single answer. A bot that confidently reports a plausible-sounding wrong answer is worse than no bot.

### Constraints

- **Tech stack**: Python 3.12, aiogram 3.x, httpx (async), aiosqlite, pydantic v2, imagehash, Docker + docker-compose — chosen and fixed; no substitutions without discussion
- **Tech stack**: No LangChain or equivalent orchestration framework — direct OpenRouter calls keep the dependency surface small and the control flow legible
- **Dependencies**: All model calls route through OpenRouter — one API key, one OpenAI-compatible schema, one billing relationship
- **Performance**: 30 second latency budget per question, end to end
- **Deployment**: Single VPS, Docker Compose — no orchestration platform, no managed services
- **Security**: Secrets from env only; `.env.example` shipped, `.env` never committed
- **Security**: Allowlist-only access; no open registration
- **Budget**: Hard global daily spend cap enforced in code, with a degraded cheaper-model mode above the cap
- **Code style**: Full type hints, Ruff clean, minimal diffs, no unrequested refactoring, no inline comments unless a line is genuinely non-obvious
- **Process**: YOLO mode — phases auto-approve and execute without per-step diff review. This supersedes the original spec's "stop after each numbered step and show me the diff" line, dropped in favor of speed during initialization
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Highest-Value Finding #1: OpenRouter Model ID Verdicts
| Configured ID | Verdict | Correct ID to use | Vision? | Notes |
|---|---|---|---|---|
| `anthropic/claude-opus-5` | **EXISTS** | `anthropic/claude-opus-5` | Yes (`text`, `image`, `file`) | Exact string is correct as configured. 1M context, $5/M in, $25/M out. |
| `anthropic/claude-sonnet-5` | **EXISTS** | `anthropic/claude-sonnet-5` | Yes (`text`, `image`, `file`) | Exact string is correct as configured. 1M context, $2/M in, $10/M out. |
| `openai/gpt-6-astra` | **EXISTS** | `openai/gpt-6-astra` | Yes (`file`, `image`, `text`) | Exact string is correct as configured. $10/M in, $50/M out (below 272k-token tier; doubles above it). |
| `openai/gpt-5.6-sol` | **EXISTS** | `openai/gpt-5.6-sol` | Yes (`file`, `image`, `text`) | Exact string is correct as configured. $2/M in, $10/M out (below 272k-token tier). |
| `google/gemini-3.7-flash` | **EXISTS** | `google/gemini-3.7-flash` | Yes (`text`, `image`, `video`, `file`, `audio`) | Exact string is correct as configured. $0.75/M in, $3.75/M out — cheapest of the five verified frontier IDs. |
| `deepseek/deepseek-v4` | **DOES NOT EXIST** | `deepseek/deepseek-v4.1-flash` | Yes (`text`, `image`) | See below. |
### DeepSeek substitution: does DeepSeek ship a vision model on OpenRouter?
- `deepseek/deepseek-v4-pro`, `deepseek/deepseek-v4-pro-0813`, `deepseek/deepseek-v4-flash`, `deepseek/deepseek-v4-flash-0731` — all **text-only** (`input_modalities: ['text']`).
- `deepseek/deepseek-v4-flash-vision-exp` — vision-capable, but explicitly labeled **experimental**, described as "an experimental vision-enabled version of DeepSeek V4 Flash 0731."
- `deepseek/deepseek-v4.1-flash` — vision-capable (`text`, `image`), **not** tagged experimental, described by DeepSeek as exceeding V4 Pro "on performance, speed, and task" — this is the newer, more stable release.
### All six final IDs support structured outputs
## Highest-Value Finding #2: Latency & Cost for Six Parallel Vision Calls
### The 30-second budget is achievable, but only if reasoning effort is forced low on every call. Left at defaults it is not achievable.
| Model | TTFT, low/min effort | TTFT, high/max effort | Output speed (low effort) |
|---|---|---|---|
| Claude Opus 5 | 2.67s | 44.75s | ~50.8 tok/s |
| Claude Sonnet 5 | 1.38s (Anthropic first-party); independent bench 1.7s | 182.6s (max) | 60-230 tok/s (wide provider variance) |
| GPT-6 Astra | 2.69s | not directly measured — GPT-5.6 Sol's max-effort figure (131s) is the closest analog in the same family | up to 54 tok/s |
| GPT-5.6 Sol | 2.47s (low), 4.58s (medium) | 16.31s (high), 131.3s (max) | not separately reported |
| Gemini 3.7 Flash | 0.74s (low effort) | 8.9-9.83s median (high), p95 49.5s | 292.5 tok/s (high effort) |
| DeepSeek V4 Flash family | ~1.1-1.9s TTFT | not applicable (non-reasoning-heavy tier) | ~103-120 tok/s |
### Cost per question (all six fired)
| Model | Input cost | Output cost | Total |
|---|---|---|---|
| Claude Opus 5 | $0.0125 | $0.0300 | **$0.0425** |
| Claude Sonnet 5 | $0.0050 | $0.0120 | **$0.0170** |
| GPT-6 Astra | $0.0250 | $0.0600 | **$0.0850** |
| GPT-5.6 Sol | $0.0050 | $0.0120 | **$0.0170** |
| Gemini 3.7 Flash | $0.0019 | $0.0045 | **$0.0064** |
| DeepSeek V4.1 Flash | $0.0004-0.0008 | $0.0007-0.0014 | **$0.0011-0.0022** |
| **Total per question** | | | **≈ $0.17** |
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
# Core (locked stack)
# Supporting
# Dev dependencies
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
# call site
# On connection open, once, before any concurrent load:
## Version Compatibility
| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| `aiogram==3.31.0` | `pydantic>=2.4.1,<2.14` | **Hard constraint from aiogram's own dependency spec.** Latest standalone pydantic (2.13.5) fits inside this range today, but do not `pip install -U pydantic` blindly in this project — 2.14+ will break aiogram installs until aiogram bumps its ceiling. Pin pydantic explicitly rather than letting it float. |
| `imagehash==4.3.2` | Pillow (any recent 9.x-12.x) | No pinned Pillow requirement upstream; 12.3.0 (current) is fine. |
| `httpx==0.28.1` | Python `>=3.8` | No conflict with 3.12. |
| `aiosqlite==0.22.1` | Python `>=3.9` | No conflict with 3.12. |
## Perceptual Hash Choice for SAT Question Photos
- **pHash (DCT-based) over aHash/dHash:** pHash is the most robust of the four to the exact distortions phone photos introduce — uneven lighting, mild rotation/perspective, JPEG recompression. aHash (mean threshold) is the weakest — it's sensitive to lighting/exposure shifts common in phone photos of a printed page. dHash (gradient-based) is fast and decent for general near-duplicate detection (product photos, screenshots) but less robust than pHash to the lighting variance specific to photographed (not screenshotted) paper.
- **Why `hash_size=16` instead of the library default of 8:** the default produces a 64-bit hash (8x8 DCT block). SAT R&W questions across hundreds of distinct items share the same visual template — a boxed/lined passage followed by 4 lettered choices in the same font and layout. A 64-bit hash has too little entropy to reliably distinguish *content* when *layout* is near-constant across the whole question bank, risking a false-positive cache hit that serves the wrong question's answer — a direct violation of the "never confidently wrong" core value. Doubling to `hash_size=16` (256-bit hash, 16x16 DCT block) retains far more of the actual text/content signal and sharply reduces same-template collisions.
- **Threshold:** could not verify an authoritative published threshold for this specific hash_size/domain combination (no primary source found for "SAT question photo dedup" specifically) — this is a **LOW confidence, needs-validation** figure, extrapolated from the general perceptual-hashing literature's rule of thumb (~3-10% of hash bits as the near-duplicate cutoff) rather than measured against real SAT photos. Treat ≤8-10 (out of 256) as a starting point and tune it empirically in Phase 1/2 against real user-submitted retake photos of the same question — err toward a *tighter* threshold (fewer false cache hits) given the cost asymmetry: a missed cache hit costs one extra inference round (~$0.17, ~25s); a false cache hit silently serves a wrong answer to a different question, which is the exact failure this whole product exists to prevent.
## Docker / docker-compose
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
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
