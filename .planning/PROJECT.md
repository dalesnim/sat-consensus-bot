# SAT Verbal Consensus Bot

## What This Is

A Telegram bot for SAT Reading & Writing practice. A user sends a photo of one SAT verbal question; the bot sends that identical image to six independent frontier models in parallel and reports what each of them chose, along with elimination reasoning for all four answer choices. Agreement across independent models is the confidence signal — the bot never claims to know the correct answer, it reports what the models converged on and how strongly.

Built for a study group / class of roughly 10–40 allowlisted students.

## Core Value

**Honest confidence signaling.** When the models unanimously agree, the user should be able to trust that. When they split, the user must see the split rather than a fabricated single answer. A bot that confidently reports a plausible-sounding wrong answer is worse than no bot.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. -->

**Ingestion**
- [ ] User can send a photo of one SAT verbal question and get a response
- [ ] Bot takes the largest available PhotoSize, or raw bytes when sent as a document
- [ ] Bot tells users to prefer document uploads (Telegram photo compression degrades OCR — the dominant failure mode)
- [ ] Bot politely rejects non-SAT-verbal images using the `is_sat_verbal` flag
- [ ] Bot rejects multi-question screenshots

**Inference**
- [ ] All six configured models are fired in parallel on every question, one round, no cascade
- [ ] Every model receives a byte-identical prompt and the identical image
- [ ] No model ever sees another model's output
- [ ] Each model returns a strict JSON contract validated with pydantic
- [ ] One repair retry on parse failure, then that model abstains for the question
- [ ] Boot-time validation confirms every configured model ID exists on OpenRouter and supports image input, failing loudly and naming the offending ID
- [ ] Boot-time validation enforces lab diversity across the round (≥4 distinct labs), refusing to start if violated

**Consensus reporting**
- [ ] Bot tallies all six votes and reports the split in a header line
- [ ] 6/6 or 5/1 reports as "strong agreement" with merged reasoning
- [ ] 4/2 reports as "majority, contested" showing both sides' elimination reasoning
- [ ] 3/3 or worse reports as "unresolved", showing every distinct position and advising the user to ask a teacher
- [ ] Two or more abstentions in a round degrades the reported confidence
- [ ] Reasoning is shown first; the consensus letter comes last inside a MarkdownV2 spoiler
- [ ] Bot never writes "the correct answer is" — only what the models chose

**Interaction**
- [ ] Typing action displayed while inference runs
- [ ] Inline "Full breakdown" button showing per-model, per-choice reasoning
- [ ] Inline "Wrong answer" button that asks for the real letter and writes it to `ground_truth`

**Caching & persistence**
- [ ] Perceptual hash computed per image; cache hit returns the stored result with no inference
- [ ] Every question, attempt, and user persisted to SQLite
- [ ] Per-attempt logging of tokens, latency, computed cost, and errors

**Access & cost control**
- [ ] Allowlist-only access via `ALLOWED_USER_IDS`
- [ ] `/adduser` restricted to `OWNER_ID`
- [ ] Per-user daily cap, default 40
- [ ] Global daily spend cap from env; above it, the bot drops to a reduced cheaper model set and says so in the reply
- [ ] `/cost` command for `OWNER_ID` showing today, this week, and cost per question

**Operations**
- [ ] Runs under Docker + docker-compose on a single VPS
- [ ] Secrets from env only; `.env.example` shipped, `.env` never committed

### Out of Scope

- **SAT Math section** — verbal is the target; math has different failure modes and different prompt requirements
- **Routing to a single "best" model** — defeats the entire premise; the ensemble *is* the product
- **Multi-question screenshots** — rejected at ingestion; one question per image keeps the contract clean
- **Conversation memory** — each question is independent; state would invite contamination between questions
- **Web UI** — Telegram is the interface
- **Any claim of knowing the correct answer** — the bot reports model choices and agreement, never ground truth
- **LangChain or any orchestration framework** — direct httpx calls against OpenRouter's OpenAI-compatible schema are sufficient and keep the dependency surface small
- **Escalation / two-tier cascade** — dropped during initialization; all six models fire every time instead (see Key Decisions)
- **Eval harness and labeled dataset (`eval run` / `eval report`)** — deferred to v2; no labeled College Board data exists yet and building one by hand is not wanted right now. The correction flow still writes `ground_truth`, so the dataset accumulates passively from real usage
- **Synthesizing practice questions** — any future dataset seeds from official College Board practice tests only

## Context

**Domain.** SAT Reading & Writing questions are text-dependent by design: the correct answer must be supported by the passage, and the wrong answers are engineered to be plausible. This is exactly the shape of problem where a single LLM produces a confident, well-argued, wrong answer. The ensemble exists specifically to catch that.

**Why lab diversity matters.** Models from the same lab share training data and RLHF methodology, so they share failure modes. Two Anthropic models agreeing is weaker evidence than an Anthropic model and a DeepSeek model agreeing. Lab diversity is worth more to this system than raw per-model capability, which is why it's a boot-time hard constraint rather than a guideline.

**Why elimination reasoning is forced.** Free-form answering is what produces the plausible-sounding wrong answer. The prompt requires transcribing the passage and all four choices verbatim before any reasoning, then writing an explicit verdict for every choice. A model may not select an answer without eliminating the other three.

**Question types** mirror College Board's official domains: `central_ideas_details`, `command_of_evidence_textual`, `command_of_evidence_quantitative`, `inferences`, `words_in_context`, `text_structure_purpose`, `cross_text_connections`, `rhetorical_synthesis`, `transitions`, `boundaries`, `form_structure_sense`.

Two types get extra prompt handling: `command_of_evidence_quantitative` must restate exact values read off the table or graph before reasoning about them; `transitions` and `boundaries` must name the grammatical relationship between clauses before choosing.

**Starting state.** Greenfield. Nothing is provisioned — no VPS, no OpenRouter key, no BotFather token. Phase 1 has to cover getting those in hand before anything can run end to end.

**Known risks carried into planning:**
- *Latency.* The 30s budget must accommodate six models in one round, two of them frontier (Opus 5, GPT-6 Astra), each generating a full transcription plus four elimination reasons at up to 2000 tokens. The slowest model sets wall time. This is the primary technical risk and wants research before Phase 1 planning.
- *Cost.* Firing both frontier models on every question is the most expensive possible configuration. The global spend cap and its degraded-mode fallback are load-bearing, not nice-to-have.
- *Unmeasured accuracy.* The 90% accuracy bar is a stated goal with no in-v1 measurement, because the eval harness is deferred. Corrections accumulate `ground_truth` so the bar becomes measurable in v2.
- *Model ID drift.* The configured OpenRouter IDs must be verified live at boot; several may not exist under the exact strings specified.

## Constraints

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

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Fire all six models every time; delete the escalation cascade | User wants a frontier model (Opus 5 / GPT-6 Astra) in every answer, not just contested ones. Removes two-round logic, tier resolution, and contamination risk entirely — one round, one tally. Costs the most per question. | — Pending |
| Relax same-lab rule from "one model per lab" to "≥4 distinct labs per round" | Firing all six means Opus 5 + Sonnet 5 (both Anthropic) and GPT-6 + GPT-5.6 (both OpenAI) coexist in one round. Strict one-per-lab is impossible with six models across four labs. Four distinct labs still preserves the diversity the ensemble depends on. | — Pending |
| Defer the eval harness and labeled dataset to v2 | No labeled College Board data exists and hand-labeling isn't wanted now. Shipping a working bot sooner beats shipping an idle harness. Everything still logs to SQLite so eval can be added later against real data. | — Pending |
| Corrections are the labeling pipeline | The "Wrong answer" button writes `ground_truth` during normal use, accumulating a dataset passively. Built in the persistence phase, not last. | — Pending |
| OpenRouter as the single model gateway | One key, one schema, one bill across six models from four labs. The alternative is four separate SDKs and four billing relationships. | — Pending |
| Never assert correctness | The bot reports what models chose and how strongly they agree. Asserting an answer it can't verify is the failure mode the whole design exists to avoid. | — Pending |
| Allowlist-only, no open access | Cost control and abuse prevention for a 10–40 person study group. | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-10 after initialization*
