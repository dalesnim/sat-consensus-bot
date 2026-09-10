# Phase 1: Core Inference Loop - Context

**Gathered:** 2026-09-10
**Status:** Ready for planning

<domain>
## Phase Boundary

A user sends a photo or document of one SAT Reading & Writing question to the Telegram bot and receives an honest six-model consensus reply — reasoning first, consensus letter last inside a spoiler — within a 30 second budget.

This phase absorbs the project's technical risk: boot-time validation against OpenRouter's live model catalog, forcing `reasoning.effort` down as the load-bearing latency mitigation, an empirical latency spike before parameters are locked, per-model timeout and failure isolation, and a pre-flight image quality gate that runs before any inference spend.

**In scope:** config loading and boot validation, the shared prompt, the six-way parallel fan-out, the strict JSON contract and its repair path, consensus tallying, reply formatting, image ingestion and rejection, Docker packaging.

**Out of scope for this phase:** persistence, the perceptual-hash cache, allowlist enforcement, spend caps, `/cost` and `/adduser`, the "Full breakdown" and "Wrong answer" buttons, `/help`, MarkdownV2 escaping hardening, message pagination, and the typing indicator. Those are Phases 2 and 3.

</domain>

<decisions>
## Implementation Decisions

### Reply Format & Copy
- Header states the split on one compact line including lab count: `5/6 agree · 3 labs` (satisfies CON-01 and CON-02 together)
- Default reply shows merged elimination reasoning for the winning letter only, roughly four lines; full per-model detail is deferred to the Phase 3 "Full breakdown" button
- The consensus letter is revealed in a MarkdownV2 spoiler, alone on the final line, after all reasoning (CON-06)
- On a 3/3 or worse unresolved split, every distinct position is shown with its supporting reasoning plus an explicit "worth asking a teacher about" line, and **no spoiler letter is shown at all** — showing a plurality letter here would imply a confidence the models do not have

### Latency & Degradation
- Per-model timeout is 22 seconds; an outer circuit breaker around the whole round is 26 seconds, leaving margin inside the 30 second budget
- A model still running at the cutoff is cancelled and counted as an abstention; the reply goes out on time rather than waiting
- A minimum of 3 valid model responses is required to report a consensus at all; below that the bot apologizes and asks the user to retry rather than reporting a consensus drawn from too few voters
- `max_tokens` starts at the specified 2000, but the empirical spike measures actual completion tokens and the value is lowered if transcription plus reasoning fits in less

### Model Call Mechanics
- JSON is enforced with OpenRouter structured outputs (`json_schema`), which research confirmed all six models support, with a prompt-only fallback path if a model rejects the schema
- Images are sent as base64 data URLs with no resizing in this phase; resize logic waits until the spike shows real image-token cost
- `reasoning.effort` is set to `none` where the model supports it, with a per-model `minimal`/`low` fallback recorded explicitly in `models.yaml` rather than a single global value
- The repair retry calls the same model with a syntax-extraction-only prompt containing the malformed text, and does **not** resend the image — cheaper, and structurally unable to re-reason and change the vote (INF-12)

### Ingestion & Rejection
- The pre-flight image quality gate runs locally before any inference spend, checking minimum resolution and Laplacian blur variance; it warns and proceeds by default, hard-rejecting only when far below threshold
- Whether an image is SAT verbal and whether it contains more than one question is decided by the models themselves via contract fields, with a majority of returning models deciding — no separate classifier call, which would add a seventh call to the round and worsen the primary latency risk
- Rejection messages are brief, friendly, and actionable — e.g. "I can't read this clearly, try sending it as a file instead of a photo"
- The document-over-photo nudge appears as a one-line footer on photo-sourced replies only, never on document-sourced ones

### Claude's Discretion
- Module and file layout (guided by `.planning/research/ARCHITECTURE.md`)
- Exact wording of all user-facing copy within the tone decided above
- Blur variance and resolution threshold starting values, to be tuned once real photos exist
- Logging format and levels
- Test structure and coverage depth

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
None — greenfield repository, no source files yet.

### Established Patterns
None established in code. The binding conventions come from PROJECT.md: full type hints, Ruff clean, minimal diffs, no inline comments unless a line is genuinely non-obvious, secrets from env only.

### Integration Points
All external. The bot integrates with the Telegram Bot API via aiogram 3.x and with OpenRouter's OpenAI-compatible chat completions endpoint via httpx. No internal integration surface exists yet.

### Research Available
- `.planning/research/ARCHITECTURE.md` — proposed module layout, fan-out and timeout patterns, data flow with failure branches
- `.planning/research/STACK.md` — verified model IDs, library versions, OpenRouter mechanics
- `.planning/research/PITFALLS.md` — ranked failure modes with prevention strategies
- `.planning/research/SUMMARY.md` — synthesized findings

</code_context>

<specifics>
## Specific Ideas

- The corrected model roster is: `anthropic/claude-opus-5`, `anthropic/claude-sonnet-5`, `openai/gpt-6-astra`, `openai/gpt-5.6-sol`, `google/gemini-3.7-flash`, `deepseek/deepseek-v4.1-flash`. The last one is a correction — `deepseek/deepseek-v4` does not exist as a vision model on OpenRouter.
- Boot validation must check three things and fail loudly naming the offending ID: the model exists in OpenRouter's live catalog, it advertises image input support, and the roster spans at least 4 distinct labs.
- The empirical latency spike is a named deliverable, not an implementation detail. It fires all six models once with the real prompt and logs actual completion tokens and wall-clock time per model. Its output determines whether `max_tokens` stays at 2000.
- Per-model failure isolation lives **inside** each coroutine. `asyncio.gather(return_exceptions=True)` is a backstop only, never the primary mechanism.
- The eleven College Board question types are enumerated in PROJECT.md and must be the exact enum used in the contract.
- The prompt is used byte-identically by every model. No model ever sees another model's output.

</specifics>

<deferred>
## Deferred Ideas

- Image resizing / downscaling before send — revisit after the spike reports real image-token cost
- Tuned blur and resolution thresholds — needs real user photos, not synthetic tests
- Fuzzy perceptual-hash matching — already tracked as CACHE-01 in v2
- Self-consistency resampling — already tracked as CONS-01 in v2

</deferred>
