---
phase: 01-core-inference-loop
plan: 06
subsystem: api
tags: [pipeline, aiogram, httpx, pydantic, consensus, image-quality]

requires:
  - phase: 01-core-inference-loop
    provides: "Settings/RosterConfig (plan 02), grade_image/to_data_url (plan 03), tally/build_reply/build_rejection (plan 04), run_round (plan 05) — all consumed unchanged"
provides:
  - "The real end-to-end round: Deps + answer_question() running byte ceiling, quality gate, base64 encode, six-way fan-out, tally, and reply rendering in strict order"
  - "Three model-decided rejection branches (unreadable_image, not_sat_verbal, multiple_questions), the last two gated on min_valid_responses so a too-small voter pool falls through to the insufficient apology instead of a false-positive rejection"
  - "handlers/ingest.py rewritten to own Telegram I/O only: file selection, download, answer_question call, and a TelegramBadRequest fallback to plain text"
  - "main.py wiring Deps into Dispatcher via workflow_data, with the httpx.AsyncClient kept open for the whole process lifetime via one outer async with"
affects: [07-latency-spike]

tech-stack:
  added: []
  patterns:
    - "pipeline.answer_question is the single ordered gate: byte-ceiling check before decode, grade_image before to_data_url, run_round before any per-model verdict is trusted, tally() last — every early-return path costs zero HTTP requests"
    - "not_sat_verbal/multiple_questions majority checks only run when the non-abstaining voter count already meets min_valid_responses; below that threshold both checks are skipped and tally()'s own insufficient-tier apology is the only output, avoiding a false rejection drawn from too few voters"
    - "aiogram DI: Dispatcher(deps=deps) populates workflow_data, and any handler declaring a `deps: Deps` parameter receives it automatically — no per-message Deps construction, no global state"

key-files:
  created:
    - tests/test_pipeline.py
  modified:
    - src/bot/pipeline.py
    - src/bot/handlers/ingest.py
    - src/bot/main.py
    - tests/test_end_to_end.py

key-decisions:
  - "The not-SAT-verbal/multiple-questions majority checks are gated on `len(voters) >= settings.min_valid_responses`, not merely `voters` being non-empty as the plan's prose loosely suggested — this is what reconciles the plan's own two behavior statements ('4 of 6 not-verbal rejects' vs '2 ok / 4 abstain renders the insufficient apology, not a rejection') and is exactly what the acceptance criteria's 4-abstain/2-ok-not-verbal test checks"
  - "grade_image's ValueError and to_data_url's ValueError are both caught and mapped to the same unreadable_image rejection, so a payload that decodes for one PIL call but fails format detection for the other still degrades to a rejection instead of an uncaught exception"
  - "The httpx.AsyncClient opened for boot validation is now kept open for the entire process lifetime (one outer `async with` wrapping both validation and start_polling) rather than closed after validation, since Deps needs a single shared client with a live connection pool for the six-way fan-out"
  - "handlers/ingest.py collapses F.photo and F.document into one shared _handle_update, since select_file_id already implements the document-over-photo preference and both aiogram filters can safely pass message.photo/message.document straight through (a photo update always has document=None and vice versa)"

patterns-established:
  - "Test transports across test_pipeline.py and test_end_to_end.py script six independently-addressable model responses by branching the MockTransport handler on the request body's `model` field, reusing tests/fixtures/verdicts.py's valid_verdict_json/abstaining_verdict_json/multi_question_verdict_json builders and tests/test_images.py's _sharp_page_bytes/_blurred_page_bytes helpers rather than re-deriving synthetic images or verdict JSON shapes"

requirements-completed: [ING-01, ING-02, ING-03, ING-05, ING-06, ING-07, INF-01, INF-14, CON-05]

duration: ~30min
completed: 2026-09-10
---

# Phase 1 Plan 6: Real Pipeline and Live-Wired Handler Summary

**Deleted the plan-01 hardcoded consensus stub and replaced it with the real ordered pipeline — byte ceiling, local quality gate, six-way OpenRouter fan-out, model-decided rejection branches, and tally-based reply rendering — wired end to end through a Telegram-I/O-only handler and a process-lifetime-shared httpx client, all green with zero credentials and zero live network calls.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-09-10T16:27:40Z (approx, context load)
- **Completed:** 2026-09-10T16:37:29Z
- **Tasks:** 2 (both `type="auto"`, Task 1 marked `tdd="true"`)
- **Files modified:** 1 created, 4 modified

## Accomplishments
- `_STUB_CONSENSUS` is gone; `pipeline.answer_question(deps, image_bytes, *, source_is_photo)` runs the real sequence in strict order and returns at the first branch that fires, with a `Deps` dataclass (`settings`, `roster`, `http`) as the single injectable bundle
- Zero HTTP requests reach the transport for oversized bytes, reject-grade images, or undecodable bytes — proven directly by request-log assertions, not just by return-value inspection
- `is_sat_verbal`/`question_count` rejections are decided by a strict majority of non-abstaining models only, gated on `min_valid_responses` so a 2-ok/4-abstain round with both ok votes saying "not verbal" correctly falls through to the `insufficient` apology instead of firing a rejection drawn from too few voters
- `handlers/ingest.py` now contains zero orchestration (`run_round`/`grade_image`/`tally` all absent by grep) and zero `file_name` logging; a `TelegramBadRequest` on send falls back to a plain-text resend so a reply that already cost real inference spend is never silently dropped
- `main.py`'s `httpx.AsyncClient` now lives for the whole process (boot validation through `start_polling`) inside one outer `async with`, and `Dispatcher(deps=deps)` injects the shared `Deps` into every handler via aiogram's `workflow_data` mechanism — confirmed by reading aiogram's installed source (`Dispatcher.workflow_data = kwargs`)
- `pytest tests/ -q` — 137 tests total (123 baseline + 13 in `test_pipeline.py` + 1 new header-exactness test in `test_end_to_end.py`), all green; `ruff check .` clean; `python -m bot --validate-only` exits 0 with `TELEGRAM_BOT_TOKEN`/`OPENROUTER_API_KEY` both unset

## Task Commits

1. **Task 1: Real pipeline with the pre-flight gate and the rejection branches** - `1ddd8e8` (feat)
2. **Task 2: Handler and startup wiring, end-to-end green** - `3b8eb94` (feat)

**Plan metadata:** pending (docs: complete plan, committed after this summary)

_Note: Task 1 is marked `tdd="true"` in the plan; see TDD Gate Compliance below._

## Files Created/Modified
- `src/bot/pipeline.py` - `Deps` (frozen dataclass), real `answer_question()`: byte ceiling → `grade_image` → `to_data_url` → `run_round` → majority-vote rejection checks → `tally()` → `build_reply()`
- `tests/test_pipeline.py` - 13 tests: zero-request guarantees on oversized/reject-grade/undecodable/zero-length bytes, warn-grade proceed-and-log, both model-decided rejections, the non-abstaining-only guard, insufficient apology (both the general case and the not-verbal-but-too-few-voters case), strong six-agree with spoiler, degraded two-abstention header, all-six-error survival, and exactly-six-requests on a clean round
- `src/bot/handlers/ingest.py` - rewritten: `_handle_update` shared by `F.photo`/`F.document`, `select_file_id` resolves the file, `Deps` arrives via handler kwarg injection, `_send` wraps `message.answer` in a `TelegramBadRequest` fallback
- `src/bot/main.py` - one outer `async with httpx.AsyncClient()` now spans boot validation and `start_polling`; `Deps` constructed once after validation succeeds and passed to `Dispatcher(deps=deps)`; `--validate-only` still returns before `Deps`/`Bot` exist
- `tests/test_end_to_end.py` - updated for the new `answer_question(deps, ...)` signature; replaced the too-small (200x100) shared fixture with `tests.test_images._sharp_page_bytes()` since the real quality gate would otherwise hard-reject it; added an exact `"6/6 agree · 4 labs"` header assertion driven by a scripted six-model `MockTransport` round

## Decisions Made
- The not-SAT-verbal/multiple-questions majority checks require `len(voters) >= settings.min_valid_responses` before running at all — reconciles the plan's own two stated behaviors and is what the acceptance criteria's specific 4-abstain/2-ok-not-verbal test verifies.
- Both `grade_image` and `to_data_url`'s `ValueError` paths degrade to the same `unreadable_image` rejection, since an image can pass one PIL call and fail format detection in the other (e.g. a decodable-but-unsupported format like BMP).
- `handlers/ingest.py` uses one shared `_handle_update` for both `F.photo` and `F.document` filters, since `select_file_id(message.photo, message.document)` already implements the document-over-photo preference and both filters guarantee the other field is unset.
- The boot-validation `httpx.AsyncClient` is no longer closed before polling starts; it is now the same client instance carried into `Deps` and used for all six-model fan-out calls for the life of the process.

## Deviations from Plan

None requiring the auto-fix rules — the pipeline's rejection-gating logic (`len(voters) >= min_valid_responses`) required interpreting the plan's prose ("skip both checks... when voters is empty") more precisely than literally written, since the literal reading would have failed the plan's own stated acceptance test (4-abstain/2-ok-not-verbal renders the apology, not a rejection). This is documented above as a Decision, not a deviation, since it makes the plan's own acceptance criteria pass rather than adding out-of-scope behavior.

## TDD Gate Compliance

Task 1 is marked `tdd="true"`, but this plan's own action block instructs writing the full implementation and its test file together and verifying via `pytest`/`ruff`, matching the pattern already established in plan 05 (see that plan's SUMMARY.md TDD Gate Compliance note). No standalone RED commit exists; `1ddd8e8` contains both `src/bot/pipeline.py` and `tests/test_pipeline.py` together, verified green (13/13 passing) before commit. Every behavior in the plan's `<behavior>` block is covered by a passing test against the real implementation.

## Issues Encountered
None. Environment matched the documented baseline exactly (123 passing tests, ruff clean, `.venv/bin/python`/`.venv/bin/pytest`), and no OpenRouter/Telegram credentials were needed or used — every test routes through `httpx.MockTransport`.

## User Setup Required

None - no external service configuration required. `python -m bot --validate-only` and the full test suite both run with `TELEGRAM_BOT_TOKEN`/`OPENROUTER_API_KEY` unset, confirmed by an explicit `env -u` run.

## Next Phase Readiness
- The phase's headline capability is real end to end: a photo (or document) reaches `answer_question`, all six models fire concurrently, and an honest tiered reply or a specific rejection comes back — with zero inference spend on any image that fails the pre-flight gate.
- Plan 07 (the empirical latency spike) can now drive this exact `pipeline.answer_question`/`Deps` path against the live OpenRouter API once `OPENROUTER_API_KEY` is provisioned — no signature or wiring changes needed.
- Docker build/run verification from the plan's `<verification>` block could not be executed in this sandbox (no `docker` binary), consistent with plan 02's prior finding; this plan did not touch `Dockerfile`/`docker-compose.yml`, so no new Docker-surface risk was introduced. Should be spot-checked on the real deployment VPS before first use, carried forward from plan 02.
- No blockers. Real credentials (`TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`) are still required before the bot serves live Telegram traffic or plan 07's spike can run against the real API.

---
*Phase: 01-core-inference-loop*
*Completed: 2026-09-10*
