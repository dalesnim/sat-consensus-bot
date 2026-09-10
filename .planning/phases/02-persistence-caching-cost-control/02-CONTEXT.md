# Phase 2: Persistence, Caching & Cost Control - Context

**Gathered:** 2026-09-11
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Every question and model attempt is durably recorded, duplicate images short-circuit to a cached answer with no new spend, and the bot stays within its budget and its allowlist as real usage accrues.

Requirements: DATA-01 through DATA-06, ACC-01 through ACC-06.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Locked by the owner (from .planning/OVERNIGHT-HANDOFF.md)
- Quality over cost: the roster is not trimmed to save money. It was chosen on measured accuracy against a 17-question labeled set.
- Manual allowlist only. No access codes, no payment integration.
- No spend cap *value* was chosen ("no cap"), but 02-04 still BUILDS the cap mechanism. Build it; leave the env value unset or high.
- The bot must never claim correctness. Unanimity is reported as agreement, never as a correct answer.

### Money guard (from CLAUDE.md)
No code path that calls `/chat/completions` may run during this phase. All tests mock httpx at the transport layer. `python -m bot --validate-only` is free and permitted.

</decisions>

<code_context>
## Existing Code Insights

Phase 1 is complete and live. 02-01 (SQLite foundation, shared WAL connection, questions + attempts persistence) and 02-03 (allowlist, per-user daily cap, /adduser) are already executed and summarised. Remaining: 02-02 (phash cache), 02-04 (spend cap + reduced set), 02-05 (/cost report + live verification).

`usage.cost` is confirmed present at that exact JSON path across three live spike runs — 02-04 and 02-05 spend accounting can rely on it (see 01-07-SUMMARY.md).

</code_context>

<specifics>
## Specific Ideas

No additional requirements — discuss phase skipped. The five PLAN.md files in this directory are the spec.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
