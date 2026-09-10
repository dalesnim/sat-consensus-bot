# Overnight handoff — read this before doing anything

Written 2026-09-11 00:55 by the session that built Phase 1 and half of Phase 2.
The owner is asleep and has given consent to proceed unattended, choosing the
recommended option at every decision point. Do not wait for input.

## HARD RULES FOR UNATTENDED WORK

1. **DO NOT SPEND OPENROUTER MONEY.** The balance is ~$10.32 and the owner has
   very little money. Every question costs ~$0.247. Do NOT run
   `scripts/model_bakeoff.py`, `scripts/latency_spike.py`, or any script that
   calls `/chat/completions`. All tests must mock httpx at the transport layer.
   `python -m bot --validate-only` is FREE (public catalog endpoint) and is fine.
2. **DO NOT move the project directory.** It sits under `~/Desktop`, which
   causes two known problems (below). Moving it mid-run would break the running
   bot and the venv. Leave it.
3. **DO NOT change the model roster.** It was chosen on measured accuracy
   against a 17-question labeled set. See `data/answer_key.json` and
   `data/bakeoff.json`.
4. **DO NOT restart or stop the bot** unless a plan requires it. It is running
   under `./bot.sh` and the owner may be using it.

## Current state

- Phase 1: COMPLETE (core inference loop, live and working)
- Phase 2: 02-01 (persistence) and 02-03 (allowlist) DONE.
  REMAINING: 02-02 (phash cache), 02-04 (spend cap), 02-05 (/cost)
- Phase 3: not started. ING-08 (typing indicator) already shipped early.
- Tests: 189 passing, ruff clean. Do not regress.

## Environment gotchas

- Use `.venv/bin/python` and `.venv/bin/pytest`. System `python3` is 3.14,
  outside the project's `<3.13` pin.
- If `import bot` fails with ModuleNotFoundError, prefix `PYTHONPATH=src`.
  Cause: iCloud sync on ~/Desktop intermittently re-hides the editable-install
  `.pth` file. pytest is unaffected.
- macOS TCC blocks LaunchAgents under ~/Desktop, so auto-start on boot cannot
  work from here. Already attempted and reverted. Do not retry.

## Roster (do not change)

Round of 7: x-ai/grok-4.6, google/gemini-3.1-pro-preview, openai/gpt-6-astra,
anthropic/claude-opus-5, anthropic/claude-sonnet-5, qwen/qwen3.8-max-0902,
google/gemini-3.7-flash.
Tiebreak model, called ONLY on an unresolved split:
anthropic/claude-fable-5.1.
Free tiebreak pair checked before escalating: opus-5 + gpt-6-astra.

## Measured facts

- Cost ~$0.247/question (7 models, plus fable on ~1 in 17).
- Round wall time 16-28s. Budget 47s per model / 50s round.
- Accuracy on 17 labeled questions: ensemble 88% by majority; **11/11 correct
  whenever all models agreed**. grok-4.6 and gemini-3.1-pro lead at 94%.
- Removed for poor accuracy: mistral-large (53%), kimi-k2.6 (41%),
  glm-5v-turbo / nova-premier / ernie (0%, never returned valid JSON).

## Owner decisions to honour

- Quality over cost. Do not trim the roster to save money.
- Manual allowlist only. No access codes, no payment integration.
- No spend cap value was chosen ("no cap"), but plan 02-04 still BUILDS the
  cap mechanism. Build it; leave the env value unset/high.
- The bot must never claim correctness. Unanimity is reported as agreement,
  never as a correct answer. This is the project's core value.

## Open items needing the owner (do not attempt)

- VPS purchase and deployment. Recommended RackNerd (~$10-15/year) or Vultr
  ($2.50/mo). Hetzner was rejected by the owner.
- Legal review: "SAT" is a College Board trademark and their practice
  questions are copyrighted; this is being sold.
