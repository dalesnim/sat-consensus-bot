---
phase: 01-core-inference-loop
plan: 03
subsystem: ingestion
tags: [pillow, pydantic, image-quality, telegram, python3.12, laplacian-blur]

requires:
  - phase: 01-core-inference-loop (plan 01)
    provides: "StrEnum/BaseModel conventions in orchestrator/contract.py; handlers/ingest.py inline photo/document branch this module will let plan 06 replace"
provides:
  - "Pure-function image ingestion gate: select_file_id, to_data_url, grade_image with no aiogram/network/logging imports"
  - "Three-level QualityGrade (ok/warn/reject) with resolution and Laplacian blur variance checks, thresholds supplied by the caller"
  - "Decompression-bomb guard via PIL.Image.MAX_IMAGE_PIXELS set at module import"
affects: [06-model-fanout-wiring]

tech-stack:
  added: []
  patterns:
    - "extract.py stays a pure function module over bytes: no Settings import, no aiogram import, no network calls — thresholds arrive as keyword arguments so plan 06 wires them from config without this module changing"
    - "Duck-typed Protocol classes (_PhotoSizeLike, _DocumentLike) replace typing.Any for aiogram-shaped objects, satisfying ruff ANN401 while keeping this module aiogram-import-free"

key-files:
  created:
    - src/bot/images/__init__.py
    - src/bot/images/extract.py
    - tests/test_images.py
  modified: []

key-decisions:
  - "Document is preferred over photo when both are present (higher fidelity, skips Telegram recompression), matching ING-03/ING-04"
  - "Hard reject floor is min_dimension // 2, exactly half the soft warn floor, so warn proceeds to inference and reject does not, per CONTEXT.md's warn-and-proceed-by-default policy"
  - "Laplacian variance computed via ImageFilter.Kernel(3x3, [0,1,0,1,-4,1,0,1,0]) + ImageStat.Stat(...).stddev[0]**2 — no numpy, no opencv, matching the plan's key_link constraint"
  - "Provisional thresholds (see below) calibrated against Image.effect_noise synthetic pages only; real-photo tuning is explicitly deferred to a later plan per CONTEXT.md"

patterns-established:
  - "TDD RED/GREEN per task: test(01-03) commit before feat(01-03) commit, for both Task 1 and Task 2"

requirements-completed: [ING-02, ING-03, ING-05]

duration: ~25min
completed: 2026-09-10
---

# Phase 1 Plan 3: Image Ingestion & Pre-Flight Quality Gate Summary

**Pure-function `src/bot/images/extract.py` selecting the highest-fidelity Telegram file (document over photo, largest PhotoSize), base64-encoding it into a data URL without re-encoding pixels, and grading resolution + Laplacian blur variance into ok/warn/reject before any of the six models is ever called.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-09-10T16:03:00Z (approx, context load)
- **Completed:** 2026-09-10T16:13:00Z
- **Tasks:** 2 (both TDD, RED then GREEN each)
- **Files modified:** 3 created, 0 modified outside this plan's own files

## Accomplishments
- `select_file_id` duck-types against aiogram's `PhotoSize`/`Document` via `Protocol` classes with zero `aiogram` import, preferring a document over any photo and the largest `PhotoSize` when only photos are present
- `to_data_url` identifies PNG/JPEG/WEBP via Pillow's `.format` and base64-encodes the original bytes untouched — no re-encoding, no resizing
- `grade_image` computes Laplacian blur variance with a hand-rolled 3x3 kernel (no numpy/opencv) and returns a three-level `QualityGrade` verdict whose hard-reject floor sits at exactly half the soft-warn floor
- `PIL.Image.MAX_IMAGE_PIXELS = 50_000_000` set at module import to guard against decompression-bomb payloads (T-03-01)
- 16 tests pass with zero credentials, zero network calls, all synthetic images generated in-memory with Pillow

## Task Commits

Each task was committed atomically (TDD RED then GREEN):

1. **Task 1: Telegram file selection and the byte ceiling**
   - `42401f7` (test, RED) — 8 failing tests, `select_file_id`/`to_data_url` stubbed to raise `NotImplementedError`
   - `6c3b6a5` (feat, GREEN) — full implementation, all 8 tests pass
2. **Task 2: Pre-flight quality gate**
   - `a5d76c6` (test, RED) — extended test file fails at collection (`grade_image`, `QualityGrade` not yet defined)
   - `518859b` (feat, GREEN) — `QualityGrade`, `QualityReport`, `grade_image` implemented; 16 tests pass total

**Plan metadata:** pending (docs: complete plan, committed after this summary)

_Note: both tasks are TDD; each has a test commit before its feat commit._

## Files Created/Modified
- `src/bot/images/__init__.py` - empty package marker
- `src/bot/images/extract.py` - `ImageSource`, `select_file_id`, `to_data_url`, `QualityGrade`, `QualityReport`, `grade_image`; `Image.MAX_IMAGE_PIXELS` guard set at import
- `tests/test_images.py` - 16 tests: 8 for file selection/data-URL encoding, 8 for the quality gate, all against Pillow-generated in-memory images and stand-in dataclasses

## Decisions Made
- Document uploads win over photo uploads whenever both are present in a single message, per ING-03/ING-04 and the CONTEXT.md document-over-photo mitigation for OCR risk.
- Grading order is resolution-hard-reject, then blur-hard-reject, then resolution-or-blur-warn, then ok — so a badly undersized image never reaches the blur check, matching the plan's stated order.
- `grade_image` catches only `PIL.UnidentifiedImageError` and re-raises as `ValueError`; no bare `except Exception` that could mask a real bug.

## Threshold Calibration (Provisional)

Blur/resolution thresholds are **explicitly provisional**, calibrated only against `PIL.Image.effect_noise`-generated synthetic pages, not real user photos, per CONTEXT.md's deferred-tuning decision:

- `min_dimension = 1000` (hard reject floor at `500`, half of this)
- `blur_warn = 100.0`
- `blur_reject = 5.0`

Calibration data (Laplacian variance via the module's exact kernel, on a 1200x1600 synthetic noise page):

| Condition | blur_variance |
|---|---|
| Sharp (no blur) | ~12,198 |
| `GaussianBlur(radius=2)` (warn case) | ~8.4 |
| `GaussianBlur(radius=8)` (reject case) | ~1.0 |

These values are not meaningful for real printed-text photos (synthetic noise has a very different frequency spectrum than a scanned page) and must be re-tuned once real user-submitted photos are available, per CONTEXT.md's "Claude's Discretion" deferral. Plan 06, which wires these as `Settings` defaults, should carry this same provisional label forward.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `typing.Any` triggered ruff ANN401 on `select_file_id`'s parameters**
- **Found during:** Task 1 GREEN verification
- **Issue:** The initial signature used `Any` for `photo_sizes`/`document` per the plan's "duck-typed... without importing aiogram" instruction, but the project's ruff config (`ANN` rule set) disallows dynamically-typed `Any` in signatures.
- **Fix:** Replaced `Any` with two local `typing.Protocol` classes (`_PhotoSizeLike`, `_DocumentLike`) declaring only the attributes actually read (`file_id`, `mime_type`), preserving the no-aiogram-import requirement while satisfying static typing.
- **Files modified:** `src/bot/images/extract.py`
- **Verification:** `ruff check src/bot/images/` exits 0
- **Committed in:** `6c3b6a5`

**2. [Rule 3 - Blocking] `python3` on PATH resolved to 3.14, outside the project's `>=3.12,<3.13` pin**
- **Found during:** Environment setup before running any tests
- **Issue:** `pip install -e ".[dev]"` failed with a Python-version mismatch against the system `python3` (3.14.7).
- **Fix:** Located an existing `/usr/local/bin/python3.12` interpreter already on the machine and built `.venv` from it; no new interpreter was installed, no package substitution occurred. `.venv/` is gitignored and local to this worktree only.
- **Files modified:** none (environment only)
- **Verification:** `.venv/bin/python --version` reports 3.12; full test suite (33 tests across the repo) passes

**3. [Rule 1 - Bug] Test count short of the 16-test acceptance floor**
- **Found during:** Task 2 GREEN verification
- **Issue:** The eight behaviors listed in the plan's `<behavior>` block for Task 2 produced 7 distinct test functions once implemented (one behavior — "width/height equal decoded dimensions in every case" — was folded into two existing tests rather than given its own), landing at 15 total tests in the file against the plan's stated floor of 16.
- **Fix:** Added a dedicated `test_width_and_height_match_decoded_dimensions_in_every_case` test that checks the dimensions-match invariant across all four synthetic image cases (sharp, small, radius-8 blur, radius-2 blur) in one place, bringing the file to 16 tests.
- **Files modified:** `tests/test_images.py`
- **Verification:** `pytest tests/test_images.py -q` reports 16 passed
- **Committed in:** `518859b`

---

**Total deviations:** 3 auto-fixed (1 bug/lint, 1 blocking/environment, 1 bug/coverage)
**Impact on plan:** No behavior change to the shipped interface; all fixes are either typing-only, environment-local, or additive test coverage.

## Issues Encountered
- Same macOS `.pth`-file `UF_HIDDEN` quirk noted in plan 01's SUMMARY (likely iCloud Desktop sync interference, since the project lives under `~/Desktop`) caused a bare `python -c "from bot.images... import"` to fail intermittently while `pytest` (which sets `pythonpath` explicitly) kept working. Verified the acceptance-criteria import command with `PYTHONPATH=src` as the same documented workaround; no effect on the committed repository.

## User Setup Required
None. This plan requires no credentials and makes no network calls — verified by running the full suite with none present.

## Next Phase Readiness
- Plan 06 can import `select_file_id`, `ImageSource`, `grade_image`, `QualityGrade`, `QualityReport`, `to_data_url` from `bot.images.extract` exactly as declared in this plan's `<interfaces>` block, and wire `min_dimension`/`blur_warn`/`blur_reject` from `Settings` — no signature changes needed.
- The provisional threshold values above should be treated as the literal starting `Settings` defaults, explicitly labeled non-final, until plan 06 or a later plan tunes them against real user photos.
- No blockers carried forward.

---
*Phase: 01-core-inference-loop*
*Completed: 2026-09-10*

## Self-Check: PASSED

All 3 created files verified present on disk (`src/bot/images/__init__.py`, `src/bot/images/extract.py`, `tests/test_images.py`); all 4 task commit hashes (`42401f7`, `6c3b6a5`, `a5d76c6`, `518859b`) verified present in `git log`.
