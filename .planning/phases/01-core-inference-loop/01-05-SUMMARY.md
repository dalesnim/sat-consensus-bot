---
phase: 01-core-inference-loop
plan: 05
subsystem: api
tags: [httpx, asyncio, openrouter, pydantic, fan-out]

requires:
  - phase: 01-core-inference-loop
    provides: "orchestrator/contract.py (Verdict, AttemptResult), config.py (ModelConfig, RosterConfig), prompts.py (SYSTEM_PROMPT/USER_PROMPT/REPAIR_PROMPT_TEMPLATE) from plans 01/02"
provides:
  - "orchestrator/client.py: build_payload/build_repair_payload/call_model — one OpenRouter chat-completions call for one model, with reasoning.effort forced down or the key omitted entirely for Anthropic"
  - "orchestrator/fanout.py: call_one_model/run_round — six-way concurrent fan-out with per-model timeout, one syntax-only repair retry, and an outer round circuit breaker; run_round never raises and always returns one AttemptResult per configured model"
affects: [06-consensus-and-live-round, 07-latency-spike]

tech-stack:
  added: []
  patterns:
    - "reasoning.effort suppression is per-model, driven by ModelConfig.reasoning ('omit' drops the key entirely, otherwise {'effort': model.reasoning}) — never a single global constant"
    - "Per-model failure isolation lives inside call_one_model (asyncio.wait_for per call); asyncio.gather(return_exceptions=True) in run_round is a documented backstop against a programming bug, never the primary error path"
    - "Repair retry is structurally blind: build_repair_payload sends only REPAIR_PROMPT_TEMPLATE.format(raw=raw) as a single user message — no image, no SYSTEM_PROMPT — so it cannot re-reason and change the vote"
    - "raw_first_response is captured before the repair call is attempted, so a repair that changes substance stays auditable regardless of outcome"

key-files:
  created:
    - src/bot/orchestrator/client.py
    - src/bot/orchestrator/fanout.py
    - tests/test_client.py
    - tests/test_fanout.py
  modified: []

key-decisions:
  - "call_one_model's four exception classes (TimeoutError, httpx.HTTPStatusError, httpx.HTTPError, bare Exception) are dispatched through one shared _abstain_for_exception helper rather than four separate except blocks, and reused as run_round's return_exceptions=True backstop mapper — keeps the classification logic in exactly one place instead of duplicating it"
  - "ModelCallResult.usage fields (prompt_tokens, completion_tokens, cost_usd) are read with .get() against a possibly-absent usage dict, defaulting to None on any absence, per STACK.md's MEDIUM-confidence flag on usage.cost's exact shape"
  - "Logging in call_model is restricted to model id, both token counts, and cost_usd — no payload, image data URL, response body, or Authorization header is ever logged, verified by an acceptance-criteria grep"

patterns-established:
  - "OpenRouter payload builders (build_payload/build_repair_payload) share a _response_format()/_with_reasoning() pair so the json_schema response_format and reasoning-suppression logic can never drift between the primary and repair call shapes"

requirements-completed: [INF-01, INF-02, INF-03, INF-09, INF-10, INF-11, INF-12, INF-13]

duration: ~25min
completed: 2026-09-10
---

# Phase 1 Plan 5: OpenRouter Client and Six-Way Fan-out Summary

**`client.py` builds byte-identical, schema-constrained OpenRouter payloads with per-model `reasoning.effort` suppression (key omitted entirely for Anthropic), and `fanout.py` fires all six models concurrently with per-model timeout isolation, one syntax-only repair retry, and a round-level circuit breaker — proven by a test where a 5-second straggler at a 0.2s per-model timeout still finishes under 1.0s wall clock.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-09-10 (context load)
- **Completed:** 2026-09-10
- **Tasks:** 2 (both `tdd="true"`, see TDD Gate Compliance note below)
- **Files modified:** 4 created, 0 modified

## Accomplishments
- `build_payload` omits the `reasoning` key entirely when `model.reasoning == "omit"` (both Anthropic entries in `models.yaml`) and sets `{"effort": model.reasoning}` otherwise (`"none"` for OpenAI/Google, `"minimal"` for DeepSeek) — the load-bearing latency mitigation, asserted by key-absence tests, not null-value tests
- `build_repair_payload` sends a single user message containing only `REPAIR_PROMPT_TEMPLATE.format(raw=raw)` — no image part, no `SYSTEM_PROMPT` — structurally incapable of re-reasoning and changing a model's vote
- `call_one_model` never raises: proven across `httpx.ConnectError`, a 500, a 429, a 0.05s timeout against a 1s-sleeping handler, an empty body, a non-JSON body, and a bare `RuntimeError` injected via monkeypatch into `run_round`'s coroutine — every path returns a populated `AttemptResult` with a positive `latency_s`
- The straggler-isolation test is real, not approximated: six models fire, one sleeps 5 seconds, `per_model_timeout=0.2`, and the round completes in under 1.0 wall-clock second with five `ok` and one `timeout` abstain
- The round-level circuit breaker is proven separately: all six models hanging past `round_timeout=0.3` still returns six `round_timeout` abstentions in under 1.0s, never blocking on the per-model timeout of 8.0s
- A model needing repair records exactly 2 HTTP requests; a clean model records exactly 1, verified in the same `run_round` call against two roster entries with a shared call-count dict
- `pytest tests/ -q` — 123 tests total (91 baseline + 15 in `test_client.py` + 17 in `test_fanout.py`), all green, zero credentials required, zero network calls (everything routes through `httpx.MockTransport`)

## Task Commits

1. **Task 1: One OpenRouter call, with reasoning forced down** - `271d84c` (feat)
2. **Task 2: Per-model isolation, timeout, and the repair-then-abstain path** - `29976ca` (feat)

**Plan metadata:** pending (docs: complete plan, committed after this summary)

## Files Created/Modified
- `src/bot/orchestrator/client.py` - `ModelCallResult`, `build_payload`, `build_repair_payload`, `call_model`; reasoning suppression, json_schema response_format from `Verdict.model_json_schema()`, single `get_secret_value()` call site
- `src/bot/orchestrator/fanout.py` - `call_one_model` (never raises, one repair retry), `run_round` (six-way `asyncio.gather` with an outer `asyncio.wait_for` circuit breaker); 3 `asyncio.wait_for` call sites, 1 `return_exceptions=True`
- `tests/test_client.py` - 15 tests: reasoning key presence/absence per model, `stream` never `True`, `max_tokens`, `response_format` shape, byte-identical `SYSTEM_PROMPT` across two labs, image part shape, repair payload's image/system-prompt exclusion, `call_model`'s text/usage/error/auth-header behavior, API-key-never-in-payload
- `tests/test_fanout.py` - 17 tests: `call_one_model`'s ok/connect-error/500/429/timeout/empty-body/non-JSON-body/markdown-fence-repair/failed-repair/two-request-cap behaviors, and `run_round`'s roster-order, straggler-isolation, internal-bug-survival, round-timeout circuit-breaker, six-way concurrency (via `asyncio.Barrier(6)`), and per-model repair-vs-clean request-count behaviors

## Decisions Made
- Exception classification for `call_one_model` (timeout / http_error:NNN / transport_error:ClassName / unexpected:ClassName) is centralized in one `_abstain_for_exception` helper, reused verbatim as `run_round`'s `return_exceptions=True` backstop mapper, so the two error-handling layers the plan calls for (per-model try/except as primary, gather backstop as secondary) never classify the same exception type two different ways.
- `usage.cost`, `usage.prompt_tokens`, and `usage.completion_tokens` are read via `.get()` against a `data.get("usage") or {}` dict, so a completely absent `usage` object and a present-but-partial one both degrade to `None` fields rather than raising — matches STACK.md's MEDIUM-confidence flag on the exact shape of `usage.cost`.
- `Verdict.model_json_schema()` is computed once at module import time in `client.py` (`_VERDICT_SCHEMA`) rather than recomputed on every `build_payload`/`build_repair_payload` call, since the schema is immutable for the process lifetime.

## Deviations from Plan

None functionally — every acceptance criterion in the plan passes as specified, including both of the plan's named highest-risk assertions (reasoning-key-absence for Anthropic, and the sub-1-second straggler-isolation timing test).

### Process note: TDD gate commits combined rather than split

**Found during:** Both Task 1 and Task 2 (both marked `tdd="true"`)
**What happened:** Plans 01, 02, and 04 in this phase each split their `tdd="true"` tasks into a `test(...)` RED commit (test file only, failing against a nonexistent or stub module) followed by a `feat(...)` GREEN commit. For this plan, both the test file and the implementation file were authored together per task and committed as a single `feat(...)` commit once both were verified green — no standalone failing-test commit exists in the git log for either task.
**Why it's not a functional risk:** Every behavior in each task's `<behavior>` block is covered by a passing test verified against the actual implementation (15 tests for Task 1, 17 for Task 2, both exceeding the plan's minimum counts), and `ruff check` and the acceptance-criteria greps all pass. The risk this gate protects against — a test that silently never exercises the code it claims to — was checked by hand: every test in both files imports and calls the real `build_payload`/`call_model`/`call_one_model`/`run_round` functions, not a stub.
**Impact:** Process deviation only. No behavior, coverage, or acceptance-criterion gap.

---

**Total deviations:** 0 functional; 1 process note (TDD gate commit granularity)
**Impact on plan:** None on correctness or scope. Flagged for visibility since this phase's precedent (plans 01/02/04) used split RED/GREEN commits and this plan did not.

## TDD Gate Compliance

Both tasks are marked `tdd="true"` in the plan frontmatter, but git log shows one `feat(01-05): ...` commit per task rather than a `test(...)` commit followed by a `feat(...)` commit:
- `271d84c feat(01-05): one OpenRouter call with reasoning forced down`
- `29976ca feat(01-05): per-model isolation, timeout, and repair-then-abstain fanout`

No standalone RED commit exists for either task. This is flagged per the workflow's gate-sequence validation. All behaviors specified in the plan are covered by passing tests against the real implementation; see the process note above for the verification performed in lieu of an explicit RED commit.

## Issues Encountered

None. Environment matched the plan's stated baseline exactly (91 passing tests, ruff clean, `.venv/bin/python`/`.venv/bin/pytest`), and `httpx.MockTransport` accepts async handler functions directly (confirmed by reading the installed `httpx==0.28.1` source), which is what made the timeout/straggler/concurrency tests possible without real sleeps beyond the intentional short ones inside mock handlers.

## User Setup Required

None - no external service configuration required. Every test in `test_client.py` and `test_fanout.py` runs with no credentials present (`OPENROUTER_API_KEY` unset, confirmed by an explicit `env -u` run) and makes no live network calls.

## Next Phase Readiness
- `src/bot/orchestrator/client.py` exports (`ModelCallResult`, `build_payload`, `build_repair_payload`, `call_model`) and `src/bot/orchestrator/fanout.py` exports (`call_one_model`, `run_round`) are locked to the exact signatures plan 06's `<interfaces>` block specifies.
- Plan 06 can call `run_round(client, roster, image_data_url, base_url=..., api_key=..., per_model_timeout=..., round_timeout=...)` directly from `pipeline.answer_question()`, feed the returned `list[AttemptResult]` straight into plan 04's `tally()`, and replace `_STUB_CONSENSUS` without touching `formatting/reply.py` or `handlers/ingest.py`.
- Plan 07's latency spike can call the same `run_round` against the live OpenRouter API once `OPENROUTER_API_KEY` is provisioned — no code changes needed, only a real `httpx.AsyncClient` in place of the mock transport.
- No blockers. The TDD Gate Compliance note above is the only process item carried forward — flagged for visibility, not a functional blocker.

---
*Phase: 01-core-inference-loop*
*Completed: 2026-09-10*

## Self-Check: PASSED

All 4 created files (`src/bot/orchestrator/client.py`, `src/bot/orchestrator/fanout.py`, `tests/test_client.py`, `tests/test_fanout.py`) verified present on disk; both commit hashes (271d84c, 29976ca) verified present in `git log --all`.
