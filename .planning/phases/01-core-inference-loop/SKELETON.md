# Walking Skeleton — SAT Verbal Consensus Bot

**Phase:** 1
**Generated:** 2026-09-10

## Capability Proven End-to-End

A student sends a photo of one SAT Reading & Writing question to the Telegram bot and receives, within 30 seconds, a reply that states how the six models split, gives the elimination reasoning behind the leading position, and hides the consensus letter in a spoiler on the final line.

The skeleton is walked in two steps. Plan 01 proves the *wiring* — a Telegram update reaches a reply with a spoiler-wrapped letter, with the six-model round stubbed. Plan 06 replaces the stub with the live round without changing a single signature Plan 01 defined.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language / runtime | Python 3.12, full type hints, Ruff-clean | Locked in PROJECT.md constraints; 3.12 sits inside every pinned library's supported range |
| Telegram framework | aiogram 3.31.0, long-polling | Single VPS with no reverse proxy and no public HTTPS endpoint; long-polling needs neither. `Formatting`/`Spoiler` builds message entities programmatically, which structurally removes the MarkdownV2 escaping bug class |
| HTTP client | one shared `httpx.AsyncClient` for the process | Six concurrent OpenRouter calls per question reuse one connection pool instead of paying six TLS handshakes |
| Model gateway | OpenRouter `/api/v1/chat/completions`, OpenAI-compatible | One key, one schema, one bill across six models from four labs |
| Orchestration | `asyncio.gather` with per-coroutine try/except; no framework | This is a fan-out-and-tally problem, not an agent problem. LangChain and equivalents are explicitly out of scope |
| Concurrency control | per-model `asyncio.wait_for` at 22s inside each coroutine; a 26s `wait_for` around `gather` as a circuit breaker only | The 30s budget is `max()` across six calls, not `avg()`. Isolation must live inside each task; `return_exceptions=True` is a backstop against a programming bug, never the mechanism |
| Latency control | `reasoning.effort` forced to `none`/`minimal` per model; the `reasoning` key omitted entirely for both Anthropic models | Load-bearing. At default effort, time-to-first-token alone runs 16–131s on several of these models and the budget fails outright |
| Contract enforcement | pydantic v2 `model_validate_json` on every response, with `response_format: json_schema` as a hint only | OpenRouter documents `strict: true` as provider-dependent; the schema improves the odds, pydantic is the actual gate |
| Repair strategy | exactly one syntax-extraction-only retry with no image and no grading rules, then abstain | A repair that can re-reason can silently change a model's vote and corrupt the ensemble |
| Configuration | `models.yaml` for the roster, `pydantic-settings` for env; secrets typed `SecretStr` | No model ID may appear in Python source (CFG-01); secrets must not survive a `repr()` |
| Boot gate | live `GET /api/v1/models` check for existence, image modality, structured-output support, and ≥4 distinct labs, before the dispatcher starts | A stale model ID must be a refusal to boot, not a 404 on the first real question |
| Data layer | none in Phase 1 | Persistence, the phash cache, spend caps, and the allowlist are Phase 2. The `sqlite_data` named volume is declared in `docker-compose.yml` now so Phase 2 needs no compose change |
| Deployment target | single VPS, Docker Compose, `python:3.12-slim`, non-root uid 10001, `restart: unless-stopped` | Locked in PROJECT.md; no orchestration platform, no managed services, no second container |
| Directory layout | flat concern folders under `src/bot/` — see below | Each folder is one concern with 1–4 files; no `services/`, `repositories/`, or `dto/` ceremony |

### Directory layout (binding for Phases 2 and 3)

```
src/bot/
├── main.py            entrypoint: settings, boot validation, Deps, polling
├── __main__.py        python -m bot
├── config.py          Settings + models.yaml parsing, no network
├── prompts.py         SYSTEM_PROMPT, USER_PROMPT, REPAIR_PROMPT_TEMPLATE — constants only
├── pipeline.py        answer_question(): gate -> fan-out -> tally -> render
├── handlers/          Telegram I/O only, no orchestration
├── orchestrator/      contract.py, client.py, fanout.py, consensus.py
├── formatting/        pure reply rendering, no Bot/Message imports
├── images/            file selection, quality gate, data URLs — no aiogram, no logging
└── validation/        boot.py — network I/O, kept out of config.py so config stays unit-testable
models.yaml            the six IDs, labs, per-model reasoning mode, max_tokens
scripts/               latency_spike.py
tests/                 mirrors src/bot, driven by httpx.MockTransport, zero credentials required
```

Phase 2 adds `db/` and `cost/`. Phase 3 adds `handlers/buttons.py` and `middleware/`. Nothing else moves.

## Stack Touched in Phase 1

- [x] Project scaffold — `pyproject.toml`, hatchling build, Ruff, pytest with `asyncio_mode = "auto"`
- [x] Routing — one aiogram `Router` handling `F.photo` and `F.document`
- [x] External data — six real OpenRouter calls per question plus one boot-time catalog read; no database in this phase by design
- [x] UI — a real Telegram reply with a spoiler entity, wired to the real pipeline
- [x] Deployment — `docker compose up -d --build` on the target VPS, plus `python -m bot` and `python -m bot --validate-only` locally

## Out of Scope (Deferred to Later Slices)

Explicitly not in the skeleton. Later phases may add these; they may not renegotiate the decisions above.

- SQLite persistence, `questions` / `attempts` / `users` schema, WAL setup — Phase 2
- Perceptual-hash cache and `served_from_cache` flags — Phase 2
- Allowlist middleware, per-user daily caps, `/adduser` — Phase 2
- Global spend cap, degraded cheaper-model set, `/cost` — Phase 2
- Typing indicator, `/help`, `/start` — Phase 3
- "Full breakdown" and "Wrong answer" inline buttons, `ground_truth` writes — Phase 3
- MarkdownV2 escaping hardening beyond entity-based construction, and message pagination — Phase 3
- Image downscaling or re-encoding before send — deferred until the Phase 1 spike reports real image-token cost
- Tuned blur and resolution thresholds — needs real user photos, not synthetic tests
- Fuzzy Hamming-distance phash matching (CACHE-01) and self-consistency resampling (CONS-01) — v2
- Eval harness and labeled dataset (EVAL-01 through EVAL-07) — v2

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- **Phase 2:** the bot remembers every question and attempt, skips re-paying for a duplicate image, and stays inside its budget and its allowlist. Adds `db/` and `cost/` behind the existing `Deps`; `pipeline.answer_question` gains a cache short-circuit in front of `run_round` and a persistence write after `tally`.
- **Phase 3:** a study group can onboard itself, drill into a full per-model breakdown, and correct a wrong answer. Adds `handlers/buttons.py` and `middleware/`; `formatting/reply.py` gains pagination and a plain-text fallback path. No change to `orchestrator/`.
