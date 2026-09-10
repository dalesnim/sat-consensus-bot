---
phase: 02-persistence-caching-cost-control
plan: 01
subsystem: database

tags: [aiosqlite, sqlite, wal, pydantic, persistence]

# Dependency graph
requires:
  - phase: 01-core-inference-loop
    provides: pipeline.answer_question, ConsensusResult/AttemptResult contracts, the six-model live fanout
provides:
  - src/bot/db/ package (connection, schema, questions repo, attempts repo)
  - one questions row + six attempts rows written per completed round on the live path
  - ConsensusResult.min_transcription_overlap, the persisted DATA-06 audit signal
affects: [02-02-caching, 02-03-access-control, 02-04-spend-cap]

# Tech tracking
tech-stack:
  added: [aiosqlite==0.22.1]
  patterns:
    - "Single shared aiosqlite connection injected via Deps, WAL + busy_timeout=5000 + foreign_keys set once at open_connection, never per query"
    - "Batch all six model results in memory during the round, one executemany after tally() rather than per-call writes — contention avoided by construction"
    - "Persistence wrapped in try/except at the end of answer_question; failure logs at error level and the already-computed reply is still returned"
    - "Vestigial schema columns (resolved_by_tier, attempts.tier, attempts.confidence) always written as the constant 'single' / NULL since no escalation cascade exists"

key-files:
  created:
    - src/bot/db/__init__.py
    - src/bot/db/schema.sql
    - src/bot/db/connection.py
    - src/bot/db/questions.py
    - src/bot/db/attempts.py
  modified:
    - pyproject.toml
    - .env.example
    - src/bot/config.py
    - src/bot/orchestrator/contract.py
    - src/bot/orchestrator/consensus.py
    - src/bot/pipeline.py
    - src/bot/main.py
    - src/bot/handlers/ingest.py
    - tests/conftest.py
    - tests/test_persistence.py
    - tests/test_pipeline.py
    - tests/test_end_to_end.py

key-decisions:
  - "_transcription_divergence renamed to _min_cross_lab_overlap, returning the score itself (float | None) instead of just the boolean, so DATA-06's overlap number survives into ConsensusResult and the database instead of being discarded after the boolean check"
  - "phash written as empty string in this plan; plan 02-02 owns imagehash and real hashing, per the plan's explicit no-imagehash-import boundary"
  - "insert_question/insert_attempts failures are caught as a single try/except around both calls — a partial write (question row without attempts) on a mid-block failure is an accepted tradeoff since the round's inference spend is already sunk and the user must not lose their reply"

requirements-completed: [DATA-03, DATA-04, DATA-06]

# Metrics
duration: 15min
completed: 2026-09-10
---

# Phase 2 Plan 1: SQLite Persistence Foundation Summary

**Every completed round now writes one `questions` row and six `attempts` rows to a WAL-mode SQLite database via a shared aiosqlite connection, including the persisted cross-model transcription overlap score that makes correlated OCR hallucination queryable after the fact.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-09-10T23:11:00+05:00
- **Completed:** 2026-09-10T23:25:54+05:00
- **Tasks:** 3 completed
- **Files modified:** 17 (5 created, 12 modified)

## Accomplishments
- `src/bot/db/` package: idempotent WAL-mode connection with `busy_timeout=5000`, a four-table schema (`questions`, `attempts`, `users`, `spend_days`) applied via `CREATE TABLE IF NOT EXISTS`, and two repositories writing schema-faithful rows from real `AttemptResult`/`ConsensusResult` objects
- `ConsensusResult.min_transcription_overlap` — the minimum cross-lab Jaccard score on passage transcriptions — is now computed once in `tally()` and persisted per question, giving DATA-06 a queryable signal instead of a log line
- Persistence is wired into the real live path: `answer_question` now requires `user_id`/`image_file_id`, persists after `tally()`, and degrades to a logged error (never a lost reply) on any SQLite failure
- 157 tests passing (up from a 139 baseline; 138-floor requirement satisfied with margin), Ruff clean

## Task Commits

Each task was committed as a RED/GREEN TDD pair:

1. **Task 1: aiosqlite dependency, DB settings, schema, and the shared connection**
   - `3eff48f` test: failing tests for connection/schema behaviors
   - `f8c6606` feat: aiosqlite pin, `DB_PATH` setting, `schema.sql`, `open_connection`
2. **Task 2: questions and attempts repositories, plus the persisted transcription overlap score**
   - `8eaa2eb` test: failing tests for both repositories and the overlap score
   - `a5a5ce5` feat: `insert_question`, `insert_attempts`, `_min_cross_lab_overlap`
3. **Task 3: wire persistence into the live request path**
   - `ca156cb` test: failing tests for full-round writes, rejection short-circuit, and failure isolation
   - `4e2911d` feat: `Deps.db`, `answer_question` persistence block, `main.py`/`ingest.py` wiring

**Plan metadata:** (this commit, immediately following)

## Files Created/Modified
- `src/bot/db/connection.py` - `open_connection`: creates parent dir, sets WAL + busy_timeout + foreign_keys once, applies `schema.sql`
- `src/bot/db/schema.sql` - all four phase-2 tables, idempotent DDL, indexed on `questions(phash)`, `questions(created_at)`, `attempts(question_id)`
- `src/bot/db/questions.py` - `insert_question`/`QuestionRow`; writes `resolved_by_tier='single'`, serialized `consensus_json`, the overlap score
- `src/bot/db/attempts.py` - `insert_attempts` via `executemany`; `tier='single'`, `confidence=NULL` always, `raw_json` envelopes verdict + truncated pre-repair text
- `src/bot/orchestrator/consensus.py` - `_min_cross_lab_overlap` replaces `_transcription_divergence`; `tally()` populates the new field
- `src/bot/orchestrator/contract.py` - `ConsensusResult.min_transcription_overlap: float | None`
- `src/bot/pipeline.py` - `Deps.db`, `answer_question(..., user_id, image_file_id)`, persistence block after `tally()`
- `src/bot/main.py` - opens/closes the shared connection around `dispatcher.start_polling`
- `src/bot/handlers/ingest.py` - passes `user_id`/`file_id` through; drops updates with no `from_user`
- `tests/conftest.py` - shared `db` fixture (async, `tmp_path`-scoped)
- `tests/test_persistence.py` - new module: connection, schema, both repositories, live-path integration

## Decisions Made
- Kept `_transcription_divergence`'s existing `logger.warning` call inside the renamed `_min_cross_lab_overlap`, preserving exact log semantics while extending its return type
- Local `settings` fixture duplicated in `tests/test_persistence.py` rather than importing `test_pipeline.settings` by name — importing it directly caused a Ruff F811 (parameter shadowing an unused top-level import); a small duplication was simpler than fixture indirection
- `phash` is deliberately empty string, not omitted — the column is `NOT NULL`, and plan 02-02 owns real perceptual hashing

## Deviations from Plan

None - plan executed exactly as written. The `aiosqlite==0.22.1` pin matched the version fixed by `.planning/research/STACK.md` and installed cleanly; no substitution was needed.

## Issues Encountered
- A manual ad-hoc sqlite inspection script (not part of the test suite) hung for >120s during exploratory verification — traced to a missing `usage` field in the hand-rolled mock response causing longer-than-expected model-call handling, unrelated to the persistence code itself. Abandoned in favor of the automated `tests/test_persistence.py::test_full_round_writes_one_question_and_six_attempts` test, which already exercises the identical path in under a second and asserts row counts, `user_id`, and `image_file_id`.

## User Setup Required
None - no external service configuration required. `DB_PATH` defaults to `data/bot.db`, which lands on the existing `/app/data` Docker volume with no compose changes needed.

## Next Phase Readiness
- Plan 02-02 (caching) can now read `consensus_json` off `questions` rows to rebuild a reply without re-running inference, and has a real `insert_question(..., phash=...)` call site ready for the perceptual hash it owns
- Plan 02-03 (access control) and 02-04 (spend cap) have `users` and `spend_days` tables already declared in `schema.sql`, unused until those plans write to them
- No blockers

---
*Phase: 02-persistence-caching-cost-control*
*Completed: 2026-09-10*

## Self-Check: PASSED
All 5 created source files and the SUMMARY.md verified present on disk. All 6 task commit hashes (3eff48f, f8c6606, 8eaa2eb, a5a5ce5, ca156cb, 4e2911d) verified present in `git log`.
