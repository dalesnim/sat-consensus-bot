---
phase: 01-core-inference-loop
plan: 02
subsystem: infra
tags: [pydantic-settings, pyyaml, httpx, docker, openrouter, boot-validation]

requires:
  - phase: 01-core-inference-loop
    provides: "Plan 01's installable package, orchestrator/contract.py shapes, and main()/handlers skeleton this plan edits"
provides:
  - "models.yaml as the single source of the six-model roster, each entry's lab, and its per-model reasoning mode"
  - "Typed Settings/RosterConfig/ModelConfig with SecretStr-protected credentials, network-free load_settings()/load_roster()"
  - "validate_roster() — live OpenRouter /models catalog cross-check for existence, image-input support, structured_outputs support, and lab diversity, all in one BootValidationError message"
  - "main() wired to fail loudly (SystemExit(1)) on any invalid roster before start_polling, plus a --validate-only entrypoint usable with zero credentials"
  - "Dockerfile + docker-compose.yml + .dockerignore packaging the bot as a non-root container with a persistent sqlite_data volume for Phase 2"
affects: [05-model-fanout, 06-consensus-and-live-round, 07-latency-spike]

tech-stack:
  added: []
  patterns:
    - "Settings/RosterConfig loading is pure and network-free; validate_roster is the only network-touching boot step, called once from main() before include_router/start_polling"
    - "--validate-only bypasses Settings() entirely (reads OPENROUTER_BASE_URL/MODELS_CONFIG_PATH straight from Settings' own field defaults) so it never requires TELEGRAM_BOT_TOKEN or OPENROUTER_API_KEY"
    - "BootValidationError accumulates every failure category (missing ID, no image, no structured_outputs, lab-diversity shortfall) into one message before raising, never fails fast on the first bad ID"

key-files:
  created:
    - models.yaml
    - .env.example
    - src/bot/config.py
    - src/bot/validation/__init__.py
    - src/bot/validation/boot.py
    - Dockerfile
    - docker-compose.yml
    - .dockerignore
    - tests/fixtures/openrouter_models.json
    - tests/test_config.py
    - tests/test_boot_validation.py
  modified:
    - src/bot/main.py

key-decisions:
  - "reasoning: omit for both Anthropic models means the request body carries no reasoning key at all (extended thinking never enabled), matching STACK.md's latency finding that Anthropic's 1024-token thinking floor is worse for the 30s budget than leaving reasoning unset"
  - "--validate-only reads OPENROUTER_BASE_URL/MODELS_CONFIG_PATH via Settings.model_fields[...].default rather than constructing Settings(), since Settings requires both secrets with no default and the plan mandates --validate-only work with zero credentials"
  - "Scoped the .env.example anti-leak test to TOKEN/KEY-named variables only, since the legitimate OPENROUTER_BASE_URL default (29 chars) would otherwise fail a blanket 20-char rule"

patterns-established:
  - "TDD gate for both config.py and boot.py: RED commit before GREEN commit, enforced per the plan's tdd=\"true\" flag on Tasks 1 and 2"

requirements-completed: [CFG-01, CFG-02, CFG-03, CFG-04, CFG-05, CFG-06]

duration: ~35min
completed: 2026-09-10
---

# Phase 1 Plan 2: Data-Driven Roster and Boot Validation Summary

**models.yaml-driven six-model roster with SecretStr-protected typed settings, a live OpenRouter catalog boot validator that names every offending model ID in one message, and non-root Docker Compose packaging — verified end to end against the real OpenRouter API with zero credentials set.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-09-10T21:05:00+05:00 (approx)
- **Completed:** 2026-09-10T21:15:28Z
- **Tasks:** 3 (2 TDD, 1 plain auto)
- **Files modified:** 11 created, 1 modified (`src/bot/main.py`)

## Accomplishments
- The corrected six-model roster (`anthropic/claude-opus-5`, `anthropic/claude-sonnet-5`, `openai/gpt-6-astra`, `openai/gpt-5.6-sol`, `google/gemini-3.7-flash`, `deepseek/deepseek-v4.1-flash`), each model's lab, and its per-model `reasoning` mode live only in `models.yaml` — zero model IDs anywhere in `src/`
- `Settings`/`RosterConfig`/`ModelConfig` are fully typed, network-free, and both credential fields are `pydantic.SecretStr` — confirmed the raw secret never appears in `repr(Settings())`
- `validate_roster()` live-verified against the real `https://openrouter.ai/api/v1/models` catalog: `python -m bot --validate-only` printed `roster ok: 6 models, 4 labs` and exited 0 with `TELEGRAM_BOT_TOKEN`/`OPENROUTER_API_KEY` both unset
- Manually confirmed the failure path: pointing `MODELS_CONFIG_PATH` at a roster with a nonexistent model ID produced `roster validation failed: absent from OpenRouter catalog: anthropic/claude-opus-999-does-not-exist` at CRITICAL and exit code 1
- Dockerfile/docker-compose.yml/.dockerignore written per spec; since no `docker` binary exists in this sandbox, validated by simulating the exact build context (`pyproject.toml` + `src/` + `models.yaml`) in an isolated venv — `pip install --no-cache-dir .` succeeded and `python -m bot --validate-only` ran correctly from that install

## Task Commits

Each task was committed atomically (TDD tasks have RED + GREEN commits):

1. **Task 1: Roster file, typed settings, and .env.example**
   - `1dc97d7` (test, RED) — failing `tests/test_config.py` plus `models.yaml`/`.env.example`
   - `c80915e` (feat, GREEN) — `src/bot/config.py` implementation, 11/11 tests passing
2. **Task 2: Boot-time validation against the live OpenRouter catalog**
   - `966bb96` (test, RED) — failing `tests/test_boot_validation.py` plus the catalog fixture
   - `23802fc` (feat, GREEN) — `src/bot/validation/boot.py` + `src/bot/main.py` wiring, 9/9 tests passing, live-verified
   - `972d6e0` (fix) — ruff line-length cleanup in the test file, found during full-project lint pass
3. **Task 3: Docker Compose packaging** - `becfb5f` (feat)

**Plan metadata:** pending (docs: complete plan, committed after this summary)

## Files Created/Modified
- `models.yaml` - the six-model roster: id, lab, reasoning per model, plus `min_distinct_labs: 4` and `max_tokens: 2000`
- `.env.example` - all 13 environment variables documented with defaults, secrets left empty
- `src/bot/config.py` - `ModelConfig`, `RosterConfig`, `Settings` (SecretStr credentials), `load_roster`, `load_settings`
- `src/bot/validation/__init__.py` - empty package marker
- `src/bot/validation/boot.py` - `BootValidationError`, `validate_roster` (catalog existence + image modality + structured_outputs + lab-diversity, all failures accumulated into one message)
- `src/bot/main.py` - `main()` now loads settings/roster, validates the roster before `include_router`/`start_polling`, exits 1 with a CRITICAL log on `BootValidationError`, and supports `--validate-only`
- `Dockerfile` - `python:3.12-slim`, non-root uid 10001, no `.env`/`tests`/`.planning` copied in
- `docker-compose.yml` - single `bot` service, `restart: unless-stopped`, `env_file: .env`, named `sqlite_data` volume, capped json-file logging
- `.dockerignore` - mirrors `.gitignore` plus build/test artifacts
- `tests/fixtures/openrouter_models.json` - six roster entries plus two decoys, structured as OpenRouter's real `/models` response
- `tests/test_config.py` - 11 tests covering roster/settings behavior
- `tests/test_boot_validation.py` - 9 tests covering every validate_roster failure mode via `httpx.MockTransport`

## Decisions Made
- `reasoning: omit` for both Anthropic models emits no `reasoning` key at all in the request body (extended thinking never enabled) rather than setting a minimal `max_tokens` budget — matches STACK.md's finding that Anthropic's 1024-token thinking floor eats too much of the 2000-token completion cap.
- `--validate-only` deliberately avoids calling `load_settings()` (which requires both secrets with no default) and instead reads `OPENROUTER_BASE_URL`/`MODELS_CONFIG_PATH` directly, falling back to `Settings.model_fields[...].default` — this is the only way to satisfy the plan's explicit requirement that `--validate-only` runs with `TELEGRAM_BOT_TOKEN` and `OPENROUTER_API_KEY` both unset while `Settings` still treats those two fields as required elsewhere.
- The `.env.example` anti-leak test only enforces the 20-character ceiling on lines whose variable name contains `TOKEN` or `KEY`, since a blanket rule would fail against the legitimate `OPENROUTER_BASE_URL` default.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Ruff line-length violations in test_boot_validation.py**
- **Found during:** Full-project `ruff check .` run after Task 2
- **Issue:** Two lines (a helper function signature, a list comprehension) exceeded the configured 100-char line length.
- **Fix:** Re-wrapped both lines without changing behavior.
- **Files modified:** `tests/test_boot_validation.py`
- **Verification:** `ruff check .` exits 0; all 37 tests still pass.
- **Committed in:** `972d6e0`

**2. [Rule 3 - Blocking] Plan's inline `--validate-only` design conflicted with Settings' required secrets**
- **Found during:** Task 2, writing `main.py`
- **Issue:** The plan's interface spec makes `TELEGRAM_BOT_TOKEN`/`OPENROUTER_API_KEY` required fields on `Settings` with no default, but the same plan's acceptance criteria requires `--validate-only` to run with both unset. Calling `load_settings()` unconditionally would raise `ValidationError` before validation could even run.
- **Fix:** `main()` branches on `--validate-only`: in that mode it reads `OPENROUTER_BASE_URL`/`MODELS_CONFIG_PATH` from the environment (falling back to `Settings`' own field defaults) without constructing a `Settings` instance at all; the normal boot path still calls `load_settings()` as specified.
- **Files modified:** `src/bot/main.py`
- **Verification:** `python -m bot --validate-only` with both env vars unset reaches the live catalog and prints `roster ok: 6 models, 4 labs`, exit 0.
- **Committed in:** `23802fc`

---

**Total deviations:** 2 auto-fixed (1 lint, 1 blocking-issue resolution)
**Impact on plan:** No scope creep; the second item resolves an internal inconsistency in the plan spec itself (required-secret Settings vs. credential-free validate-only), necessary for the plan's own acceptance criteria to be satisfiable.

## Issues Encountered
- **No `docker` binary in this sandbox.** The plan's Task 3 `<verify>` block (`docker compose config -q`, `docker build`, `docker run`) could not execute directly. Mitigated by: (1) `yaml.safe_load`-based structural validation of `docker-compose.yml` (single `bot` service, `restart: unless-stopped`, named `sqlite_data` volume, no `depends_on`); (2) simulating the Dockerfile's `pip install --no-cache-dir .` step in an isolated venv against an exact copy of the build context (`pyproject.toml` + `src/` + `models.yaml`, nothing else), which succeeded; (3) running `python -m bot --validate-only` from that simulated install, which reached the live catalog and printed `roster ok: 6 models, 4 labs`. The actual `docker build`/`docker run` acceptance criteria (non-root uid, `.env`/`tests`/`.planning` absence from the image) rely on `.dockerignore` and the Dockerfile's explicit `COPY` list being correct, which were reviewed by hand against the plan's requirements — this is the one area of this plan not verified by an executed command and should be spot-checked on the actual deployment VPS before first use.
- **`grep -c 'deepseek/deepseek-v4$' models.yaml` false-negative risk avoided:** confirmed `deepseek/deepseek-v4.1-flash` (not the nonexistent `deepseek/deepseek-v4`) is the only DeepSeek entry in `models.yaml`.
- **Coincidental substring collision in the plan's inline repr-leak check:** `assert 'y' not in repr(Settings())` (using `OPENROUTER_API_KEY=y` as the test value) fails not because of a secret leak but because `models_config_path`'s default value `models.yaml` contains the letter "y" (from `.yaml`) in the repr. Verified by hand that `repr(Settings())` correctly renders `SecretStr('**********')` for both credential fields with no trace of the real secret value. The project's actual `test_settings_repr_never_leaks_secrets` test in `tests/test_config.py` uses unambiguous secret strings (`"super-secret-token"`, `"super-secret-key"`) and passes cleanly — this is the test that should be trusted for T-02-01.

## User Setup Required

None - no external service configuration required. `.env.example` documents everything needed; a real `.env` with `TELEGRAM_BOT_TOKEN` and `OPENROUTER_API_KEY` is still required before the bot can actually serve Telegram traffic (carried forward from Plan 01), but every test and the boot validator itself run without it.

## Next Phase Readiness
- `src/bot/config.py` exports (`ModelConfig`, `RosterConfig`, `Settings`, `load_roster`, `load_settings`) and `src/bot/validation/boot.py` exports (`BootValidationError`, `validate_roster`) are locked and tested, per this plan's `<interfaces>` contract — plans 05 and 07 can import them unchanged.
- No blockers for plans 03/04 (running in parallel in sibling worktrees) or for wave 3 plans that depend on this one.
- One item to verify once Docker is available in a real environment: `docker build` + `docker run --rm ... id -u` should print `10001`, and `docker run --rm ... ls /app` should show no `.env`/`tests`/`.planning` — both are expected to pass given the Dockerfile's explicit `COPY` list and `USER bot` directive, but were not executed against an actual Docker daemon in this sandbox.

---
*Phase: 01-core-inference-loop*
*Completed: 2026-09-10*

## Self-Check: PASSED

All 13 files (11 created, 1 modified, this summary) verified present on disk; all 6 commit hashes (1dc97d7, c80915e, 966bb96, 23802fc, 972d6e0, becfb5f) verified present in `git log --all`.
