# Project Research Summary

**Project:** SAT Verbal Consensus Bot
**Domain:** Async Python Telegram bot fanning one SAT R&W question image out to six vision LLMs in parallel via OpenRouter, tallying consensus
**Researched:** 2026-09-10
**Confidence:** HIGH overall — model catalog and library versions live-verified; latency/cost figures and the pitfall analysis are MEDIUM (extrapolated from third-party benchmarks and general literature, not a run of this exact prompt)

## Executive Summary

This is a fan-out-and-tally bot, not an agentic system — six identical, parallel, non-interacting calls to one OpenAI-compatible endpoint, validated against a strict pydantic contract, with SQLite persistence. The architecture research confirms the right shape is a flat, orchestrator-centric structure (`asyncio.gather` with per-model `wait_for` timeouts, one shared SQLite connection in WAL mode, no framework) — this is an `asyncio.gather` problem, not an orchestration-framework problem, and the codebase should read that way. One of the six configured model IDs is wrong and must be fixed before Phase 1 runs a single real question: `deepseek/deepseek-v4` does not exist on OpenRouter and must become `deepseek/deepseek-v4.1-flash`. The other five IDs are verified correct against the live catalog.

The single most consequential finding is that the 30-second latency budget is not a property of picking fast-enough models — all six candidates are 2026-generation reasoning models with a "thinking" dial, and left at default effort, TTFT alone runs 16-130 seconds on several of them. The budget is only achievable if `reasoning.effort` is forced to `none`/`minimal` on every OpenAI/Google/DeepSeek call and left unset (no extended thinking) on the two Anthropic calls, combined with per-model (not global) timeouts around 20-25s. This must be a named, explicit Phase 1 task with its own test, not an implementation detail buried inside the client wrapper — get it wrong and the bot is unusable, not just slow.

The second major theme is that this bot's core failure modes are silent by construction. Three separate pitfalls — models converging on a wrong answer because their errors are correlated rather than independent (shared SAT test-prep training data), all six models hallucinating the same plausible-but-wrong transcription off the same degraded image, and a perceptual-hash cache collision serving a confident answer to the wrong question — all produce output that is indistinguishable from a correct, well-functioning round. None of them raise an exception, log an error, or produce a visibly broken message. Because the eval harness is deferred to v2, the "Wrong answer" correction flow is the *only* check against any of these in v1, which means passive instrumentation (transcription-divergence logging, `served_from_cache` flags, per-lab/per-type agreement tracking) has to be built into the inference and persistence phases from day one — retrofitting it after a collision has already served wrong answers is the expensive path. Feature research also surfaces a set of table-stakes gaps missing from PROJECT.md's Active requirements (no `/help`, no pre-flight image quality gate, no MarkdownV2 escaping plan, no pagination plan for a breakdown message that will routinely exceed Telegram's 4096-character cap, and a correction flow whose input mode is unspecified and risks corrupting the one dataset the deferred eval harness depends on) — these are cheap (all S-complexity) and should be folded into the roadmap rather than treated as v1.x polish.

## Key Findings

### Recommended Stack

Locked stack (Python 3.12, aiogram 3.31.0, httpx 0.28.1, aiosqlite 0.22.1, pydantic 2.13.5 pinned `<2.14` for aiogram compatibility, imagehash 4.3.2, Ruff) is internally compatible with no version conflicts. All six final model IDs support `response_format`/`structured_outputs` and a `reasoning.effort` dial — the latter is the load-bearing mechanism for hitting the latency budget, not an optional tuning knob.

**Core technologies:**
- **aiogram 3.31.0** — async Telegram framework; `Formatting`/`Spoiler`/`Bold` API and `ChatActionSender` cover the spoiler-answer and typing-indicator requirements natively, sidestepping hand-escaped MarkdownV2 strings (the single most common aiogram bug class).
- **httpx.AsyncClient (shared, one instance)** — six concurrent OpenRouter calls per question; a shared client reuses the connection pool instead of paying 6x TLS handshake overhead per question.
- **aiosqlite 0.22.1, WAL mode + `busy_timeout`, one shared connection** — SQLite is single-writer regardless of async wrapper; buffer all six model results in memory and write them in one batch transaction after `gather` completes rather than six concurrent writes.
- **pydantic v2, `model_validate_json` + `ValidationError.errors()`** — the actual contract enforcement; OpenRouter's `strict: true` on `json_schema` is provider-dependent, not a guarantee, so every response must still be validated regardless of what was requested.
- **imagehash.phash, `hash_size=16` (256-bit), not the library default of 8** — SAT R&W questions share a near-identical visual template (boxed passage, four lettered choices) across hundreds of distinct items; a 64-bit hash has too little discriminative power on this template-heavy content and risks a false-positive cache hit serving the wrong question's answer.

### Expected Features

**Must have (table stakes — currently missing from PROJECT.md Active scope):**
- `/start` and `/help` onboarding — no bot is usable by a 10-40 person group without one
- Pre-flight image quality gate (blur variance + resolution floor) — attacks the user's own named dominant failure mode (bad OCR) *before* six paid model calls run on an unusable image; complements, not replaces, the existing "prefer document upload" messaging
- Robust MarkdownV2 escaping utility (shared, tested against adversarial LLM-shaped strings) — the consensus spoiler and full breakdown both render untrusted model-generated text; an unescaped character causes a total `sendMessage` failure (400 `can't parse entities`), not a cosmetic glitch — the user gets nothing
- Message-length pagination for "Full breakdown" — six models' transcription + four elimination verdicts each will **routinely**, not occasionally, exceed Telegram's 4096-character cap
- Structured A/B/C/D inline buttons for "Wrong answer" correction (not free text) — PROJECT.md's spec ("asks for the real letter") doesn't fix the input mode; free text invites malformed input ("b", "B)", "it's b i think") that corrupts `ground_truth`, the one dataset the deferred v2 eval harness will depend on
- Friendly quota-exceeded messaging — cheap, and the per-user daily cap is already load-bearing

**Should have (differentiators):**
- Lab-spread-aware consensus annotation — see Apple ML Research finding below; a display-layer change on top of the already-planned boot-time lab-diversity tracking, not a new data source
- The already-planned design itself (independent single-round voting, forced verbatim transcription, forced per-choice elimination) is validated by the literature — no changes needed there

**Defer (v2+):**
- Self-consistency resampling (2-3x per model before ensemble vote) — the single strongest published accuracy lever found in this research pass (+3 to +23 points), but multiplies cost and latency 2-3x, breaking both hard-locked constraints; revisit only if v2 eval data shows per-model reasoning failure, not image quality, is the bottleneck
- Private `/mystats`, gamification — not needed to validate the core consensus premise

### Architecture Approach

Flat, non-layered structure: `handlers/` (Telegram I/O only) → `orchestrator/` (fan-out, contract, consensus — pure, independently testable, no Telegram objects) → `db/` (all SQL centralized here) → `formatting/` (pure functions, no aiogram dependency). The riskiest logic (parallel calls, partial failure, timeouts) lives in `orchestrator/fanout.py` and must be catchable/testable without a live Telegram message.

**Major components:**
1. **Boot-time validation** (`validation/boot.py`) — live `GET /models` check that every configured ID exists, supports image input, and the roster spans ≥4 distinct labs; fails loudly and exits nonzero, naming the offending ID, rather than letting a stale/wrong ID 404 on the first real question
2. **Fan-out orchestrator** (`orchestrator/fanout.py`) — owns the six-way `asyncio.gather`, with the *per-model* `asyncio.wait_for` timeout as the real latency control and an outer round-level timeout as a defensive backstop only; must catch every exception inside each per-model coroutine so one flaky/slow model never cancels the other five
3. **Response validation + repair** (`orchestrator/contract.py`) — pydantic parse, one repair retry (syntax-extraction only, no re-sent image/prompt, so the retry can't silently change the model's vote), else abstain
4. **Consensus tally + reply formatting** — pure functions operating on validated/abstained results, decoupled from Telegram objects
5. **Cache gate** (`images/extract.py` + `db/questions.py`) — computes phash and short-circuits the entire orchestrator on a cache hit; sits *in front of* the orchestrator, not inside it

### Critical Pitfalls

1. **Consensus is not a calibrated confidence signal — agreement can be correlated, not independent.** Models share pretraining exposure to SAT test-prep material and may converge on the same wrong answer for the same reason, producing 6/6 "strong agreement" that is confidently wrong. Never let UI copy imply agreement means correctness; log per-lab and per-question-type agreement data now even though it isn't surfaced yet, since it's the only groundwork for the deferred eval harness.
2. **Correlated OCR hallucination across models seeing the identical degraded image.** A blurry/glared photo doesn't make a model say "I can't read this" — it produces a plausible, confidently wrong transcription, and because all six models see the *same* image, they can hallucinate *similarly*, producing agreement instead of the disagreement the ensemble is supposed to surface. Diff the six transcriptions pairwise; if ≥2 lab-distinct models diverge beyond minor OCR noise, flag low-confidence regardless of answer-letter agreement — and be explicit in the UX that this check cannot catch the "all six hallucinated the same way" case.
3. **Perceptual-hash cache collision serves a wrong answer with zero visible error.** Standard pHash is invariant to exactly the wrong things for this content: it discards high-frequency detail (the actual words) to stay invariant to crop/brightness/JPEG noise, but for template-heavy SAT question images, the words are the only thing that distinguishes two different questions. Ship exact-phash-match caching only in v1 (handles "same photo re-sent," the dominant real case) and explicitly defer Hamming-distance fuzzy matching until a content-verification step exists — do not serve a fuzzy hit on hash proximity alone.
4. **The 30s budget is `max()`, not `avg()`, across six calls, and reasoning-effort defaults blow through it by 5-40x.** Force `reasoning.effort: "none"/"minimal"` on every OpenAI/Google/DeepSeek call, leave Anthropic's `reasoning` field unset entirely, and use a per-model timeout (20-25s) well under the 30s wall clock so one stalled model degrades to an abstain instead of dragging the whole round over budget.
5. **Spend-cap enforcement as read-then-write is a TOCTOU race that concurrent study-group usage will actually hit.** 3-5 students hitting send within the same second (a normal study-session pattern) can all pass a stale-read cap check simultaneously. Enforce with a single atomic conditional `UPDATE ... WHERE total + ? <= ?`, and make sure JSON-repair retries are counted in the reservation, not silently excluded.

## Implications for Roadmap

Architecture research independently converged on a 2-3 phase structure matching PROJECT.md's stated preference for a compressed roadmap; feature and pitfall research slot into that same structure without requiring a 4th phase — they add tasks inside the existing three, not new phases.

### Phase 1: Core Inference Loop
**Rationale:** Absorbs essentially all of this project's technical risk in one place — model ID correctness, reasoning-effort/latency control, JSON-contract compliance and repair, per-model failure isolation, boot-time validation. Nothing else in the roadmap is buildable end-to-end until one photo reliably produces one correct six-model tallied reply within budget.
**Delivers:** Credentials + `config.py`; `validation/boot.py` (live model/modality/lab-diversity check, with the corrected six-ID roster); `orchestrator/client.py` proven against one real model before wiring all six; `orchestrator/fanout.py` (six-way `asyncio.gather`, per-model `wait_for` timeout, `reasoning.effort` forced low/unset per provider); `orchestrator/contract.py` (pydantic contract + one syntax-only repair retry, raw pre-repair response logged); `orchestrator/consensus.py` (tally); minimal `handlers/ingest.py` + `formatting/reply.py`; bare persistence writes.
**Addresses:** Ingestion and Inference requirements from PROJECT.md; the pre-flight image quality gate (cheap, S-complexity, and logically precedes inference in the data flow — belongs here rather than deferred).
**Avoids:** Pitfall 4 (latency blowout) by construction; lays the groundwork for Pitfalls 1 and 2 (log raw transcriptions and per-model latency/error metadata from the first working round, even before the tally UI surfaces any of it).
**Explicit named task, not buried in implementation:** forcing `reasoning.effort` per-provider and validating actual `usage.completion_tokens`/wall-clock time against the 30s budget with a real prompt, before committing to a final `max_tokens` value.

### Phase 2: Persistence, Caching & Cost Control
**Rationale:** Everything here is a policy/data layer on top of a working Phase 1 round — cache short-circuit, spend accounting, and access control all need real `attempts` rows to operate against, so they follow rather than lead.
**Delivers:** Full `questions`/`attempts`/`users` schema in active use; phash cache (`hash_size=16`, **exact-match only in v1**, `served_from_cache` logged per attempt, Hamming-fuzzy matching explicitly deferred pending a content-verification step); atomic conditional-update spend cap with degraded cheaper-model-set fallback (GPT-6 Astra — roughly half the ~$0.17/question all-six cost — is the natural first model dropped); allowlist + per-user daily cap middleware; `/cost` and `/adduser`.
**Avoids:** Pitfall 3 (cache collision) via exact-match-only caching; Pitfall 5 (spend-cap race) via atomic updates instead of read-then-write.

### Phase 3: Interaction & Consensus Reporting Polish
**Rationale:** Mostly reply-text and UI work with no new architectural risk — could be folded into Phase 2 if the roadmap wants exactly two phases, but keeping it separate isolates the table-stakes gaps (onboarding, escaping, pagination, structured correction input) that are otherwise easy to under-scope as "just formatting."
**Delivers:** `/start`/`/help` onboarding with photo-taking guidance; robust MarkdownV2 escaping utility (aiogram `Text`/`Spoiler`/`Bold` objects, not hand-escaped strings) with an adversarial-string test and a plain-text fallback on `CantParseEntities`; message-length pagination for "Full breakdown" (split by model, don't truncate); structured A/B/C/D inline buttons for "Wrong answer" (protects `ground_truth` integrity); lab-spread-aware consensus annotation ("5/6 agree, spanning 4 labs" vs. "spanning 2 labs" — see Apple ML Research finding below); friendly quota-exceeded copy; typing indicator via `ChatActionSender`.
**Avoids:** Pitfall 7 (MarkdownV2 total delivery failure) via the shared escaping utility and fallback.

### Phase Ordering Rationale

- Dependency-driven, not preference-driven: boot validation must exist before the fan-out can be trusted; the fan-out must produce real `attempts` rows before caching/cost/access-control logic has anything real to enforce against; the correction-button UX only matters once a real reply is being sent.
- Grouping by architectural risk profile, not by feature category: Phase 1 is "does the hard technical core work at all," Phase 2 is "policy and data correctness," Phase 3 is "user-facing polish with well-documented patterns" — this ordering front-loads exactly the risk PROJECT.md flagged as wanting research before Phase 1 planning (latency).
- The pre-flight image quality gate is placed in Phase 1 rather than Phase 3 despite being a "table stakes UX" item, because architecturally it precedes inference in the data flow and is cheap enough not to threaten Phase 1's already-heavy scope.

### Research Flags

Needs research/spike during planning:
- **Phase 1:** An early empirical spike — fire all six models once with the real system prompt and image, log actual `usage.completion_tokens` and wall-clock time per model, *before* finalizing `max_tokens` and confirming the 30s budget holds with `reasoning.effort` forced low. The 24-27s worked example in STACK.md is MEDIUM confidence, interpolated from general benchmarks, not measured against this exact prompt shape.
- **Phase 1:** Exact JSON key for `usage.cost` (or derive from token counts × price) and exact `architecture.input_modalities` field shape should be spot-checked against a live OpenRouter response, not assumed from docs excerpts (flagged MEDIUM in both STACK.md and ARCHITECTURE.md).

Standard patterns (skip research-phase):
- **Phase 2:** SQLite WAL/`aiosqlite` concurrency handling and atomic conditional-update spend caps are well-documented patterns with clear prior art cited in PITFALLS.md — implement directly.
- **Phase 3:** aiogram's `Formatting`/`Spoiler`/`ChatActionSender`/`InlineKeyboardBuilder` APIs are stable, documented, and cited directly in STACK.md with working code patterns — implement directly.

## Conflicts and Resolutions

- **Model roster correctness.** PROJECT.md's Known Risks section flags vaguely that "several [model IDs] may not exist." Research resolves this precisely: only one of six is wrong (`deepseek/deepseek-v4` → `deepseek/deepseek-v4.1-flash`); the other five are confirmed correct against the live catalog. The roadmap should treat this as a one-line config fix validated by the boot-time check, not an open risk requiring further investigation.
- **Perceptual hash strategy — three documents, one resolved recommendation.** ARCHITECTURE.md recommends shipping exact-phash-match only and deferring Hamming-distance fuzzy matching entirely; STACK.md recommends `hash_size=16` with a Hamming threshold of ≤8-10 as a *starting point*; PITFALLS.md argues fuzzy matching is structurally the wrong tool for this content domain without a secondary content-verification step. These are not in real conflict but read as three different emphases — resolved here as: use `hash_size=16` (STACK.md) but restrict v1 to exact-match lookups only (ARCHITECTURE.md), with fuzzy Hamming-distance matching explicitly out of scope for v1 and revisited only once a content-verification step (PITFALLS.md) is designed in, not bolted on. This is the safer failure mode — a cache miss costs one inference round (~$0.17, ~25s); a false cache hit silently serves a wrong answer, which is the exact failure this product exists to prevent.
- **"Wrong answer" correction input mode.** PROJECT.md specifies the button "asks for the real letter" but does not fix the input mechanism. FEATURES.md's recommendation (structured A/B/C/D inline buttons, not free text) is a refinement that should win — it protects the `ground_truth` dataset without changing any locked scope or requirement.
- **Self-consistency resampling.** Flagged across FEATURES.md and PITFALLS.md as the single strongest accuracy lever in the entire research pass, and explicitly *not* recommended for this roadmap — it directly conflicts with the already-locked "one round, no cascade" decision and both the 30s latency and global spend cap constraints. Per instructions, this is noted once as a real tradeoff and not relitigated against the Out of Scope list; it is correctly out for v1 and worth reconsidering only if v2 eval data isolates per-model reasoning (not image quality) as the accuracy bottleneck.
- **No contradictions found between research and PROJECT.md's Out of Scope list or Core Value.** All findings reinforce "never assert correctness" and "ensemble is the product" rather than pushing against them (e.g., the anti-feature findings on self-reported confidence scores and confidence-weighted voting directly support the existing unweighted-tally design).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Model IDs, modalities, and `supported_parameters` verified live against OpenRouter's `/models` catalog; library versions verified via PyPI. Latency/cost figures are MEDIUM (third-party general benchmarks interpolated onto an estimated, not measured, token count for this exact prompt). |
| Features | MEDIUM-HIGH | Prompt-engineering and ensemble-agreement claims are arxiv-sourced and consistent across multiple papers (HIGH); Telegram UX practices and the ConvergePanel competitor analog are practitioner/product-page sourced (MEDIUM). |
| Architecture | HIGH | aiogram router patterns, `asyncio.gather`/`wait_for` semantics, and aiosqlite single-writer behavior all confirmed against current docs and issue trackers. One field-name detail (`/models` capability field shape) flagged MEDIUM pending a live spot-check. |
| Pitfalls | MEDIUM-HIGH | aiogram/Telegram/SQLite/OpenRouter mechanics verified against docs and issue trackers (HIGH); consensus-calibration and correlated-error claims sourced to recent literature (HIGH on the underlying finding, MEDIUM on domain-specific extrapolation to SAT test-prep content specifically). pHash Hamming-distance threshold for this domain is explicitly LOW confidence — no primary source found for "SAT question photo dedup" specifically. |

**Overall confidence:** HIGH on what to build and in what order; MEDIUM on the exact numeric parameters (max_tokens, per-model timeout seconds, phash threshold) that should be tuned empirically in Phase 1 rather than locked from research alone.

### Gaps to Address

- **Real latency/token-count measurement:** the 30s budget's margin is thin (worked example ~27s against a 30s budget) and based on estimated, not measured, completion-token counts — run the Phase 1 spike before finalizing `max_tokens` or declaring the budget safely met.
- **pHash Hamming-distance threshold:** no authoritative source for this specific domain; v1 sidesteps this by using exact-match-only caching (see Conflicts and Resolutions), deferring the threshold question until fuzzy matching is actually built.
- **Per-model JSON-repair-retry frequency:** expected to skew toward whichever of the six is the "budget" model, but unverified for this exact six-model roster until real traffic exists — instrument and monitor from Phase 1, don't assume even distribution.
- **OpenRouter `usage.cost` field exact shape:** verify against a live response in Phase 1 rather than assuming a specific JSON key from docs excerpts, since cost accounting in Phase 2 depends on it being correct.
- **Apple ML Research finding, applied concretely:** "Nine Judges, Two Effective Votes" (arxiv 2605.29800) found a 9-model, 7-lab panel carried only ~2 independent votes' worth of information due to correlated errors — this is the strongest single piece of evidence that raw vote count alone overstates confidence. The concrete roadmap implication (Phase 3) is to report lab spread within the majority alongside the vote tally, e.g. "5/6 agree, spanning 4 labs" rather than "5/6 agree" — reusing the already-planned boot-time lab mapping, not a new data source.

## Sources

### Primary (HIGH confidence)
- `https://openrouter.ai/api/v1/models` — live catalog fetch, 2026-09-10 — model ID/modality/pricing verdicts, including the deepseek-v4 → deepseek-v4.1-flash correction
- `https://openrouter.ai/docs/use-cases/reasoning-tokens` — `reasoning.effort`/`reasoning.max_tokens` mechanics, the load-bearing source for the latency mitigation strategy
- `https://openrouter.ai/docs/features/structured-outputs` — `response_format`/`json_schema` provider-dependent enforcement
- PyPI JSON API — aiogram, httpx, aiosqlite, pydantic, ImageHash, ruff, pillow version/compatibility verification
- [Nine Judges, Two Effective Votes (arxiv 2605.29800, Apple ML Research)](https://machinelearning.apple.com/research/correlated-llm-evaluation-panels) — lab-spread annotation recommendation
- [aiogram Router / formatting / chat_action documentation](https://docs.aiogram.dev/) — code patterns used directly in Phase 1/3 recommendations

### Secondary (MEDIUM confidence)
- [When LLMs Agree, Are They Right? (arxiv 2607.08065v1)](https://arxiv.org/html/2607.08065v1) — correlated-agreement pitfall
- [Artificial Analysis provider benchmarks](https://artificialanalysis.ai/) — latency/throughput figures used for the 30s budget analysis
- [Context-Independent OCR with Multimodal LLMs (arxiv 2503.23667)](https://arxiv.org/pdf/2503.23667) — pre-flight image quality gate rationale
- [BiasPrompting (arxiv 2511.20086)](https://arxiv.org/html/2511.20086) — validates forced per-choice elimination design
- [ConvergePanel product page](https://convergepanel.com/use-cases/multi-llm-answer-comparison) — competitor validation of the independent-multi-model-answers premise

### Tertiary (LOW confidence)
- General perceptual-hashing threshold literature (no primary source specific to photographed SAT-question dedup) — flagged as needing empirical validation, resolved for v1 by deferring fuzzy matching entirely
- Telegram bot UX practitioner blogs — directionally reliable, not rigorously sourced

---
*Research completed: 2026-09-10*
*Ready for roadmap: yes*
