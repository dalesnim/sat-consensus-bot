---
phase: 02-persistence-caching-cost-control
plan: 02
subsystem: caching

tags: [imagehash, phash, sqlite, cache, cost-control]

# Dependency graph
requires:
  - phase: 02-persistence-caching-cost-control
    provides: "02-01: SQLite questions/attempts persistence, insert_question with a phash column, shared aiosqlite connection via Deps.db"
provides:
  - "compute_phash(data) -> 64-char hex string, exact 256-bit pHash at hash_size=16"
  - "find_cached_question(conn, phash) -> CachedQuestion | None, exact-match lookup excluding cache-sourced and insufficient rows"
  - "cache branch in answer_question: zero-cost short-circuit on exact phash match, with a served_from_cache=1 audit row"
affects: [02-04-spend-cap, 02-05-cost-report]

# Tech tracking
tech-stack:
  added: [imagehash==4.3.2]
  patterns:
    - "phash + sha256 computed once, right after the quality gate and before to_data_url, so a cache hit never pays for base64 encoding or a network call"
    - "Cache repo functions accessed via qualified module import (`from bot.db import questions as questions_repo`) rather than a bare name import, keeping the call site the single occurrence of the function name in pipeline.py"
    - "Cache read wrapped in narrow try/except that degrades to a normal paid round; the audit-row write on a hit is wrapped separately so a persistence failure never turns a successful cache hit into an unhandled exception"
    - "No Hamming-distance/fuzzy matching anywhere in the cache path — exact 256-bit string equality only, enforced by grep-based acceptance criteria"

key-files:
  created:
    - tests/test_cache.py
  modified:
    - pyproject.toml
    - src/bot/images/extract.py
    - src/bot/db/questions.py
    - src/bot/pipeline.py

key-decisions:
  - "find_cached_question is imported via `from bot.db import questions as questions_repo` and called as questions_repo.find_cached_question(...), not a bare name import, so the literal function name appears exactly once in pipeline.py (matches the plan's grep-based acceptance criterion) while insert_question keeps its existing direct import"
  - "The SHA-256 mismatch warning is logged after the cache-hit audit row insert, not before, so the log line can name both question ids (source_question_id and the newly inserted row's id), satisfying 'naming both question ids' from the plan"
  - "insert_question on the cache-hit path is wrapped in its own try/except, matching the existing live-path persistence-failure tolerance even though the plan text didn't call this out explicitly — a DB write failure on a cache hit must not turn a free answer into a crash (Rule 2)"
  - "Reused test_persistence.py's convention of a locally duplicated `settings` pytest fixture in tests/test_cache.py rather than importing test_pipeline.settings by name, avoiding the Ruff F811 shadowing issue already documented in 02-01-SUMMARY.md"

patterns-established:
  - "Perceptual-hash cache key computed once per request and reused for both the cache lookup and the eventual insert_question call, avoiding a second Pillow decode"

requirements-completed: [DATA-01, DATA-02, DATA-05]

# Metrics
duration: 22min
completed: 2026-09-10
---

# Phase 2 Plan 2: Exact-Match Perceptual Hash Caching Summary

**Every submitted image is hashed with a 256-bit pHash (`hash_size=16`); an exact match short-circuits the round to a stored `ConsensusResult` with zero OpenRouter calls, while a byte-mismatch on the same phash is served anyway but logged as a queryable collision signal.**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-09-10T23:57:00+05:00
- **Completed:** 2026-09-11T00:19:00+05:00
- **Tasks:** 2 completed
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- `compute_phash` added to `src/bot/images/extract.py` — deterministic, format-invariant (PNG vs JPEG re-encode of the same content), 64-character lowercase hex output, `ValueError` on undecodable bytes matching `to_data_url`'s existing contract
- `find_cached_question` added to `src/bot/db/questions.py` — exact-phash SQL lookup that excludes `served_from_cache = 1` rows (no chained cache hits) and `consensus_state = 'insufficient'` rows (failed rounds are never replayed), returning the most recent match
- `answer_question` now short-circuits on a cache hit before any OpenRouter call: rebuilds the reply from `ConsensusResult.model_validate_json(cached.consensus_json)`, writes a `served_from_cache=1` audit row pointing at `source_question_id`, and writes zero `attempts` rows
- A SHA-256 discriminator check runs on every hit; a mismatch (same phash, different bytes) still serves the cached answer per the locked exact-match decision, but logs a `WARNING` naming both question ids and both hashes — the only detector for a phash collision in v1
- The cache lookup itself is exception-isolated: a `find_cached_question` failure logs and falls through to a normal paid round rather than losing the user's answer
- 202 tests passing (up from a 189 baseline; 13 new tests added), Ruff clean, zero live OpenRouter calls made

## Task Commits

Each task was committed as a RED/GREEN TDD pair:

1. **Task 1: compute_phash and the exact-match lookup**
   - `6962871` test: failing tests for compute_phash and find_cached_question
   - `823e805` feat: implement compute_phash and find_cached_question
2. **Task 2: cache branch in the pipeline with a persisted cache-hit row**
   - `d28e174` test: failing pipeline-level cache branch tests
   - `1bcd0ae` feat: wire cache branch into answer_question

**Plan metadata:** (this commit, immediately following)

## Files Created/Modified
- `src/bot/images/extract.py` - `PHASH_SIZE = 16` constant, `compute_phash(data: bytes) -> str`
- `src/bot/db/questions.py` - `CachedQuestion` pydantic model, `find_cached_question(conn, phash)`
- `src/bot/pipeline.py` - phash/sha256 computed after the quality gate, cache branch before `to_data_url`, placeholder `phash=""` replaced with the real value on the live-path insert
- `tests/test_cache.py` - new module: `compute_phash` behaviors, `find_cached_question` behaviors, and four pipeline-level cache-branch integration tests

## Decisions Made
- Qualified module import (`from bot.db import questions as questions_repo`) for `find_cached_question` so the literal function name appears exactly once in `pipeline.py`, satisfying the plan's grep-based acceptance criterion while leaving `insert_question`'s existing direct import untouched
- SHA-256 mismatch warning logged after the audit-row insert so it can carry both question ids in one line
- Cache-hit audit row insert wrapped in its own try/except (Rule 2 — a DB write failure on a free cache hit must not crash the response)
- Local `settings` fixture duplicated in `tests/test_cache.py`, following the precedent set in `tests/test_persistence.py` (see 02-01-SUMMARY.md) to avoid a Ruff F811 shadowing issue from importing the fixture by name across modules

## Deviations from Plan

None - plan executed exactly as written. The `imagehash==4.3.2` pin matched the version fixed by `.planning/research/STACK.md` and installed cleanly with its transitive `numpy`/`scipy`/`PyWavelets` dependencies; no substitution was needed.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. No new environment variables or Docker changes.

## Next Phase Readiness
- Plan 02-04 (spend cap) and 02-05 (`/cost` report) can rely on cache hits already being distinguishable from paid rounds via `served_from_cache` when computing spend — a cache hit contributes zero new `attempts` rows and therefore zero new cost
- The `sha_match=<bool>` log line and the phash-collision `WARNING` give the owner a queryable signal to spot-check before trusting the hit rate, per `.planning/research/PITFALLS.md`
- No blockers

---
*Phase: 02-persistence-caching-cost-control*
*Completed: 2026-09-10*
