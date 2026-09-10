---
phase: 01-core-inference-loop
plan: 07
subsystem: tooling
tags: [spike, latency, measurement, openrouter, credentials, readme]

requires:
  - phase: 01-core-inference-loop
    provides: "build_payload/call_model (plan 05), load_settings/load_roster (plan 02), to_data_url (plan 03), answer_question (plan 06) — all consumed unchanged by the spike"
provides:
  - "scripts/latency_spike.py — one-shot measurement of real wall clock, prompt/completion tokens, and cost per model against the exact request shape the bot sends"
  - "SPIKE-RESULTS.md — three recorded live runs replacing the MEDIUM-confidence research latency estimate with measurement"
  - "The resolved cost JSON path (usage.cost), which Phase 2 spend accounting depends on"
  - "README.md — local run, test, validate-only, spike, and docker instructions"
affects: [02-04-spend-cap, 02-05-cost-command]

tech-stack:
  added: []
  patterns:
    - "The spike deliberately omits asyncio.wait_for — measuring true model latency past the 22s per-model timeout is the entire point, so a straggler is recorded rather than cancelled"
    - "Live-contact defects that mocked transports structurally cannot catch (provider-side reasoning.effort rejection, strict-schema additionalProperties, upstream 429 on image payloads) are found here and only here"

key-files:
  created:
    - scripts/latency_spike.py
    - README.md
    - .planning/phases/01-core-inference-loop/SPIKE-RESULTS.md
  modified:
    - models.yaml
    - src/bot/orchestrator/client.py

key-decisions:
  - "max_tokens was NOT lowered to the spike's 1800 recommendation and instead later raised to 3000: the recommendation was computed from a six-model roster that was subsequently replaced on measured accuracy, and the accuracy-selected roster emits longer elimination reasoning. The spike's function — turning an estimate into a measurement — was served; its specific number was superseded by newer measurement, not ignored."
  - "reasoning.effort: none is not universally accepted. gpt-6-astra and gemini-3.7-flash reject it outright ('Reasoning is mandatory for this endpoint'); both moved to minimal. This invalidated a Phase 1 planning assumption that the suppression was uniform across providers."
  - "The pydantic-generated JSON schema needed _strictify (setting additionalProperties: false and required on every nested object node) before gpt-5.6-sol would accept it under strict mode — provider strict-mode enforcement is stricter than model_json_schema()'s default output."
  - "deepseek/deepseek-v4.1-flash was dropped from the roster: persistently 429 rate-limited upstream on image payloads via the shared DeepInfra pool while text-only calls succeeded. This silently dropped the live roster to 3 labs and broke the lab-diversity premise, which no unit test could have detected."
  - "Task 2 (credential provisioning) and Task 3 (live spike + first real round) were human checkpoints, both satisfied on 2026-09-10: .env exists and is git-ignored, three spike runs are recorded, and the bot has been serving real questions in production since."

patterns-established:
  - "A live spike is the correct instrument for provider-contract defects. Every one of the three defects in 82f75c1 was invisible to a 137-test suite running against mocked transports, because each lived in the provider's acceptance rules rather than in our code's logic."

requirements-completed: [CFG-02, CFG-03, CFG-04, CFG-06, ING-01, INF-09]

duration: ~45min (across the original build and the live-contact fix cycle)
completed: 2026-09-10
---

# Phase 1 Plan 7: Empirical Latency Spike Summary

**Replaced the project's largest MEDIUM-confidence assumption — a 27-second latency estimate interpolated from third-party benchmarks — with three recorded live measurements against the real prompt, the real image shape, and the real models, and in doing so exposed three provider-contract defects that a fully green mocked test suite was structurally incapable of catching.**

## Performance

- **Duration:** ~45 min including the follow-up fix cycle
- **Completed:** 2026-09-10
- **Tasks:** 3 (1 auto, 2 human checkpoints — both satisfied)
- **Files:** 3 created, 2 modified

## Accomplishments

- `scripts/latency_spike.py` fires the whole roster once through `build_payload` and `call_model` — the identical code path the bot uses, not a parallel request builder — with no per-model timeout, and records wall clock, `usage.prompt_tokens`, `usage.completion_tokens`, `usage.cost`, first-try parse success, and the exception type per model.
- The script refuses to report a measurement from fewer than four successful models (non-zero exit), so a broken run cannot silently become the basis for a `max_tokens` decision. This fired on the first run (2/6) and prevented exactly that.
- Cost is present at `usage.cost` — this resolves the flagged research gap that Phase 2 spend accounting (02-04, 02-05) depends on.
- Round wall clock measured at 32.6s → 19.4s → 22.1s across the three runs as the defects were fixed. The final six-model round came in at 22.1s with 6/6 models returning.
- Three live-contact defects found and fixed in `82f75c1`, none of which a mocked transport could reach:
  1. `reasoning.effort: none` rejected outright by gpt-6-astra and gemini-3.7-flash → both moved to `minimal`.
  2. gpt-5.6-sol rejects the pydantic-generated schema under strict mode for nested objects missing `additionalProperties: false` → `_strictify` added to `client.py`.
  3. deepseek/deepseek-v4.1-flash persistently 429 on image payloads via the shared upstream pool while text-only succeeded, silently collapsing the roster from 4 labs to 3 at runtime → replaced.
- `README.md` documents setup, `pytest -q`, the free `python -m bot --validate-only`, the spike, local run, and docker compose, and states that `.env` is git-ignored and must never be committed.
- Security posture verified: `git log --all --name-only` shows `.env` was never committed on any branch, `git check-ignore .env` exits 0, `grep 'sk-or-' README.md` returns nothing, and the script contains no `get_secret_value` call — the key is passed through and never unwrapped for printing.

## Task Commits

1. **Task 1: Empirical latency spike script** — `d1c17ec` (feat)
2. **Live-contact fixes exposed by Task 3** — `82f75c1` (fix)

## Deviations from Plan

- **`max_tokens` left above the spike's recommendation.** The plan directed lowering `max_tokens` to the `## Decision` value if below 2000; the final run recommended 1800. It was not applied, and the value later moved to 3000. Reason: the six-model roster the recommendation was computed against was itself replaced shortly afterward on measured accuracy over a 17-question labeled set, and the accuracy-selected roster produces longer elimination reasoning. Truncating it at 1800 would have cost correctness to save a budget that was never binding. The plan's actual purpose — replacing an estimate with a measurement — was served.
- **Roster changed after the spike.** The plan assumed the six IDs it measured were final. They were not: the roster is now seven models across five labs plus a conditional tiebreak, chosen on accuracy rather than on the lab-diversity heuristic Phase 1 planned around.

## Follow-ups for Phase 2

- **T-07-06 (deferred by design):** the bot handle has no allowlist gate until ACC-01 lands. Allowlist enforcement shipped in 02-03; this is now closed.
- Spend accounting (02-04, 02-05) can rely on `usage.cost` being present at that exact path — confirmed across three live runs.
