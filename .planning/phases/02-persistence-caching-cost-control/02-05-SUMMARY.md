---
phase: 02-persistence-caching-cost-control
plan: 05
subsystem: cost-reporting

tags: [aiosqlite, aiogram, cost-report, owner-command, checkpoint-blocked]

# Dependency graph
requires:
  - phase: 02-persistence-caching-cost-control
    provides: "02-02: served_from_cache flag; 02-03: owner router + _is_owner re-check pattern; 02-04: spend_days ledger via day_totals-equivalent columns"
provides:
  - "src/bot/cost/report.py: CostReport, build_cost_report(conn, *, cap_usd, now) — spend/volume aggregates over questions/attempts/spend_days"
  - "src/bot/handlers/owner.py: /cost command, owner-only, renders CostReport as Bold-header Text nodes"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Clock injected as a `now: datetime` parameter rather than read inside build_cost_report, so day-boundary behavior is testable without freezing the system clock"
    - "UTC day key derived via now.strftime('%Y-%m-%d') and matched against questions.created_at with substr(created_at, 1, 10) = ?, never a date-range function, since created_at is a UTC ISO-8601 string"
    - "owner.py's _send widened from str-only to str | Text so a single send helper serves both plain-string replies (existing commands) and the new multi-node Bold-header /cost reply, matching the Text-accepting _send already used in handlers/ingest.py"

key-files:
  created:
    - src/bot/cost/report.py
    - tests/test_cost_report.py
  modified:
    - src/bot/handlers/owner.py
    - README.md

key-decisions:
  - "cache_hit_rate_today is returned as an already-scaled percentage (0-100), not a 0-1 fraction, so the handler can render it directly as f'{value:.1f}%' per the plan's literal reply-format spec ('{cache_hit_rate_today}%)')"
  - "_send in owner.py changed from `text: str` to `content: str | Text` (isinstance check wraps plain strings in Text as before) rather than adding a second send function, keeping one send path for all six owner commands and matching the pattern already established in handlers/ingest.py"
  - "Both Task 1 and Task 2 RED phases were verified honestly: the implementation file was moved aside (Task 1) or reverted via `git checkout -- <file>` (Task 2, since the /cost handler was additive to an already-committed file) immediately before running pytest, confirming a real collection/import failure, before being restored for the GREEN run — not just written as if TDD had been followed"

requirements-completed: []

# Metrics
duration: 12min
completed: 2026-09-10
---

# Phase 2 Plan 5: /cost Command and Operator Documentation Summary (Tasks 1-2 complete; Task 3 blocked on human checkpoint)

**`build_cost_report` aggregates spend-today, spend-this-week, question/cache/reduced-round counts, and cost-per-question (today and all-time) from `questions`/`attempts`/`spend_days` with an injectable clock and zero division-by-zero holes; `/cost` renders it to the owner alone as a UTC-labeled, four-decimal-place Telegram reply. The plan's Task 3 — ten-step live verification against the running bot and real Telegram/OpenRouter traffic — was correctly NOT attempted by this agent and remains an outstanding human checkpoint.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-09-10T20:50:00Z
- **Completed (Tasks 1-2):** 2026-09-10T21:00:00Z (approx)
- **Tasks:** 2 of 3 completed (Task 3 is a blocking human-verify checkpoint, not attempted)
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- `src/bot/cost/report.py`: `CostReport` frozen dataclass and `build_cost_report(conn, *, cap_usd, now)`. Derives the UTC day key from the injected `now`, sums `spend_days.actual_usd` over the trailing 7-day window (`WHERE day BETWEEN ? AND ?`), counts `questions` rows via `substr(created_at, 1, 10) = ?` (including cache-served rows in the total, isolating `served_from_cache = 1` for the hit count), and computes `cost_per_question_all_time` from `SUM(attempts.cost_usd)` divided by the count of non-cache-served `questions` rows — all guarded against zero denominators, all parameters bound with `?`.
- `src/bot/handlers/owner.py`: `@router.message(Command("cost"))` handler, gated by the same `_is_owner` inline re-check used by `/pause`/`/resume`/`/status`. On success it calls `build_cost_report(deps.db, cap_usd=deps.settings.daily_spend_cap_usd, now=datetime.now(UTC))` and renders a `Bold`-headed, four-decimal-place multi-line reply (today's spend/cap/reservation, last-7-days spend, question/cache/reduced-round counts with hit-rate percentage, cost per question today and all-time, and a closing "Daily figures reset at 00:00 UTC." line). Non-owner and `OWNER_ID`-unset callers get the identical generic invite-only refusal used elsewhere, with no numbers or `$` characters.
- `README.md` gained an Operations section: the six operator-relevant env vars (`OWNER_ID`, `ALLOWED_USER_IDS`, `PER_USER_DAILY_CAP`, `DAILY_SPEND_CAP_USD`, `ROUND_COST_SAFETY_MULTIPLIER`, `DB_PATH`), the `/adduser` and `/cost` commands, the UTC daily-boundary note, the `sqlite_data` Docker volume persistence note, and an example `sqlite3` audit query for `served_from_cache = 1` rows.
- 246 tests passing (up from a 229 baseline; 17 new tests: 12 for `build_cost_report`, 5 for the `/cost` handler), Ruff clean, zero live OpenRouter calls made — every new test mocks or bypasses the network entirely (the handler tests construct a real `httpx.AsyncClient` but never call `.post`/`.get` against it).

## Task Commits

Each of Tasks 1 and 2 was committed as a RED/GREEN TDD pair, with RED honestly verified (implementation moved aside or the target file reverted with `git checkout -- <file>` immediately before running pytest, to confirm a real failure, then restored for GREEN) rather than assumed:

1. **Task 1: cost aggregates over the persisted rows**
   - `d804697` test: add failing tests for cost aggregates
   - `922aa5f` feat: implement cost aggregates over persisted rows
2. **Task 2: the /cost command and operator documentation**
   - `860225d` test: add failing tests for the /cost handler
   - `6b5787c` feat: add /cost command and operator documentation

**Task 3 (checkpoint:human-verify, gate="blocking"): NOT attempted.** See "Outstanding: Task 3 — Live Verification" below.

## Files Created/Modified

- `src/bot/cost/report.py` — `CostReport`, `build_cost_report(conn, *, cap_usd: float, now: datetime) -> CostReport`
- `src/bot/handlers/owner.py` — `_cost_report_nodes(report)`, `handle_cost` on `Command("cost")`; `_send` widened to `content: str | Text`
- `tests/test_cost_report.py` — new module: 12 `build_cost_report` behavior tests (empty DB, spend today/week, question/cache/reduced counts, day-boundary exclusion, cost-per-question today and all-time, zero-denominator guards) + 5 `/cost` handler tests (owner success, UTC substring, non-owner refusal with no `$`, `OWNER_ID`-unset refusal, empty-database zeroed reply)
- `README.md` — new Operations section (env var table, owner commands, UTC boundary note, Docker volume note, cache-audit `sqlite3` query)

## Decisions Made

See `key-decisions` in frontmatter. Notably: `cache_hit_rate_today` is pre-scaled to 0-100 (not 0-1) so the handler's `f"{value:.1f}%"` matches the plan's literal reply format without a second conversion at the call site; `_send` in `owner.py` was widened rather than duplicated, to keep one send path for all owner commands.

## Deviations from Plan

None — Tasks 1 and 2 executed exactly as written. No Rule 1-4 deviations were needed; the existing `_is_owner`/`_send` helpers and `Deps`/roster fixtures from 02-03 and 02-04 covered every interface the plan assumed.

## Requirements

`ACC-06` ("`/cost` command for `OWNER_ID` showing today, this week, and cost per question") is **implemented and covered by automated tests** but is **not marked complete in REQUIREMENTS.md** by this agent. The plan's own `<success_criteria>` ties this plan's completion to "every Phase 2 requirement is confirmed against the live bot," which is exactly what the blocked Task 3 checkpoint verifies. Marking `ACC-06` complete before that live confirmation would overstate what has actually been validated. Recommend marking it complete only after Task 3 is approved.

## Outstanding: Task 3 — Live Verification (checkpoint:human-verify, gate="blocking")

**This agent did not attempt, simulate, or fabricate results for Task 3.** It requires driving the live bot from a real Telegram client and real OpenRouter model calls, which this agent is explicitly forbidden from doing (money guard: ~$10.32 balance, ~$0.247/question) and structurally cannot do (no Telegram client access).

The owner must perform the following steps verbatim, in order, against the running bot:

> Set `OWNER_ID` to your own numeric Telegram id, leave `ALLOWED_USER_IDS` empty, set `DAILY_SPEND_CAP_USD=1.00`, and start the bot.
>
> 1. **Allowlist refuses.** From a second Telegram account that is not the owner, send any SAT question photo. Expected: the invite-only refusal. Then run `/cost` as the owner — `Questions today` must still be `0` and spend must be `$0.0000`. This is the paywall working: an unauthorised question cost nothing.
> 2. **/adduser works.** As the owner, send `/adduser <second account's id>`. Expected: a confirmation naming the id. Resend the photo from the second account. Expected: a normal six-model consensus reply.
> 3. **/adduser is owner-only.** From the second account, send `/adduser 999999999`. Expected: the same generic refusal, no confirmation.
> 4. **Persistence.** Run `sqlite3 data/bot.db "SELECT id, user_id, consensus_state, min_transcription_overlap FROM questions;"` and `sqlite3 data/bot.db "SELECT model_id, answer, latency_ms, cost_usd, error FROM attempts;"`. Expected: one question row attributed to the second account, six attempt rows with non-null `latency_ms` and `cost_usd`.
> 5. **Cache is free.** Send the byte-identical photo again from either account. Expected: a reply within about a second, identical text to the first. Then `sqlite3 data/bot.db "SELECT id, served_from_cache, source_question_id FROM questions;"` — expected: a second row with `served_from_cache = 1` pointing at the first, and still only six rows in `attempts`.
> 6. **Per-user cap.** Temporarily set `PER_USER_DAILY_CAP=1`, restart, and send a second distinct question from the non-owner account. Expected: "You've used all 1 of today's questions. The limit resets at midnight UTC." Restore the value to 40.
> 7. **Spend cap degrades.** Temporarily set `DAILY_SPEND_CAP_USD` to just above the day's spend so far (read it from `/cost`), restart, and send a new distinct question. Expected: a normal answer that ends with a line stating a reduced 4-model set answered it, and the per-model list in the reply shows four models with neither `claude-opus-5` nor `gpt-6-astra` present.
> 8. **Budget exhaustion refuses.** Set `DAILY_SPEND_CAP_USD=0.01`, restart, send a new distinct question. Expected: "Today's question budget is used up. It resets at midnight UTC — try again then." and no new `attempts` rows.
> 9. **/cost reads correctly.** Restore `DAILY_SPEND_CAP_USD` to its real value and run `/cost` as the owner. Expected: today's spend, the cap, last 7 days, question count with the cache count and hit rate, cost per question to four decimal places, and a line saying figures reset at 00:00 UTC. Cross-check `cost_per_question_today` against the $0.11 measured baseline — a wildly different number means the cost accounting is wrong, not that the models got cheaper.
> 10. **/cost is owner-only.** Send `/cost` from the second account. Expected: the generic refusal with no figures.
>
> Restore `.env` to production values before approving.

**Resume signal:** Type "approved" (or run `/gsd:execute-phase` again to resume) if all ten checks pass, or describe which of the ten checks failed and what was observed instead.

## Issues Encountered

None beyond the expected checkpoint block.

## User Setup Required

- `DAILY_SPEND_CAP_USD`, `ALLOWED_USER_IDS`, and `PER_USER_DAILY_CAP` need temporary changes during the Task 3 walkthrough (see steps 6-8 above), all reverted afterward per the walkthrough's own instructions.
- No new environment variables were introduced by this plan.

## Next Phase Readiness

- Tasks 1 and 2 are complete, tested, and committed; nothing further is needed from a code standpoint to close this plan.
- **Blocked:** Task 3's ten-step live verification must be run and approved by the owner before this plan (and Phase 2 as a whole) can be marked complete. `STATE.md` records this as the current blocker; `ROADMAP.md`/`REQUIREMENTS.md` are intentionally left unadvanced for this plan until that approval lands.

---
*Phase: 02-persistence-caching-cost-control*
*Status: Tasks 1-2 complete, 2026-09-10. Task 3 outstanding — blocked on human checkpoint.*

## Self-Check: PASSED
All 5 created/modified files verified present on disk (`src/bot/cost/report.py`,
`tests/test_cost_report.py`, `src/bot/handlers/owner.py`, `README.md`, this SUMMARY.md).
All 5 commit hashes (d804697, 922aa5f, 860225d, 6b5787c, f5d371c) verified present in `git log`.
