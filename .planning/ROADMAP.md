# Roadmap: SAT Verbal Consensus Bot

## Overview

Three phases, each a vertical slice. Phase 1 builds the entire core loop — a user sends a photo, six models fire in parallel under a forced-low-reasoning-effort budget, and a real consensus reply comes back — and absorbs essentially all of the project's technical risk (model ID correctness, latency, JSON contract compliance, per-model failure isolation, boot-time validation) in one place, because nothing else is buildable or verifiable until one photo reliably produces one tallied reply within 30 seconds. Phase 2 adds the policy and data layer on top of that working round: perceptual-hash caching, full persistence, spend accounting, and access control — all of which need real `attempts` rows to operate against, so they follow rather than lead. Phase 3 is user-facing polish with no new architectural risk: onboarding, the full-breakdown and correction buttons, adversarial-safe MarkdownV2 escaping, and message pagination.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Core Inference Loop** - A user can send a photo of an SAT verbal question and get a real six-model consensus reply within the latency budget
- [ ] **Phase 2: Persistence, Caching & Cost Control** - The bot remembers every question and attempt, skips re-paying for duplicate images, and stays within budget and allowlist
- [ ] **Phase 3: Interaction & Consensus Reporting Polish** - The bot is fully usable and trustworthy for a study group — onboarding, breakdowns, corrections, and reliable message delivery

## Phase Details

### Phase 1: Core Inference Loop

**Goal**: **As a** student practicing SAT Reading & Writing, **I want to** send a photo of one question to a Telegram bot, **so that** I can see how six independent frontier models split on it and why, without ever being told a fabricated single answer.

**Detail**: A user can send a photo of one SAT verbal question and receive an honest, six-model consensus reply — reasoning first, letter last — within the 30-second budget. This phase absorbs the project's technical risk: boot-time validation against OpenRouter's live model catalog (using the corrected roster where `deepseek/deepseek-v4` is `deepseek/deepseek-v4.1-flash`), forcing `reasoning.effort` to none/minimal on every call as the load-bearing latency mitigation, an early empirical spike firing all six models once with the real prompt to log actual completion tokens and wall-clock time before locking `max_tokens` or trusting the 30s budget, per-model timeouts with failure isolation inside each coroutine (never delegated to `gather`'s `return_exceptions`), and the pre-flight image quality gate running before any inference spend.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: CFG-01, CFG-02, CFG-03, CFG-04, CFG-05, CFG-06, ING-01, ING-02, ING-03, ING-04, ING-05, ING-06, ING-07, INF-01, INF-02, INF-03, INF-04, INF-05, INF-06, INF-07, INF-08, INF-09, INF-10, INF-11, INF-12, INF-13, INF-14, INF-15, CON-01, CON-02, CON-03, CON-04, CON-05, CON-06, CON-07
**Success Criteria** (what must be TRUE):

  1. User can send a photo or document of one SAT verbal question and receive a reply showing the vote split and reasoning within roughly 30 seconds.
  2. When models disagree, the user sees the actual split (e.g. "4/2, majority contested") with elimination reasoning from both sides, spanning labs, rather than a single fabricated answer.
  3. If the image is unreadable, not an SAT verbal question, or contains more than one question, the user gets a clear rejection message before any model is called.
  4. If one or more models time out or fail to produce valid JSON, the reply still arrives on time, showing visibly degraded confidence rather than an error or a hang.
  5. The bot refuses to start, naming the offending model ID, if any configured model doesn't exist on OpenRouter, lacks image support, or if the roster spans fewer than 4 distinct labs.

**Plans:** 6/7 plans executed

Plans:

- [x] 01-01-PLAN.md — Walking Skeleton: scaffold, JSON contract, shared prompt, photo-in/reply-out with a stubbed round
- [x] 01-02-PLAN.md — models.yaml roster, typed settings, live boot validation, Docker Compose packaging
- [x] 01-03-PLAN.md — Telegram file selection, byte ceiling, pre-flight resolution and blur quality gate
- [x] 01-04-PLAN.md — Consensus tally with lab spread and abstention degradation, tier-aware reply rendering
- [x] 01-05-PLAN.md — Six-way parallel fan-out, forced-low reasoning effort, per-model timeout, syntax-only repair retry
- [x] 01-06-PLAN.md — Real pipeline wiring plus the not-SAT-verbal, multi-question, and too-few-voters rejection branches
- [ ] 01-07-PLAN.md — Empirical latency spike, credential provisioning, first live round

### Phase 2: Persistence, Caching & Cost Control

**Goal**: Every question and model attempt is durably recorded, duplicate images short-circuit to a cached answer with no new spend, and the bot stays within its budget and its allowlist as real usage accrues.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, ACC-01, ACC-02, ACC-03, ACC-04, ACC-05, ACC-06
**Success Criteria** (what must be TRUE):

  1. Re-sending the exact same image returns the stored result instantly, with no new model calls and no new cost.
  2. Every question, model attempt, and user is persisted with enough detail (hash, tokens, latency, cost, errors, cache flag, transcription) to audit what happened after the fact.
  3. Only allowlisted users can use the bot, and each user is capped at a daily question count (default 40).
  4. When the global daily spend cap is hit, the bot automatically drops to a reduced cheaper model set for subsequent questions and says so in the reply.
  5. The owner can run `/cost` to see spend today, this week, and per question, and can run `/adduser` to add new allowlisted users.

**Plans:** 2/5 plans executed

Plans:

- [x] 02-01-PLAN.md — SQLite foundation: schema, shared WAL connection, and every question and attempt persisted on the live path
- [ ] 02-02-PLAN.md — Exact 256-bit perceptual-hash cache, zero-cost repeat answers, cache-hit audit rows
- [x] 02-03-PLAN.md — Allowlist paywall, atomic per-user daily cap, owner-only /adduser
- [ ] 02-04-PLAN.md — Atomic global spend cap with reduced cheaper model set and in-reply disclosure
- [ ] 02-05-PLAN.md — /cost unit-economics report plus live end-to-end verification of the phase

### Phase 3: Interaction & Consensus Reporting Polish

**Goal**: The bot is fully usable and trustworthy end-to-end for a study group — new users can onboard themselves, every reply reliably reaches Telegram regardless of what the models generated, and users can drill into a full breakdown or correct a wrong answer.
**Mode:** mvp
**Depends on**: Phase 1, Phase 2
**Requirements**: ING-08, CON-08, CON-09, UX-01, UX-02, UX-03, UX-04, UX-05
**Success Criteria** (what must be TRUE):

  1. New users can run `/help` and understand what the bot does, how to photograph a question, and why it never states a correct answer.
  2. User can press "Full breakdown" to see every model's per-choice reasoning, correctly paginated when it exceeds Telegram's message length limit.
  3. User can press "Wrong answer" and submit the correct letter via A/B/C/D buttons, which is written to `ground_truth` for that question.
  4. No reply ever fails to send because of an unescaped formatting character in model-generated text, and a typing indicator is visible while inference runs.

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Inference Loop | 7/7 | Complete | 2026-09-10 |
| 2. Persistence, Caching & Cost Control | 2/5 | In Progress|  |
| 3. Interaction & Consensus Reporting Polish | 0/TBD | Not started | - |
