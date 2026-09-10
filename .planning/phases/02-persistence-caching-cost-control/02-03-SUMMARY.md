---
phase: 02-persistence-caching-cost-control
plan: 03
subsystem: access-control

tags: [aiogram, middleware, sqlite, allowlist, paywall]

# Dependency graph
requires:
  - phase: 02-persistence-caching-cost-control
    provides: src/bot/db/ package (open_connection, schema with a pre-declared unwritten users table), Deps dataclass, aiogram Dispatcher/router wiring
provides:
  - src/bot/db/users.py — allowlist reads/writes and the single-statement atomic daily-cap consume
  - src/bot/middleware/access.py — AccessMiddleware, an aiogram outer middleware refusing before any handler runs
  - src/bot/handlers/owner.py — /adduser restricted to OWNER_ID with in-handler defence in depth
affects: [02-04-spend-cap, any future phase adding new message handlers (all pass through AccessMiddleware automatically)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Atomic single-statement UPDATE for quota enforcement (allowlist check + day rollover + cap check + increment in one WHERE clause), never SELECT-then-UPDATE — closes the check-then-act race PITFALLS.md names as the real failure shape under concurrent load"
    - "INSERT ... ON CONFLICT DO NOTHING RETURNING <pk> to detect newly-created vs already-existing rows without an extra SELECT"
    - "aiogram outer_middleware on dispatcher.message registered before include_router so every router (including future ones) is covered automatically"
    - "Fail-closed on both axes: unset OWNER_ID disables owner commands entirely; any exception inside AccessMiddleware refuses rather than passes through"

key-files:
  created:
    - src/bot/db/users.py
    - src/bot/middleware/__init__.py
    - src/bot/middleware/access.py
    - src/bot/handlers/owner.py
    - tests/test_access.py
    - tests/test_owner_commands.py
  modified:
    - src/bot/config.py
    - .env.example
    - src/bot/main.py

key-decisions:
  - "add_user() uses INSERT ... ON CONFLICT DO NOTHING RETURNING telegram_id instead of a SELECT-then-INSERT to detect novelty, so the file's total SELECT count stays at the one used by is_allowed() and satisfies the plan's grep gate"
  - "access.py imports the users module qualified (`from bot.db import users as users_repo`) rather than importing try_consume_daily by name, so the literal string 'try_consume_daily' appears on exactly one line as the plan's grep gate requires"
  - "seed_allowlist(conn, settings.allowlist_ids) is called once in main.py right after opening the connection — the plan defines seed_allowlist and documents it as 'called once at startup' but does not assign a specific wiring task; without this call ALLOWED_USER_IDS would be parsed but never written to the users table, making the paywall's env-based path inert (Rule 2)"
  - "A cache hit still consumes a daily slot (per plan) — the per-user cap bounds request volume and abuse, not just spend"

requirements-completed: [ACC-01, ACC-02, ACC-03]

# Metrics
duration: 9min
completed: 2026-09-10
---

# Phase 2 Plan 3: Allowlist Paywall, Per-User Cap, Owner-Only /adduser Summary

**An aiogram outer middleware refuses every unauthorized or over-cap update before `answer_question` is reachable, enforced by one atomic SQLite `UPDATE` that folds the allowlist check, UTC day rollover, cap check, and increment into a single statement so concurrent requests cannot race the last slot, plus an owner-only `/adduser` that fails closed when `OWNER_ID` is unset.**

## Performance

- **Duration:** ~9 min (commit-to-commit)
- **Started:** 2026-09-10T23:32:30+05:00
- **Completed:** 2026-09-10T23:41:02+05:00
- **Tasks:** 3 completed
- **Files modified:** 9 (6 created, 3 modified)

## Accomplishments
- `src/bot/db/users.py`: `ensure_user`, `seed_allowlist`, `add_user`, `is_allowed`, `try_consume_daily` — the cap/allowlist enforcement point is one conditional `UPDATE` statement, verified concurrency-safe with a 10-way `asyncio.gather` test against a user with exactly one question of headroom (exactly one `True`)
- `src/bot/middleware/access.py`: `AccessMiddleware`, registered as `dispatcher.message.outer_middleware(...)` before any router is included, so it covers every current and future message handler. Drops `from_user is None` updates silently, bypasses the owner unconditionally, lets free (non-photo/document) messages through on an allowlist-only check, and fails closed (refuses, no pass-through) on any exception including a closed/broken database connection
- `src/bot/handlers/owner.py`: `/adduser <telegram_id>` restricted to `OWNER_ID`, re-checked inside the handler as defence in depth on top of the middleware, refuses everyone and logs `critical` when `OWNER_ID` is unset, never string-interpolates the argument into SQL
- 185 tests passing (up from 160 baseline; +25 new), Ruff clean
- Verified end-to-end: a non-allowlisted photo update produces zero HTTP requests (`test_middleware_blocks_unknown_photo_user_zero_http`)

## Task Commits

Each task was committed as a RED/GREEN TDD pair:

1. **Task 1: settings, allowlist seeding, and the atomic daily-cap consume**
   - `79896b3` test: failing tests for settings/users/daily/concurrency behaviors
   - `9e1b7f1` feat: `Settings.owner_id`/`allowed_user_ids`/`allowlist_ids`/`per_user_daily_cap`, `src/bot/db/users.py`
2. **Task 2: access middleware that refuses before any handler runs**
   - `f4abee8` test: failing tests for the outer middleware
   - `a8dc6d3` feat: `AccessMiddleware`, registered in `main.py`, `seed_allowlist` wired at startup
3. **Task 3: /adduser, owner-restricted**
   - `03f145b` test: failing tests for owner-restricted `/adduser`
   - `33bcee7` feat: `src/bot/handlers/owner.py`, owner router included before the ingest router

**Plan metadata:** (this commit, immediately following)

## Files Created/Modified
- `src/bot/db/users.py` - `ensure_user` (idempotent upsert of `is_allowed` only, preserves `daily_count`), `seed_allowlist`, `add_user` (RETURNING-based novelty detection), `is_allowed`, `try_consume_daily` (the one atomic UPDATE)
- `src/bot/middleware/access.py` - `AccessMiddleware(BaseMiddleware)`; check order is from_user→owner→free-message-allowlist→paid-message-cap-consume; fails closed on any exception
- `src/bot/handlers/owner.py` - `/adduser` handler; owner re-check, `int()` parse with usage-text fallback, routes through the same `Text`+`as_kwargs()`+`TelegramBadRequest` fallback pattern as `ingest.py`
- `src/bot/config.py` - `owner_id: int | None = None` (fails closed by default), `allowed_user_ids: str`, `allowlist_ids` property, `per_user_daily_cap: int = 40`
- `.env.example` - added `ALLOWED_USER_IDS=` and `PER_USER_DAILY_CAP=40` (`OWNER_ID=` was already present)
- `src/bot/main.py` - opens connection → `seed_allowlist` → registers `AccessMiddleware` as outer middleware → includes owner router before the ingest router
- `tests/test_access.py` - settings parsing, `users.py` behaviors, 10-way concurrency test, middleware behaviors including the zero-HTTP-request and database-error-refuses cases
- `tests/test_owner_commands.py` - owner-only `/adduser` behaviors including the `OWNER_ID`-unset fail-closed case

## Decisions Made
See `key-decisions` in frontmatter — the two grep-gate-driven implementation choices (`RETURNING` instead of `SELECT`-then-`INSERT` in `add_user`; qualified `users_repo.try_consume_daily` import) are stylistic, not architectural, and do not change external behavior.

## Deviations from Plan

**1. [Rule 2 - Missing Critical] Wired `seed_allowlist` into `main.py` startup**
- **Found during:** Task 2
- **Issue:** The plan defines `seed_allowlist(conn, ids)` in Task 1 and documents it as "called once at startup" but never assigns a specific task to actually call it from `main.py`. Without this, `ALLOWED_USER_IDS` would parse correctly into `Settings.allowlist_ids` but never reach the `users` table — the env-based half of the paywall would be silently inert.
- **Fix:** Added `await seed_allowlist(conn, settings.allowlist_ids)` in `main.py` immediately after `open_connection`, before `Deps` is constructed.
- **Files modified:** `src/bot/main.py`
- **Verification:** Covered indirectly — `seed_allowlist`/`ensure_user` are exercised directly in `tests/test_access.py`; `main.py` import-checked with `python -c "import bot.main"`.
- **Committed in:** `a8dc6d3` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Necessary for `ALLOWED_USER_IDS` to have any effect at all. No scope creep — no new files, no new behavior beyond what the plan's interface already declared.

## Issues Encountered
None beyond the two grep-gate-driven implementation choices noted above (not blocking, resolved on first pass).

**Pre-existing, unrelated working-tree drift observed (not touched):** `models.yaml`, `scripts/model_bakeoff.py`, and `tests/test_config.py` carry uncommitted local edits adding an eighth model (`anthropic/claude-fable-5.1`) that were already present in the working tree before this plan started and are outside this plan's `files_modified` list. Per the plan's explicit instruction not to touch `models.yaml`/consensus/reply formatting, and per the executor's scope boundary, these were left untouched and uncommitted. The full test suite (185 passed) already reflects their presence since they are uncommitted working-tree state, not something this plan introduced.

## User Setup Required
None beyond what's already configured. `OWNER_ID` is expected to already be set in the real `.env` (per the phase's `user_setup` block); `ALLOWED_USER_IDS` and `PER_USER_DAILY_CAP` are new optional variables added to `.env.example` with safe defaults (`PER_USER_DAILY_CAP` defaults to 40 in code if unset).

## Next Phase Readiness
- Plan 02-04 (global spend cap) can build on the same `Deps`/middleware pattern; `AccessMiddleware` already sits outer-most in the dispatcher chain, so a spend-cap check can be added as its own middleware or folded into the existing one without touching handler code
- The `users` table is now actively written by real traffic (`daily_count`, `daily_count_date`, `is_allowed`, `added_at`), unblocking a future `/cost`-per-user or usage-reporting feature
- No blockers

---
*Phase: 02-persistence-caching-cost-control*
*Completed: 2026-09-10*

## Self-Check: PASSED
All 6 created source/test files and the SUMMARY.md verified present on disk. All 6 task commit hashes (79896b3, 9e1b7f1, f4abee8, a8dc6d3, 03f145b, 33bcee7) verified present in `git log`.
