---
phase: 01-core-inference-loop
plan: 04
subsystem: api
tags: [consensus, aiogram, pydantic, tally, reply-formatting]

requires:
  - phase: 01-core-inference-loop
    provides: "AttemptResult, ConsensusResult, Position, ConsensusTier, RejectionReason from orchestrator/contract.py; build_reply/build_rejection signatures; formatting/reply.py stub"
provides:
  - "Pure tally(results, *, min_valid=3) -> ConsensusResult over AttemptResult lists, no I/O"
  - "Tier-aware build_reply() rendering strong/contested/unresolved/insufficient with spoiler-last letter placement or no letter at all"
  - "Cross-lab transcription divergence detection via normalized Jaccard token overlap, logged as WARNING with model IDs and score only"
  - "Modal question_type extraction with tie-breaking to None"
affects: [06-consensus-and-live-round]

tech-stack:
  added: []
  patterns:
    - "consensus.py is a pure module (no aiogram/httpx/bot.config imports, single module logger only) so plan 06 can call tally() from the live fan-out without pulling in Telegram or HTTP dependencies"
    - "reply.py builds every message as a flat list of str/Bold/Spoiler nodes passed to Text(*nodes) — never a hand-assembled MarkdownV2 string — so LLM-generated punctuation renders literally and cannot break delivery or impersonate bot chrome"
    - "Footer (photo nudge) is always inserted before the spoiler block so the consensus letter is structurally guaranteed to be the final content in strong/contested replies"

key-files:
  created:
    - src/bot/orchestrator/consensus.py
    - tests/test_consensus.py
    - tests/test_reply.py
  modified:
    - src/bot/formatting/reply.py

key-decisions:
  - "Tier boundary uses top.votes/total_valid >= 5/6 OR top.votes == total_valid for strong, top.votes > total_valid/2 for contested, everything else (including any tie at the top) is unresolved — matches CONTEXT.md's 6/0, 5/1 = strong; 4/2 = contested; 3/3 and flatter = unresolved exactly"
  - "labs_in_majority is scoped to distinct labs among the winning position's voters only when a winner exists; falls back to distinct labs across all ok results for unresolved/insufficient, since there is no majority to scope to"
  - "Reasoning dedup is case-insensitive on stripped text, first-seen order preserved, so two models phrasing the same elimination identically only appears once in the merged strong-tier body"
  - "Transcription divergence threshold is a fixed 0.9 Jaccard token overlap on lab-distinct pairs only (same-lab pairs skipped, since correlated hallucination within one lab's models isn't independent evidence either way) — computed and logged in this phase per PROJECT.md's passive-instrumentation requirement, not yet surfaced in the reply body"
  - "Strong-tier body caps merged reasoning at four bulleted lines; contested/unresolved show each position's full reasoning list under a Bold '{letter} — {votes} models' label, since those tiers are lower-volume (2-4 positions vs. one merged block)"
  - "insufficient tier's apology text names the actual total_valid count out of 6 rather than a generic message, since the plan's action block specifies this exact copy"

patterns-established:
  - "TDD RED/GREEN commit pairs per task: test(01-04) commit fails against the pre-existing plan-01 stub or missing module, feat(01-04) commit makes it pass — both tasks in this plan followed this gate"
  - "Reply body construction is a list-of-nodes builder (_position_block, _bulleted_lines helpers) rather than string concatenation, so Bold/Spoiler entities compose correctly through aiogram's Text(*nodes) tree renderer"

requirements-completed: [ING-04, INF-14, CON-01, CON-02, CON-03, CON-04, CON-05, CON-06, CON-07]

duration: ~15min
completed: 2026-09-10
---

# Phase 1 Plan 4: Consensus Tally and Tier-Aware Reply Summary

**Pure vote-tallying module (`orchestrator/consensus.py`) turning six `AttemptResult`s into a tiered `ConsensusResult` with lab-spread-aware majority scoping and cross-lab transcription-divergence logging, plus a rewritten `formatting/reply.py` that renders each tier's exact header/body/spoiler-placement rules using only aiogram `Text`/`Bold`/`Spoiler` entities.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-09-10T21:08:00+05:00 (approx, context load)
- **Completed:** 2026-09-10T21:16:00+05:00
- **Tasks:** 2 (both TDD, each with a RED test commit and a GREEN implementation commit)
- **Files modified:** 3 created, 1 modified

## Accomplishments
- `tally()` correctly classifies every tier boundary the CONTEXT.md decisions specify: 6/0 and 5/1 as `strong`, 4/2 as `contested`, 3/3 and any tie-at-top (including 2/2/1/1) as `unresolved` with no winning letter, and anything below 3 valid responses as `insufficient` before any vote math runs
- `labs_in_majority` counts distinct labs among the winning position's voters only — a 5/6 split concentrated in two labs now reports differently from one spanning four, directly implementing the Apple ML Research "Nine Judges, Two Effective Votes" lab-spread finding from PROJECT.md
- Cross-lab transcription divergence is computed via normalized Jaccard token overlap (threshold 0.9) on every lab-distinct `ok` pair and logged as a WARNING naming the two model IDs and the score — never the transcription text itself (T-04-03)
- `build_reply()` renders all four tiers to spec: `strong` shows up to four bulleted merged-reasoning lines with the letter alone in a trailing spoiler; `contested` shows both sides' reasoning under Bold labels before the spoiler; `unresolved` shows every position and a teacher-referral line with zero spoiler entities anywhere; `insufficient` is a plain apology naming how many of six models answered
- Every reply is built from `Text`/`Bold`/`Spoiler` entity nodes rather than interpolated MarkdownV2 strings, so a reasoning string containing all of MarkdownV2's reserved characters plus a bare backslash renders without raising and survives verbatim in the message text (T-04-01)
- `pytest tests/ -q` — 55 tests total, all green; `pytest tests/test_end_to_end.py -q` (plan 01's assertions) still passes unmodified after the `reply.py` rewrite

## Task Commits

1. **Task 1: Consensus tally** - `4aeaf7f` (test, RED — 18 tests against a module that doesn't exist yet) then `4b304f4` (feat, GREEN — all 18 pass)
2. **Task 2: Tier-aware reply rendering** - `7d35d92` (test, RED — 4 of 20 tests fail against the plan-01 stub's bullet-less body, missing Bold entities, and generic apology text) then `c119b35` (feat, GREEN — all 20 pass)

**Plan metadata:** pending (docs: complete plan, committed after this summary)

## Files Created/Modified
- `src/bot/orchestrator/consensus.py` - `MIN_VALID_RESPONSES_DEFAULT = 3`, `tally()`; pure module, no aiogram/httpx/bot.config imports
- `tests/test_consensus.py` - 18 tests covering every tier boundary from 6/0 through 2/2/1/1, the abstention floor, labs-in-majority scoping, reasoning dedup, transcription divergence, and modal question_type
- `src/bot/formatting/reply.py` - rewritten `build_reply()` body/header construction per tier; `build_rejection()` left intact from plan 01
- `tests/test_reply.py` - 20 tests covering exact headers, spoiler-last placement and offset, Bold entity labels, the four-line bullet cap, degraded header suffix, photo/document footer toggle, adversarial MarkdownV2-reserved-character punctuation, and a module-source scan for the four forbidden phrases

## Decisions Made
- Tier math: `strong` when `top/total_valid >= 5/6` or `top == total_valid`; `contested` when `top > total_valid/2` and not `strong`; a tie between the top two positions always forces `unresolved` regardless of ratio, so 3/3 (and any flatter split) never produces a winning letter even if some other arithmetic path would have called it close to a majority.
- `labs_in_majority` falls back to the count of distinct labs across all `ok` results when there is no winner (unresolved/insufficient), since "majority" has no meaning to scope to in that case.
- Strong-tier reasoning is capped at four bulleted lines (merged block); contested and unresolved show each position's full reasoning list, since those tiers only ever have 2-4 positions rather than one large merged set.
- The photo-source footer is always inserted into the node list before the spoiler block is appended, structurally guaranteeing the consensus letter is the last content in the message regardless of footer presence.

## Deviations from Plan

None - plan executed exactly as written. The two TDD tasks each followed the RED/GREEN gate: the consensus RED commit failed on `ModuleNotFoundError` (the module didn't exist), and the reply RED commit was strengthened past its first pass-on-first-try draft — see below.

### Process note (not a deviation, but worth recording)

My first draft of `tests/test_reply.py` passed 16/16 against the pre-existing plan-01 `reply.py` stub without any implementation changes, which the TDD fail-fast rule flags as a signal to investigate rather than proceed. I added four more specific tests (four-line bullet cap with exact bullet text, Bold entity labels for contested/unresolved position headers, and the exact `insufficient` apology wording) that correctly failed against the stub (4/20), confirming true RED before writing the GREEN implementation.

---
**Total deviations:** 0
**Impact on plan:** None.

## Issues Encountered
- No `.venv` existed in this worktree (worktrees don't share a virtualenv with the main checkout, and referencing the main checkout's `.venv` by absolute path was blocked by the worktree-isolation sandbox). Created a local `.venv` inside the worktree via `python3.12 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"`. `.venv/` is already gitignored from plan 01, so this has no effect on the committed repository.

## User Setup Required

None - no external service configuration required. All 55 tests run with no credentials present and make no network calls.

## Next Phase Readiness
- `tally()` and `build_reply()` are the two functions plan 06 will call directly: `tally(results)` on the six `AttemptResult`s from the live fan-out, then `build_reply(consensus_result, source_is_photo=...)` — no signature changes needed on either side.
- `formatting/reply.py`'s public signatures (`build_reply`, `build_rejection`) remain byte-identical to plan 01, so `handlers/ingest.py` and `pipeline.py` need no changes to consume this plan's output once plan 06 replaces `pipeline._STUB_CONSENSUS` with a real `tally()` call.
- `transcription_divergence` is computed and logged but not yet surfaced in the reply body, per PROJECT.md's phased instrumentation plan — this is intentional groundwork for the deferred eval harness, not a gap in this plan's scope.
- No blockers.

---
*Phase: 01-core-inference-loop*
*Completed: 2026-09-10*

## Self-Check: PASSED

All 5 created/modified files verified present on disk; all 4 commit hashes (4aeaf7f, 4b304f4, 7d35d92, c119b35) verified present in `git log`.
