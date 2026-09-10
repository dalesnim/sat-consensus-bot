# Phase 3: Interaction & Consensus Reporting Polish - Context

**Gathered:** 2026-09-11
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

The bot is fully usable and trustworthy end-to-end for a study group — new users can onboard themselves, every reply reliably reaches Telegram regardless of what the models generated, and users can drill into a full breakdown or correct a wrong answer.

Requirements: ING-08, CON-08, CON-09, UX-01, UX-02, UX-03, UX-04, UX-05.

Success criteria:
1. New users can run `/help` and understand what the bot does, how to photograph a question, and why it never states a correct answer.
2. User can press "Full breakdown" to see every model's per-choice reasoning, correctly paginated when it exceeds Telegram's message length limit.
3. User can press "Wrong answer" and submit the correct letter via A/B/C/D buttons, which is written to `ground_truth` for that question.
4. No reply ever fails to send because of an unescaped formatting character in model-generated text, and a typing indicator is visible while inference runs.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting. Use the ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Locked by the owner (from .planning/OVERNIGHT-HANDOFF.md and PROJECT.md)
- The bot must never claim correctness. Unanimity is reported as agreement, never as a correct answer. `/help` must say this explicitly (UX-05).
- The correction flow (UX-02/03/04) is the sole v1 labeling mechanism — the eval harness was deferred to v2. `ground_truth` accuracy therefore matters: structured A/B/C/D buttons only, never free text.
- Manual allowlist only. `/help` must not imply open registration.

### Money guard (from CLAUDE.md)
No code path that calls `/chat/completions` may run during this phase. All tests mock httpx at the transport layer. `python -m bot --validate-only` is free and permitted.

</decisions>

<code_context>
## Existing Code Insights

Phases 1 and 2 are the substrate. Relevant already-built pieces:

- **ING-08 (typing indicator) already shipped early** — delivered ahead of this phase in commit `23865cf`. Planning should verify rather than rebuild it.
- `src/bot/formatting/reply.py` owns reply rendering (`build_reply`, `build_rejection`). CON-06/CON-07 are already satisfied there: reasoning first, letter last inside a MarkdownV2 spoiler, never an assertion of correctness. CON-08 (escaping) and CON-09 (pagination) extend this module.
- `src/bot/handlers/ingest.py` already has a `TelegramBadRequest` → plain-text fallback on send. CON-08 should make that fallback unreachable for formatting reasons rather than replace it.
- `src/bot/db/questions.py` holds the `ground_truth` column that UX-04 writes to; 02-01 established the persistence layer and 02-02 adds the cache lookup.
- `src/bot/handlers/owner.py` is the existing pattern for command handlers (`/adduser`, `/pause`, `/resume`, `/status`, `/cost`).
- Per-model verdicts with per-choice elimination reasoning are already captured and persisted as `attempts` rows — UX-01's "Full breakdown" reads existing data rather than requiring new inference.

Test conventions: `tests/` mocks httpx at the transport layer; verdict JSON builders live in `tests/fixtures/verdicts.py`. Baseline is 189 tests passing and `ruff check .` clean.

</code_context>

<specifics>
## Specific Ideas

No additional requirements — discuss phase skipped. The ROADMAP phase description and the eight requirement IDs are the spec.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
