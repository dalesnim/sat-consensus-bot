# Requirements: SAT Verbal Consensus Bot

**Defined:** 2026-09-10
**Core Value:** Honest confidence signaling — when models unanimously agree the user can trust that; when they split the user must see the split rather than a fabricated single answer.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Configuration & Boot Validation

- [ ] **CFG-01**: Bot loads model roster from `models.yaml` at startup; no model IDs are hardcoded in Python
- [ ] **CFG-02**: Bot fetches `GET /api/v1/models` from OpenRouter at boot and confirms every configured model ID exists, failing loudly and naming the offending ID
- [ ] **CFG-03**: Bot confirms at boot that every configured model advertises image input support, failing loudly and naming the offending ID
- [ ] **CFG-04**: Bot enforces lab diversity at boot — the round must contain at least 4 distinct labs — and refuses to start if violated
- [ ] **CFG-05**: Bot reads all secrets from environment variables only; `.env.example` is shipped and `.env` is never committed
- [ ] **CFG-06**: Bot runs under Docker Compose on a single VPS with a persistent SQLite volume

### Ingestion

- [ ] **ING-01**: User can send a photo of one SAT verbal question and receive a consensus reply
- [ ] **ING-02**: Bot extracts the largest available `PhotoSize` when the image arrives as a photo
- [ ] **ING-03**: Bot extracts raw bytes when the image arrives as a document
- [ ] **ING-04**: Bot tells users to prefer document uploads over photos, because Telegram compression degrades OCR
- [ ] **ING-05**: Bot runs a pre-flight image quality check and warns or rejects images too degraded to read reliably, before spending any inference budget
- [ ] **ING-06**: Bot politely rejects images that are not SAT verbal questions, using the `is_sat_verbal` field in the model contract
- [ ] **ING-07**: Bot rejects screenshots containing more than one question
- [ ] **ING-08**: Bot displays a typing action while inference runs

### Inference

- [ ] **INF-01**: All six configured models fire in parallel on every question — one round, no escalation cascade
- [ ] **INF-02**: Every model receives a byte-identical prompt and the identical image
- [ ] **INF-03**: No model receives any other model's output at any point
- [ ] **INF-04**: The shared prompt requires verbatim transcription of the passage and all four choices before any reasoning
- [ ] **INF-05**: The shared prompt requires an explicit verdict for every one of the four choices, forbidding answer selection without eliminating the other three
- [ ] **INF-06**: The shared prompt requires restating exact values read off tables or graphs for `command_of_evidence_quantitative` questions
- [ ] **INF-07**: The shared prompt requires naming the grammatical relationship between clauses for `transitions` and `boundaries` questions
- [ ] **INF-08**: The shared prompt requires answers supported by the text only, with no outside knowledge, and JSON output only
- [ ] **INF-09**: `reasoning.effort` is forced to none/minimal on every model call, so the 30 second budget holds
- [ ] **INF-10**: Each model call has its own timeout; a single slow or failed model cannot take down the round
- [ ] **INF-11**: Each model response is validated against the strict JSON contract with pydantic v2
- [ ] **INF-12**: A parse failure triggers exactly one repair retry scoped to syntax extraction only, so the repair cannot change the model's answer
- [ ] **INF-13**: A model that still fails after the repair retry is recorded as abstaining for that question
- [ ] **INF-14**: Two or more abstentions in a round visibly degrades the confidence reported to the user
- [ ] **INF-15**: A question is classified into one of the eleven College Board question types

### Consensus Reporting

- [ ] **CON-01**: Bot tallies all six votes and states the split in a header line
- [ ] **CON-02**: Bot reports the number of distinct labs represented within the majority alongside the vote count
- [ ] **CON-03**: 6/6 or 5/1 reports as strong agreement with merged reasoning
- [ ] **CON-04**: 4/2 reports as majority and contested, showing both sides' elimination reasoning
- [ ] **CON-05**: 3/3 or worse reports as unresolved, showing every distinct position and advising the user to ask a teacher
- [ ] **CON-06**: Reasoning appears first in the reply; the consensus letter appears last inside a MarkdownV2 spoiler
- [ ] **CON-07**: Bot never asserts a correct answer — replies state only what the models chose
- [ ] **CON-08**: All model-generated text is escaped for MarkdownV2 so a formatting character cannot cause the reply to fail to send
- [ ] **CON-09**: Replies exceeding Telegram's message length limit are paginated rather than truncated or dropped

### Interaction

- [ ] **UX-01**: User can press "Full breakdown" to see per-model, per-choice reasoning
- [ ] **UX-02**: User can press "Wrong answer" to submit a correction
- [ ] **UX-03**: Correction input uses structured A/B/C/D buttons rather than free text, protecting `ground_truth` from malformed input
- [ ] **UX-04**: A submitted correction is written to the `ground_truth` column for that question
- [ ] **UX-05**: `/help` explains what the bot does, how to photograph a question, and why it never states a correct answer

### Caching & Persistence

- [ ] **DATA-01**: Bot computes a perceptual hash of every submitted image at `hash_size=16`
- [ ] **DATA-02**: An exact perceptual hash match returns the stored result with no inference; no fuzzy Hamming-distance matching in v1
- [ ] **DATA-03**: Every question is persisted with its hash, image file id, question type, consensus answer, consensus state, ground truth, and user
- [ ] **DATA-04**: Every model attempt is persisted with model id, answer, confidence, raw JSON, latency, token counts, computed cost, and error
- [ ] **DATA-05**: Replies served from cache are flagged as such in persistence
- [ ] **DATA-06**: Cross-model transcription divergence is logged, so correlated OCR hallucination is detectable after the fact

### Access & Cost Control

- [ ] **ACC-01**: Only users on the allowlist can use the bot
- [ ] **ACC-02**: `OWNER_ID` can add users via `/adduser`
- [ ] **ACC-03**: Each user has a daily question cap, default 40
- [ ] **ACC-04**: A global daily spend cap is read from the environment and enforced atomically, so concurrent requests cannot race past it
- [ ] **ACC-05**: Above the spend cap the bot drops to a reduced cheaper model set and says so in the reply
- [ ] **ACC-06**: `OWNER_ID` can run `/cost` to see spend today, this week, and per question

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Evaluation

- **EVAL-01**: `eval run` scores every labeled question against every configured model individually
- **EVAL-02**: `eval report` prints per-model accuracy overall and by question type
- **EVAL-03**: `eval report` prints ensemble accuracy versus the best single model
- **EVAL-04**: `eval report` prints accuracy when unanimous, quantifying how far 6/6 can be trusted
- **EVAL-05**: `eval report` prints the unanimous-but-wrong rate by question type; types above a few percent get a warning line added to the bot's replies
- **EVAL-06**: Accuracy is measured against a 90% absolute bar
- **EVAL-07**: Dataset is sourced from `ground_truth` accumulated by the correction flow, and from official College Board practice tests — never synthesized

### Caching

- **CACHE-01**: Fuzzy perceptual hash matching with a threshold tuned empirically against real user photos

### Consensus

- **CONS-01**: Self-consistency resampling, revisited once eval data shows whether failures are dominated by reasoning errors or image quality

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| SAT Math section | Verbal is the target; math has different failure modes and prompt requirements |
| Routing to a single "best" model | Defeats the premise — the ensemble is the product |
| Escalation / two-tier cascade | Dropped at initialization; all six models fire every round instead |
| Multi-question screenshots | Rejected at ingestion; one question per image keeps the contract clean |
| Conversation memory | Each question is independent; state invites contamination between questions |
| Web UI | Telegram is the interface |
| Any claim of knowing the correct answer | The bot reports model choices and agreement, never ground truth |
| LangChain or any orchestration framework | Direct httpx against OpenRouter's OpenAI-compatible schema is sufficient and keeps the dependency surface small |
| Per-model confidence numbers shown to users | Verbalized LLM confidence is measurably miscalibrated and saturates near 80-100% regardless of difficulty; agreement is the only honest signal |
| Streaming responses | The bot needs a complete valid JSON object before it can validate and tally; SSE adds complexity without reducing total latency |
| Eval harness in v1 | No labeled dataset exists and hand-labeling is not wanted now; corrections accumulate `ground_truth` for v2 |
| Synthesized practice questions | Any future dataset seeds from official College Board practice tests only |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CFG-01 | Phase 1 | Pending |
| CFG-02 | Phase 1 | Pending |
| CFG-03 | Phase 1 | Pending |
| CFG-04 | Phase 1 | Pending |
| CFG-05 | Phase 1 | Pending |
| CFG-06 | Phase 1 | Pending |
| ING-01 | Phase 1 | Pending |
| ING-02 | Phase 1 | Pending |
| ING-03 | Phase 1 | Pending |
| ING-04 | Phase 1 | Pending |
| ING-05 | Phase 1 | Pending |
| ING-06 | Phase 1 | Pending |
| ING-07 | Phase 1 | Pending |
| ING-08 | Phase 3 | Pending |
| INF-01 | Phase 1 | Pending |
| INF-02 | Phase 1 | Pending |
| INF-03 | Phase 1 | Pending |
| INF-04 | Phase 1 | Pending |
| INF-05 | Phase 1 | Pending |
| INF-06 | Phase 1 | Pending |
| INF-07 | Phase 1 | Pending |
| INF-08 | Phase 1 | Pending |
| INF-09 | Phase 1 | Pending |
| INF-10 | Phase 1 | Pending |
| INF-11 | Phase 1 | Pending |
| INF-12 | Phase 1 | Pending |
| INF-13 | Phase 1 | Pending |
| INF-14 | Phase 1 | Pending |
| INF-15 | Phase 1 | Pending |
| CON-01 | Phase 1 | Pending |
| CON-02 | Phase 1 | Pending |
| CON-03 | Phase 1 | Pending |
| CON-04 | Phase 1 | Pending |
| CON-05 | Phase 1 | Pending |
| CON-06 | Phase 1 | Pending |
| CON-07 | Phase 1 | Pending |
| CON-08 | Phase 3 | Pending |
| CON-09 | Phase 3 | Pending |
| UX-01 | Phase 3 | Pending |
| UX-02 | Phase 3 | Pending |
| UX-03 | Phase 3 | Pending |
| UX-04 | Phase 3 | Pending |
| UX-05 | Phase 3 | Pending |
| DATA-01 | Phase 2 | Pending |
| DATA-02 | Phase 2 | Pending |
| DATA-03 | Phase 2 | Pending |
| DATA-04 | Phase 2 | Pending |
| DATA-05 | Phase 2 | Pending |
| DATA-06 | Phase 2 | Pending |
| ACC-01 | Phase 2 | Pending |
| ACC-02 | Phase 2 | Pending |
| ACC-03 | Phase 2 | Pending |
| ACC-04 | Phase 2 | Pending |
| ACC-05 | Phase 2 | Pending |
| ACC-06 | Phase 2 | Pending |

**Coverage:**
- v1 requirements: 55 total
- Mapped to phases: 55
- Unmapped: 0 ✓

---
*Requirements defined: 2026-09-10*
*Last updated: 2026-09-10 after roadmap creation*
