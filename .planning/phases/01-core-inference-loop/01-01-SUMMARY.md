---
phase: 01-core-inference-loop
plan: 01
subsystem: api
tags: [aiogram, pydantic, httpx, telegram, python3.12]

requires: []
provides:
  - "Installable src-layout Python 3.12 package (sat-consensus-bot) with pinned deps"
  - "Strict pydantic v2 JSON contract (Verdict, AttemptResult, ConsensusResult, QuestionType, RejectionReason, Position, ConsensusTier, Choices, ChoiceVerdict)"
  - "Byte-identical SYSTEM_PROMPT / USER_PROMPT / REPAIR_PROMPT_TEMPLATE constants"
  - "aiogram long-polling bot skeleton: main.py, __main__.py, handlers/ingest.py routing photo/document to a reply"
  - "formatting/reply.py building spoiler-last consensus replies and rejection copy via aiogram Text/Spoiler entities"
  - "pipeline.answer_question() entry point with a hardcoded ConsensusResult stub, ready for plan 06 to replace"
affects: [02-boot-validation-and-config, 05-model-fanout, 06-consensus-and-live-round]

tech-stack:
  added: [aiogram==3.31.0, httpx==0.28.1, "pydantic>=2.4.1,<2.14", pydantic-settings, Pillow==12.3.0, PyYAML, python-dotenv, ruff==0.16.6, pytest, pytest-asyncio]
  patterns:
    - "Reply text built exclusively via aiogram.utils.formatting.Text/Spoiler entities, never hand-escaped MarkdownV2 strings"
    - "orchestrator/contract.py is the single source of truth for the per-model JSON contract and consensus shapes; every later plan imports from here without changing signatures"
    - "pipeline.answer_question() is the one async entry point handlers call; internals (currently a stub) are swappable without touching handler code"

key-files:
  created:
    - pyproject.toml
    - .gitignore
    - src/bot/orchestrator/contract.py
    - src/bot/prompts.py
    - src/bot/pipeline.py
    - src/bot/formatting/reply.py
    - src/bot/handlers/ingest.py
    - src/bot/main.py
    - src/bot/__main__.py
    - tests/conftest.py
    - tests/fixtures/verdicts.py
    - tests/test_contract.py
    - tests/test_end_to_end.py
  modified: []

key-decisions:
  - "Package legitimacy gate (Task 1) was answered by the developer before this executor ran; all ten packages confirmed, none rejected"
  - "Verdict's model_validator enforces elimination discipline (exactly 4 eliminations covering A-D, exactly one 'selected', answer must match the selected choice) only when is_sat_verbal and question_count==1; otherwise answer must be None"
  - "Reply body text is assembled as a single joined string, with Spoiler(winning_letter) appended as a separate trailing Text node so the spoiler entity always ends at len(text)"
  - "insufficient consensus tier renders as an apology line only — no header stats, no footer, no spoiler — per the plan's 'nothing else after it' requirement"

patterns-established:
  - "Every AttemptResult is constructed via .ok()/.abstain() classmethods, never the bare constructor, to keep raw_first_response/abstain_reason bookkeeping consistent"
  - "TDD gate for contract.py: RED commit (ae5084f) before GREEN commit (65d0bc8), enforced per plan's tdd=\"true\" flag"

requirements-completed: [CFG-05, ING-01, INF-02, INF-03, INF-04, INF-05, INF-06, INF-07, INF-08, INF-11, INF-15, CON-06, CON-07]

duration: ~20min
completed: 2026-09-10
---

# Phase 1 Plan 1: Walking Skeleton Summary

**Installable aiogram 3.31.0 Telegram bot with a strict pydantic v2 JSON contract, a byte-identical shared SYSTEM_PROMPT, and a stubbed-consensus end-to-end reply path (spoiler-wrapped letter last), all green under ruff and pytest with zero credentials.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-09-10T20:53:00+05:00 (approx, context load)
- **Completed:** 2026-09-10T21:03:00+05:00
- **Tasks:** 4 (1 pre-approved checkpoint + 3 auto tasks, one TDD)
- **Files modified:** 19 created, 0 modified outside this plan's own files

## Accomplishments
- Package legitimacy gate confirmed by the developer before install; `pip install -e ".[dev]"` installs exactly the pinned versions from STACK.md with no substitutions
- `Verdict` contract structurally rejects every malformed shape the plan specified: mismatched answer/selected choice, missing eliminations, double-selection, duplicate choices, missing quantitative/clause fields
- `SYSTEM_PROMPT` is a single parameterless constant containing all 11 `QuestionType` values and the INF-04 through INF-08 requirements as literal text; `REPAIR_PROMPT_TEMPLATE` contains no reference to the image
- Full wiring from a Telegram photo/document update through `answer_question()` to a `build_reply()` message whose final line is `Spoiler(winning_letter)` with reasoning first
- `python -m bot` with a fake token reaches Telegram's real API and fails with `TelegramUnauthorizedError`, not an import or type error, confirming the whole import graph is sound

## Task Commits

1. **Task 1: Package legitimacy gate before first install** - answered by developer prior to execution (see `<human_gate_already_answered>`), no commit (nothing built yet)
2. **Task 2: Project scaffold and failing end-to-end test** - `8487bc2` (feat)
3. **Task 3: JSON contract and the shared prompt** - `ae5084f` (test, RED) then `65d0bc8` (feat, GREEN)
4. **Task 4: Wire the skeleton end to end with a stubbed round** - `3a357cb` (feat)

**Plan metadata:** pending (docs: complete plan, committed after this summary)

## Files Created/Modified
- `pyproject.toml` - pinned deps, ruff/pytest config, src-layout build
- `.gitignore` - excludes `.env` from the very first commit
- `src/bot/orchestrator/contract.py` - `QuestionType`, `Choices`, `ChoiceVerdict`, `Verdict` (with elimination-discipline validator), `AttemptResult`, `ConsensusResult`, `Position`, `ConsensusTier`, `RejectionReason`
- `src/bot/prompts.py` - `SYSTEM_PROMPT`, `USER_PROMPT`, `REPAIR_PROMPT_TEMPLATE` constants only
- `src/bot/pipeline.py` - `answer_question()` with `_STUB_CONSENSUS` stand-in for the live round
- `src/bot/formatting/reply.py` - `build_reply()`, `build_rejection()` using `aiogram.utils.formatting`
- `src/bot/handlers/ingest.py` - `router` handling `F.photo`/`F.document`, logs only chat_id/file_unique_id/byte length
- `src/bot/main.py`, `src/bot/__main__.py` - long-polling entrypoint reading `TELEGRAM_BOT_TOKEN`
- `tests/conftest.py`, `tests/fixtures/verdicts.py`, `tests/test_contract.py`, `tests/test_end_to_end.py` - 17 passing tests, no credentials required

## Decisions Made
- Package legitimacy: **confirmed** by the developer for all ten packages (aiogram, httpx, pydantic, pydantic-settings, Pillow, PyYAML, python-dotenv, ruff, pytest, pytest-asyncio); none rejected.
- Elimination-discipline validation only fires when `is_sat_verbal` is true and `question_count == 1`; all other cases require `answer is None` and skip the four-choice checks, matching the plan's accept/reject test matrix exactly.
- Reply assembly joins body lines into one string and appends `Spoiler(letter)` as a trailing `Text` node, guaranteeing the spoiler entity always terminates at `len(text)` regardless of body content length.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Ruff line-length violations in generated prompt and contract text**
- **Found during:** Task 3 and Task 4 verification
- **Issue:** Several literal strings (`SYSTEM_PROMPT` bullet lines, one `ValueError` message, one f-string header line, one docstring) exceeded the configured 100-char line length.
- **Fix:** Re-wrapped the affected lines without changing their meaning or the constants' semantic content.
- **Files modified:** `src/bot/prompts.py`, `src/bot/orchestrator/contract.py`, `src/bot/pipeline.py`, `src/bot/formatting/reply.py`
- **Verification:** `ruff check .` exits 0
- **Committed in:** `65d0bc8`, `3a357cb` (part of the same task's commit)

---

**Total deviations:** 1 auto-fixed (1 bug/lint)
**Impact on plan:** Cosmetic only — no behavior change, no scope creep.

## Issues Encountered
- Local macOS environment quirk (unrelated to the codebase): the pip editable-install `.pth` file in `.venv/` was repeatedly given the macOS `UF_HIDDEN` flag (observed to be re-applied, likely by iCloud Desktop sync on this machine, since the project lives under `~/Desktop`), which made bare `python -c "import bot..."` fail intermittently while `pytest` (which configures `pythonpath` explicitly) kept working. Worked around locally with `PYTHONPATH=src` for verification; `.venv/` is gitignored so this has no effect on the committed repository or on any other machine.

## User Setup Required

**External service requires manual configuration before the bot can actually run** (not required for any test in this plan):
- `TELEGRAM_BOT_TOKEN` — obtain from Telegram's `@BotFather` via `/newbot`, then set it in a local `.env` (never committed; `.gitignore` already excludes it).

No OpenRouter key or VPS is needed for this plan; the six-model round is stubbed until plan 06.

## Next Phase Readiness
- The exact interfaces plans 02-07 compile against (`Verdict`, `AttemptResult`, `ConsensusResult`, `Position`, `QuestionType`, `RejectionReason`, `ConsensusTier`, `build_reply`, `build_rejection`, `answer_question`) are locked and tested.
- Plan 06 can replace `_STUB_CONSENSUS` inside `pipeline.answer_question()` with the live six-model fan-out without touching `formatting/reply.py` or `handlers/ingest.py`.
- No blockers. The only carried-forward item is provisioning real credentials (`TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`) before any later plan can run against live services.

---
*Phase: 01-core-inference-loop*
*Completed: 2026-09-10*

## Self-Check: PASSED

All 14 created files verified present on disk; all 5 commit hashes (8487bc2, ae5084f, 65d0bc8, 3a357cb, ba30c47) verified present in `git log --all`.
