# Pitfalls Research

**Domain:** Multi-model vision-consensus Telegram bot (SAT Reading & Writing, 6 models via OpenRouter, single VPS, 10-40 user study group)
**Researched:** 2026-09-10
**Confidence:** MEDIUM-HIGH (aiogram/Telegram/SQLite/OpenRouter mechanics verified against docs and issue trackers; consensus-calibration claims sourced to recent literature; a few domain-specific extrapolations flagged LOW where noted)

## Critical Pitfalls

### Pitfall 1: Consensus is treated as a calibrated confidence signal, but agreement and correctness are not the same thing

**What goes wrong:**
The bot's entire value proposition is "when models agree, trust it; when they split, don't." But agreement across models is not evidence of correctness in the way majority voting assumes — it's evidence that the models converged, which can happen for reasons that have nothing to do with the passage being read correctly. Six models can hit 6/6 "strong agreement" on a wrong answer, and the bot will report it with the highest confidence tier it has.

**Why it happens:**
Majority-vote / self-consistency confidence assumes independent errors (Condorcet Jury Theorem territory). LLMs are not independent voters. Recent work auditing cross-model agreement as a confidence signal found that "agents may share training histories, so their agreement may reflect correlated errors rather than independent support," and that high ensemble agreement "often indicates unanimous convergence on the same verdict, even when that is the wrong verdict." Self-consistency was designed to *raise accuracy via voting*, not to produce a calibrated confidence number — reusing the vote split as a trust signal is exactly the practice recent papers are auditing and finding wanting (arxiv.org/html/2607.08065v1, "When LLMs Agree, Are They Right?").

For this domain specifically, three concrete correlation sources apply:
1. **Shared pretraining corpora.** SAT test-prep content (strategy blogs, "how to eliminate wrong answers" guides, published practice books) is heavily represented in the web-scrape-derived data every major lab trains on. Models may be agreeing because they've all absorbed the same test-taking heuristics ("avoid extreme language," "the answer restates the passage's main claim"), not because they independently read the passage correctly. This is a genuinely different failure mode from random disagreement — it produces *confident, consistent, wrong* answers, which is precisely the shape of error the ensemble was built to catch, and precisely the shape it's weakest against.
2. **Distillation / synthetic-data cross-pollination.** Labs increasingly train on outputs (directly or indirectly) from other labs' frontier models. "Four distinct labs" does not guarantee four independent reasoning processes if two of the labs' training pipelines both leaned on GPT-class synthetic data at some stage. (MEDIUM confidence — well-documented as an industry pattern, not verifiable per-model without lab disclosure.)
3. **Correlated OCR errors** — see Pitfall 2, which compounds this one: if all six models misread the same ambiguous word the same way, agreement is guaranteed and meaningless.

**How to avoid:**
- Never let the copy imply agreement *means* correctness. PROJECT.md already commits to this ("never claims to know the correct answer") — hold the line at the UI-copy level too: "strong agreement" should be phrased as "all models converged," not "high confidence this is correct."
- Track disagreement diversity, not just count: log which labs agreed vs. split, not just the tally. A 5/1 where the lone dissenter is the only non-Western-lab model is a different signal than a 5/1 where the split cuts across labs. This is groundwork for the deferred eval harness — capture it now even if not surfaced to users yet.
- Since the eval harness is deferred to v2, the `ground_truth` correction flow is the *only* check on this pitfall in v1. Make the "Wrong answer" button maximally low-friction — every correction is a data point on whether 6/6 agreement is actually reliable for this question type. Consider quietly logging per-question-type agreement-vs-correction rates from day one so v2's eval harness has something to analyze.
- Do not add a 7th "tie-breaker" model or a "trust the frontier models more" weighting scheme to compensate — that reintroduces the single-best-model premise the ensemble exists to avoid, and the literature suggests weighting won't fix correlated errors anyway.

**Warning signs:**
- Corrections cluster on specific question types (e.g., `command_of_evidence_quantitative` or `rhetorical_synthesis`) at 6/6 or 5/1 — that's the signature of shared systematic error, not noise.
- Corrections cluster on questions with short, generic-sounding wrong answers, which are more likely already "known" from test-prep material than reasoned from the specific passage.

**Phase to address:**
Consensus reporting phase (core logic) for the copy/framing discipline; persistence phase for capturing per-type/per-lab agreement data that makes this measurable later.

---

### Pitfall 2: Bad OCR doesn't fail loudly — it produces a plausible, confidently wrong passage transcription, and the ensemble structure makes this worse, not better

**What goes wrong:**
When a vision model can't cleanly read a degraded image (Telegram photo compression, glare, skew, a cropped passage), the dangerous failure is not "I can't read this" — it's silent hallucination of plausible-sounding text that fits the visible context. Documented real-world cases show pipelines running for weeks producing fully fabricated OCR content with no error signal, and hallucination rates rising specifically on blurry or rotated inputs — exactly the inputs a phone photo of a printed SAT page produces.

Because your prompt design forces verbatim transcription before reasoning (a good defense against free-form guessing), a model that mis-transcribes will then reason *coherently and confidently* from its own hallucinated passage — the elimination reasoning will read as sound, well-argued, and totally disconnected from the actual source text. This is worse than a model that just picks a wrong letter, because the reasoning provides false reassurance to a student who can't easily check it against the original.

The ensemble does not automatically catch this. If the image degradation is uniform (glare on the same word for every model, the same passage cropped for every model), multiple models are likely to hallucinate *similarly* — filling the same gap with the same statistically probable phrase — which produces agreement, not disagreement. This is the sharpest version of Pitfall 1: correlated OCR failure directly produces false-confidence consensus.

**Why it happens:**
Vision-language models are trained to be helpful and produce an answer; refusing or flagging uncertainty on partial legibility is not the default behavior, it has to be explicitly prompted and even then is unreliable across providers/models.

**How to avoid:**
- **Cross-model transcription comparison is the right instinct but is not sufficient alone** — evaluate it as one signal, not the detector. Since all six models see the *identical* image, correlated hallucination on the same degraded region is plausible; independent verification requires the transcriptions to actually diverge on the ambiguous span, which they may not.
- Concretely: after collecting all six responses, diff the transcribed passage text (not just the answer letter) pairwise. If ≥2 lab-distinct models produce transcriptions that disagree beyond minor whitespace/OCR noise (use a normalized edit-distance or token-overlap threshold, not exact match), treat the round as **low-confidence regardless of answer agreement** and say so — this is a stronger signal than answer-letter agreement alone, and directly catches the "all six hallucinated differently" case. It will NOT catch the "all six hallucinated the same way" case; be honest about that gap in the UX copy rather than implying transcription-checking is a complete defense.
- Push the OCR quality problem upstream, not just downstream: the "prefer document upload" instruction (already in PROJECT.md) is the single highest-leverage mitigation, since document uploads skip Telegram's photo compression (resize to 2560px longest side + ~85% JPEG quality) entirely.
- Add a cheap pre-flight legibility check before spending money on six model calls: if the image is small, low-contrast, or extremely low-resolution, reject or warn before inference rather than after. (This can be simple heuristics — pixel dimensions, blur variance via Laplacian — not a model call.)

**Warning signs:**
- 6/6 or 5/1 "strong agreement" rounds where the per-model transcriptions of the passage, when diffed, show they are not actually verbatim-identical (small numeric or word substitutions) — this is the early warning that OCR is diverging even when answers converge.
- Corrections that come with a comment like "the passage says X, not Y" pointing at a transcription error rather than a reasoning error.

**Phase to address:**
Inference phase (prompt design + response parsing) for the JSON contract to include the transcription as a first-class field usable for comparison; consensus reporting phase for surfacing transcription-divergence as a distinct confidence dimension from answer-tally agreement.

---

### Pitfall 3: Perceptual hashing is structurally the wrong tool for near-duplicate SAT question images, and a cache collision serves a confidently wrong answer with zero visible error

**What goes wrong:**
SAT R&W questions from the same test form (or same publisher's practice sets) share almost everything visually: same font, same passage box layout, same four-choice layout, same margins, same screenshot chrome if students crop similarly. Two genuinely *different* questions can be visually closer to each other than a JPEG-compressed vs. original version of the *same* question is to itself. A perceptual-hash collision here doesn't produce a visibly broken result — it produces a normal-looking, fully confident cached answer for the wrong question. There is no error state; the user just gets told the wrong thing with total conviction.

**Why it happens:**
Standard perceptual hash algorithms (aHash, pHash/DCT-based, dHash) are deliberately built to be invariant to exactly the kind of variation that separates near-duplicate document photos — minor crop, brightness, JPEG artifacting — by discarding high-frequency detail and keeping only a coarse low-frequency structure. For photographs of natural scenes this works well because the *identifying* information is in that coarse structure. For **text-dense document images, the differentiating information between two different questions is almost entirely in the fine detail** (the actual words) — precisely the high-frequency content DCT-based pHash throws away to achieve its invariance. This is a domain mismatch, not a tuning problem: a bigger hash or looser/tighter threshold doesn't fix the fact that the algorithm is designed to ignore the part of the image that actually distinguishes two SAT questions with the same template.

General guidance on Hamming-distance thresholds (0 = identical, 1-5 bits = very close, 6-15 = "shared similarities" which is exactly the same-template-different-question zone, 16+ = probably different) confirms the middle band is genuinely ambiguous for any image type — and for structurally-similar text documents, real different-content pairs will land in that same middle band as genuine re-sends of the same photo (recompressed, re-cropped, rotated).

**How to avoid:**
- Do not rely on perceptual hash alone as the cache key. Use it only as a *candidate filter* (find near-hash matches), then confirm the match with something that actually reads the content: compare a fast, cheap OCR/text-extraction of the candidate against the incoming image (a lightweight non-frontier model call, or a text-similarity check on the already-cached transcription if the cache stores it) before serving a cached answer. Treat a phash "hit" as "worth checking," not "answer confirmed."
- Set the phash threshold tight (near 0, not the commonly-cited "6-15 bits = similar" band) precisely because this domain's false-positive risk is unusually high, and accept more cache misses (re-running inference) as the safer failure mode — a cache miss costs money, a cache collision serves misinformation with full confidence.
- Log every cache hit's hash distance. If corrections start coming in on cache-hit answers, that's a strong signal the threshold is too loose or the verification step is missing.

**Warning signs:**
- Cache hit rate that seems too high relative to the number of genuinely distinct questions the group is likely working through (e.g., a study group progressing through a practice test linearly shouldn't produce many legitimate re-sends).
- Corrections on responses that were served from cache (track this explicitly — a `served_from_cache` flag per attempt is cheap and necessary for debugging this exact failure mode).

**Phase to address:**
Caching & persistence phase. This needs the verification step designed in from the start — retrofitting a confirmation check after cache-collision bugs have already served wrong answers is much more expensive than building it in initially.

---

### Pitfall 4: The 30-second budget is set by the slowest of six parallel calls, and two of them are frontier models with no fallback if either stalls

**What goes wrong:**
Firing all six models in one round with no cascade (a deliberate design choice per PROJECT.md) means total wall time is `max()`, not `avg()`, across six concurrent calls. Frontier models (Opus-class, GPT-Astra-class) generating a full verbatim transcription plus four elimination reasons at up to 2000 tokens routinely take 15-30+ seconds on their own even without contention. Under real usage — a study group of 10-40 people, several sending questions in the same few minutes during a session — provider-side queuing on the frontier models' endpoints adds latency variance on top of generation time. One slow model call blows the budget for every user waiting on that round, and because there is no cascade or partial-result path, the entire response is either "wait longer than 30s" or the round has to time out and degrade.

**Why it happens:**
The cascade/two-tier design was explicitly dropped ("costs the most per question," "Pending" outcome in Key Decisions) in favor of always firing all six, which removes the natural mechanism (return early on cheap-model agreement) that would have bounded latency in the common case. A single-round, all-models design has no slack — every question pays the full six-way latency tax, including easy questions that five of six models would answer in 2 seconds.

**How to avoid:**
- Set a **per-model timeout well under the 30s global budget** (e.g., 20-22s) so a single stalled model degrades to "abstained" rather than dragging the whole round past budget. This is different from the JSON-repair-retry abstention path — this is a wall-clock abstention. PROJECT.md already treats "two or more abstentions degrades confidence," so a timeout-based abstention fits the existing contract without new design.
- Do not wait for `asyncio.gather` with no per-task timeout — use `asyncio.wait_for` per model call (or `asyncio.gather` with `return_exceptions=True` plus a global `asyncio.wait_for` wrapper) so slow models don't block fast ones from being counted.
- Show the "typing" indicator (already planned) but also consider a progressive update if the round is taking long (e.g., edit the message once at ~15s with "still waiting on N models" ) so users don't assume the bot is dead — Telegram's UX has no other signal during a 20-30s wait.
- Load-test with concurrent questions before launch, not after: simulate 3-5 simultaneous questions (plausible for a study group session) and confirm total latency doesn't compound due to shared OpenRouter connection pool limits or event-loop contention in a single-process aiogram deployment.

**Warning signs:**
- P95 latency creeping toward or past 30s in logs even with only 1-2 concurrent users — this means the steady-state (uncontended) latency budget is already tight, and any real contention will blow it.
- Per-attempt logging (already planned) showing one or two specific models consistently the slowest — that's actionable (timeout tuning, or reconsidering that model's place in the roster) well before it's a user-facing complaint.

**Phase to address:**
Inference phase — per-model timeout and `asyncio.wait_for` pattern must be in the initial implementation, not bolted on after a latency incident. Flagged in PROJECT.md as wanting research before Phase 1 planning; this confirms that instinct.

---

### Pitfall 5: Spend caps checked-then-enforced have a race window that concurrent group usage will actually hit

**What goes wrong:**
A global daily spend cap implemented as "read current spend, compare to cap, proceed or degrade" is a classic TOCTOU (time-of-check-to-time-of-use) race. With a study group of 10-40 people, it is entirely plausible for 3-5 people to send questions within the same second or two (e.g., right after a teacher says "everyone check question 12"). If each request reads the day's spend-so-far *before* any of them writes their own cost back, all of them can pass the check even though their combined cost blows the cap — because "10 concurrent requests reading a budget with headroom for 1 will all proceed" is exactly the documented failure shape for this pattern.

Beyond the race, spend caps get bypassed in less exotic ways worth designing against explicitly:
- **Retries not counted toward spend.** A JSON-repair retry (already planned per PROJECT.md) is a second API call with its own token cost. If the cap-check only counts "one call per model per question" in its accounting logic, repair retries silently exceed the intended per-question cost.
- **Cached-token / prompt-caching accounting mismatches.** If cost is computed from the provider's returned usage object, make sure cached-input pricing (cheaper) vs. full-price tokens are both correctly summed — a cost calculation that assumes a flat per-token rate will overcount or undercount depending on whether the identical image+prompt across six models triggers any provider-side caching.
- **Per-user daily caps resetting on server-local time vs. user expectation.** If "daily" resets at UTC midnight on a VPS, but the study group is in a different timezone, the cap can reset mid-session in a way that's inconsistent with "resets once a day" from the user's perspective (either resetting twice in what feels like one evening across a UTC boundary, or not resetting when the group expects a fresh day).

**How to avoid:**
- Enforce the spend cap with an **atomic conditional update**, not a read-then-write: e.g., `UPDATE spend SET total = total + ? WHERE total + ? <= ?` (or equivalent optimistic-concurrency pattern) as a single SQLite statement, checked for whether the row was actually updated, rather than a separate SELECT followed by an INSERT. This closes the race without needing external locking infrastructure.
- Reserve/decrement the estimated cost *before* firing the round (based on expected max token cost for the model set), then reconcile with actual cost after the response — this bounds the worst case to one round's overshoot rather than unbounded concurrent overshoot, and naturally covers the repair-retry case if the reservation includes retry budget.
- Pick a single explicit timezone for "daily" (UTC is simplest and defensible for a global spend cap) and document it in the `/cost` command output so `OWNER_ID` isn't surprised by reset timing.
- Test the degraded-mode fallback (cheaper model set above cap) under concurrent load specifically — confirm that once the cap trips, every in-flight and subsequent request actually sees the degraded set, not just requests that happen to re-check after the write lands.

**Warning signs:**
- `/cost` command showing a day's total that exceeds the configured cap — if this is ever possible, the enforcement is check-then-act, not atomic.
- Spend that jumps in bursts correlated with study-session timing rather than smoothly — a sign concurrent requests are landing in the race window together.

**Phase to address:**
Access & cost control phase. This is explicitly called out in PROJECT.md as "load-bearing, not nice-to-have" — the atomic-update requirement should be a stated implementation constraint in that phase's plan, not left to whoever writes the spend-check function.

---

### Pitfall 6: The JSON repair retry silently lets a model change its answer, corrupting the vote it's supposed to be casting

**What goes wrong:**
When a model emits malformed JSON (markdown fences, prose preamble, trailing comma, truncation at max_tokens) and the planned mitigation is "one repair retry, then abstain," the repair retry is not a formatting fix — it's a **new inference call**. Asking the model to "fix this JSON" or re-sending the prompt gives it a second chance to reconsider its reasoning, not just its syntax. A model that would have voted B on the first (malformed) attempt can vote C on the repair attempt, especially if the repair prompt includes any of its own prior reasoning as context (which can shift its answer either direction). The recorded vote then reflects whichever answer survived the repair round, not a clean signal of what the model "actually thinks" — and this happens invisibly, since only the final parsed JSON is logged unless the raw first attempt is also captured.

This also means: not all six models get equal treatment. A model that happens to need a repair retry gets an extra "attempt" at reasoning that the five clean-JSON models didn't get, which is a subtle form of the free-form-answering problem PROJECT.md's elimination-reasoning design is specifically trying to prevent.

**Why it happens:**
Reliability at emitting clean, schema-conforming JSON varies significantly across models even when going through OpenRouter's structured-output support. OpenRouter normalizes the request format, but enforcement varies by underlying provider — some guarantee schema conformance, others treat the schema as a strong hint and can still emit prose wrappers or fenced code blocks; exact compliance is not guaranteed uniformly across every model on the roster. In general, weaker or non-frontier models (smaller open-weight models more than the frontier labs' flagship models) are more prone to wrapping JSON in markdown fences or adding conversational preambles, so expect repair-retry frequency to skew toward whichever of the six is the "budget" pick rather than being evenly distributed. (MEDIUM confidence: general pattern well-documented; exact per-model failure rate for this specific six-model roster is unverified until the actual model IDs are locked and tested — flag for phase-specific testing once the roster from the stack-research agent is finalized.)

**How to avoid:**
- Use OpenRouter's `response_format: json_schema` (structured outputs) as the first line of defense for every model that supports it, not prompt-only JSON instructions — this reduces but does not eliminate the fence/preamble problem, since support varies by provider.
- Log the **raw first-attempt response** even when it fails to parse, before attempting repair. Without this, you cannot ever audit whether repair retries are changing answers, because the "before" state is gone.
- Make the repair prompt strictly a formatting fix: send back only "extract and return valid JSON matching this schema from the following text: {raw_output}" with *no* additional context that invites re-reasoning (don't re-send the image, don't re-send the original prompt) — this makes the repair call a pure syntax-extraction task, not a second reasoning opportunity, and should structurally prevent the answer from changing during repair.
- If the repair-extracted answer differs from a naive regex/substring pull of the answer letter out of the raw (malformed) first response, treat that as suspicious — log it distinctly, and consider abstaining rather than trusting the repaired version, since it suggests the repair step altered substance, not just syntax.

**Warning signs:**
- Repair-retry rate concentrated on one or two specific models — confirms which of the six are weakest at structured output and may warrant reconsidering their place in the roster or applying stricter prompting for those specific models.
- Any case where the repaired JSON's answer letter doesn't match a naive extraction from the raw malformed text — direct evidence the repair call re-reasoned rather than reformatted.

**Phase to address:**
Inference phase (response parsing / repair logic). The "log raw response before repair" requirement should be part of the initial pydantic-validation-plus-repair implementation, not added after the first audit reveals it's missing.

---

### Pitfall 7: A single unescaped character in model-generated reasoning text breaks MarkdownV2 parsing and the entire answer fails to deliver

**What goes wrong:**
The consensus letter is planned to render inside a MarkdownV2 spoiler, with elimination reasoning shown first. That reasoning text is LLM-generated and therefore unpredictable — it can and will contain characters from MarkdownV2's reserved set (`_ * [ ] ( ) ~ \` > # + - = | { } . !`) as ordinary punctuation (a hyphen in "well-supported," a period ending a sentence, parentheses around a citation). MarkdownV2 requires every one of these to be escaped with a preceding backslash *outside* of intentional formatting spans, and Telegram's Bot API rejects the entire `sendMessage` call with a 400 `can't parse entities` error if even one is missed — not a partial render, a total failure. For this bot, a formatting bug in the reply is not cosmetic, it's "the user never gets their answer," which the focus area for this research correctly flags as a total failure to deliver.

Known aiogram-specific traps compound this: `escape_md()`-style helpers have had gaps (e.g., a documented case of not escaping `=`), the `pre()`/code-block formatting has a documented bug where content without leading/trailing newlines silently drops the first line, and unclosed single `_` or `*` characters anywhere in interpolated text raise `CantParseEntities`. Since six independent models are all contributing free-text reasoning into a single formatted message, there are six independent sources of "the message that character came from is unpredictable."

**Why it happens:**
MarkdownV2 escaping is easy to get right for static, developer-written strings and easy to get subtly wrong for interpolated LLM output, because the reserved-character set is unusually broad (it includes `.` and `-` and `!`, characters that appear constitutively in normal English prose) and escaping must be applied to the *content* being interpolated, not to hand-authored template text, which is a different code path than most examples demonstrate.

**How to avoid:**
- Escape every piece of LLM-generated text (transcriptions, reasoning, elimination text) through a single, tested escape function immediately before interpolation — never construct the final message string first and try to escape it as a whole, since that will also escape intentional formatting markers (spoiler syntax, bold markers) the bot itself adds.
- Prefer aiogram 3's `aiogram.utils.markdown` helper functions (`hbold`, `hitalic`, `hspoiler`, etc., or the `Text`/formatting-object API) which unparse/build the entity structure programmatically rather than hand-escaping raw strings — this sidesteps the "did I escape this substring correctly" class of bug entirely, per aiogram's own FAQ recommendation.
- Write a unit test that runs LLM-shaped adversarial reasoning strings (containing `.`, `-`, `()`, `_`, `*`, unmatched quote characters, and a bare backslash) through the actual send path against a fake/sandboxed check, or at minimum through the escaping function, before this ships. This is cheap insurance against a class of bug that otherwise only surfaces in production when a specific model happens to phrase something a specific way.
- Have a fallback: if `sendMessage` with `parse_mode=MarkdownV2` raises a parse-entity error, catch it and resend as plain text (no formatting) rather than letting the exception propagate and the user get nothing. A degraded-but-delivered answer beats a silently dropped one.

**Warning signs:**
- Any unhandled `TelegramBadRequest` / `can't parse entities` exception in logs — this should never reach the user as "no reply," it should be caught and imply a bug in the escaping path.
- Spot-check the escape function against reasoning text containing markdown-special characters from each of the six models specifically, since each model has a different "voice" and may favor different punctuation patterns.

**Phase to address:**
Interaction phase (message formatting/rendering). Needs a plain-text fallback path built in from the start, and the adversarial-string test written before the first real model output is rendered to a live chat.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| Building manual `escape_md()` string replacement instead of using aiogram's formatting helpers/objects | Faster to write initially | Recurring `CantParseEntities` failures as new punctuation patterns appear in LLM output | Never for this project — reasoning text is high-variance LLM output, not static strings |
| Read-then-write spend cap check instead of atomic conditional update | Simpler code, works fine in manual testing (single user) | Cap silently bypassed under any real concurrent group usage | Never — this is explicitly load-bearing per PROJECT.md |
| Skipping the raw-response log before JSON repair | Slightly less logging code | Impossible to audit whether repair retries change model votes after the fact | Never — cheap to add now, expensive to reconstruct later |
| Using default 8x8 DCT pHash with a loose threshold for caching | Simple, well-known library call (`imagehash`) | Silent wrong-answer cache collisions on visually similar different questions | Only acceptable if paired with a secondary content-verification step before serving a cache hit |
| Long-polling instead of webhook on the single VPS | No need for public HTTPS endpoint, TLS cert management, or reverse proxy config | Slightly higher latency floor per update, one extra long-lived connection to manage | Acceptable and recommended at this scale (10-40 users) — webhook complexity buys nothing here |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|-----------------|-------------------|
| OpenRouter | Treating every model route as interchangeable for `response_format: json_schema` support | Verify structured-output support per model at boot (alongside the already-planned image-input capability check); don't assume schema conformance is guaranteed just because the request didn't error |
| OpenRouter | Assuming rate limits are per-API-key, so parallel per-user keys would help | Rate limits are account-wide on OpenRouter, and paid models have no hard OpenRouter-side cap but are still subject to upstream provider limits — six parallel calls per question, times several concurrent users, can trigger upstream 429s that have nothing to do with your own spend cap |
| Telegram Bot API | Relying on the compressed `PhotoSize` array as the only input path | Already planned to prefer document uploads — also handle the case where a user sends a `photo` anyway; the OCR-hallucination risk (Pitfall 2) is highest on that path, so route photo-message inputs through the same legibility pre-check as documents |
| Telegram Bot API | Not answering callback queries before doing async work in a button handler | Call `answer()` on the callback query immediately (even with no text) before running any inference-adjacent logic, so the button doesn't appear to "hang" in the client |
| aiosqlite | Assuming default journal mode handles concurrent writers gracefully | Enable WAL mode and set `PRAGMA busy_timeout` explicitly at connection setup — default rollback-journal mode plus concurrent async writers from multiple aiogram handler coroutines will surface `database is locked` under real (not just simulated) concurrent load |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| No per-model timeout inside the six-way `asyncio.gather` | P95 latency creeping toward 30s even with 1 concurrent user | `asyncio.wait_for` per model call, well under the global budget, with timeout treated as abstention | Breaks first under any concurrency — 2-3 simultaneous questions during a study session is enough |
| Single SQLite file with no WAL mode under bursty write load | Occasional `database is locked` errors during multi-user sessions, worse right when the group is most active | WAL mode + busy_timeout + minimizing transaction scope per write | Becomes visible once several students message within the same few seconds — plausible at 10-40 users during a live session |
| Uncapped six-way fan-out with no per-user or per-round concurrency ceiling on the VPS | Event loop contention or connection-pool exhaustion if several users trigger rounds simultaneously | Bound the httpx client's connection pool explicitly and consider a small in-process semaphore on concurrent in-flight rounds so the VPS doesn't try to run 30+ simultaneous outbound calls | Relevant well before 40 users — a handful of simultaneous questions is already 30+ concurrent outbound HTTP calls (6 models x 5 users) |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging full request/response bodies for debugging | Base64 image data and/or API keys end up in log files, which are often less access-controlled than the database | Log structured metadata (model, tokens, latency, cost, parsed answer) by default; gate full raw-body logging behind an explicit debug flag that is off in normal operation, and never log the `Authorization` header |
| Echoing OpenRouter error messages verbatim back to Telegram users | Provider error text can leak account/billing details or internal routing info | Catch provider errors, log the raw detail server-side, show users a generic "a model failed to respond" message |
| Storing the OpenRouter key and bot token in the same `.env` with no distinct handling | Not distinct-domain risk here, but a single leaked `.env` compromises both spend and bot control simultaneously | Standard secret hygiene applies — `.env` never committed (already planned) — worth explicitly confirming `.env` is in `.gitignore` from the first commit, not added after a scare |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Silent 20-30 second wait with only a static "typing" indicator | Users assume the bot is broken and resend the same photo, doubling cost and creating duplicate near-simultaneous cache/consensus requests for the same question | Consider a single progress edit partway through (e.g., "4/6 models responded") so users don't bail and resend |
| "Strong agreement" framed in a way that reads as "this is correct" | Directly undermines the stated Core Value ("never claims to know the correct answer") if copy drifts even slightly toward certainty language | Keep agreement language strictly about model convergence, not correctness, in every UI string — this is a copy-review item, not just a logic item |
| Rejecting a multi-question screenshot with a generic error | User doesn't know *why* it was rejected or what to do instead | Rejection message should name the specific reason (multiple questions detected / not SAT verbal) so the user can immediately retake or recrop, rather than guessing |

## "Looks Done But Isn't" Checklist

- [ ] **JSON repair retry:** Often missing the raw-pre-repair-response log — verify the raw malformed output is persisted alongside the repaired parse, not discarded
- [ ] **Perceptual hash cache:** Often missing a content-verification step on hash "hits" — verify a phash match is confirmed against actual content before being served, not trusted on hash proximity alone
- [ ] **Spend cap enforcement:** Often implemented as read-then-write — verify the enforcement path is a single atomic conditional update under concurrent-request testing, not just single-request testing
- [ ] **MarkdownV2 rendering:** Often tested only with hand-typed sample strings — verify against actual model-generated reasoning text containing periods, hyphens, and parentheses in normal prose positions
- [ ] **Per-model timeout:** Often implemented as a global timeout on the whole `gather()` call — verify each model call individually times out and abstains rather than the entire round failing if one model hangs
- [ ] **Boot-time model validation:** Often checks model existence but not structured-output/schema support — verify both capabilities are checked, not just image-input support, given PROJECT.md's other boot-time checks

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|----------------|------------------|
| Cache collision serving a wrong answer | LOW (technical) / MEDIUM (trust) | Invalidate the cache entry on any correction tied to a cache-served attempt; tighten the phash threshold or add the verification step; re-run the affected cache-hit questions live |
| Spend cap race condition discovered after overspend | LOW (technical) / MEDIUM (budget) | Switch the check to an atomic conditional update; the overspend itself is usually small in absolute terms at this scale (10-40 users) but should be treated as a signal to audit the whole cost-accounting path, not just patched locally |
| MarkdownV2 delivery failures discovered in production | LOW | Add the plain-text fallback on parse-entity exceptions immediately; backfill by resending any answers that failed to deliver, since the inference already ran and the cost was already spent |
| Consensus-agreement-as-confidence found to be systematically wrong on a question type (via corrections) | MEDIUM | This is expected and by design (it's why the correction flow exists) — document the finding, consider flagging that question type as lower-confidence in the UI copy even at 6/6 agreement, feed it into the v2 eval harness design |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|----------------|
| Consensus treated as calibrated confidence | Consensus reporting phase | UI copy review confirms no string implies correctness; per-type/per-lab agreement data is being logged |
| Silent OCR hallucination | Inference phase (prompt/schema) + Consensus reporting phase | Transcription field present in schema; transcription-divergence check implemented and surfaced as a distinct signal from answer-tally agreement |
| Cache collision from perceptual hash mismatch with text-dense images | Caching & persistence phase | Cache hits pass through a content-verification step before being served; `served_from_cache` logged per attempt |
| Latency blowout from six-way fan-out with two frontier models | Inference phase | Per-model `asyncio.wait_for` timeout in place; load test with 3-5 concurrent questions shows P95 within budget |
| Spend cap TOCTOU race | Access & cost control phase | Atomic conditional update verified under concurrent-request test; retries and cached-token pricing both included in cost accounting |
| JSON repair retry silently changing the vote | Inference phase (response parsing) | Raw pre-repair response logged; repair prompt contains no re-reasoning context; repaired answer cross-checked against naive extraction from raw text |
| MarkdownV2 total delivery failure | Interaction phase | Adversarial-string test passes; plain-text fallback on parse-entity exception confirmed working |
| SQLite concurrent write contention | Caching & persistence phase | WAL mode + busy_timeout set at connection init; verified under simulated concurrent-write test |

## Sources

- [When LLMs Agree, Are They Right? Auditing Self-Consistency and Cross-Model Agreement as Confidence Signals](https://arxiv.org/html/2607.08065v1)
- [Self-ensemble: Mitigating Confidence Mis-calibration for Large Language Models](https://arxiv.org/pdf/2506.01951)
- [Learning to Trust the Crowd: A Multi-Model Consensus Reasoning Engine for Large Language Models](https://arxiv.org/pdf/2601.07245)
- [NLP Evaluation in trouble: On the Need to Measure LLM Data Contamination for each Benchmark](https://arxiv.org/pdf/2310.18018)
- [Evaluation data contamination in LLMs: how do we measure it and (when) does it matter?](https://arxiv.org/pdf/2411.03923)
- [When Your LLM Hallucinated Your OCR](https://woitzik.dev/blog/llm-hallucinated-ocr-paperless/)
- [LLM OCR: Why the Errors Got Harder to Spot](https://www.llamaindex.ai/blog/llm-ocr)
- [Reading Between the Lines: Abstaining from VLM-Generated OCR Errors via Latent Representation Probes](https://arxiv.org/pdf/2511.19806)
- [OpenRouter — Structured Outputs docs](https://openrouter.ai/docs/guides/features/structured-outputs)
- [OpenRouter Structured Output Broke Before Translation Quality Did — 3 Layers of Defense](https://dev.to/lovanaut55/openrouter-structured-output-broke-before-translation-quality-did-3-layers-of-defense-for-1cdb)
- [OpenRouter API Credit & Rate Limits docs](https://openrouter.ai/docs/api_reference/limits)
- [OpenRouter Rate Limits: Why They Happen and How Multi Provider Fallback Fixes Them](https://www.requesty.ai/blog/openrouter-rate-limits-why-they-happen-and-how-multi-provider-fallback-fixes-them)
- [aiogram issue #360 — markdown.escape_md() doesn't escape '=' sign](https://github.com/aiogram/aiogram/issues/360)
- [aiogram issue #596 — text decoration pre() bug](https://github.com/aiogram/aiogram/issues/596)
- [aiogram issue #197 — CantParseEntities exception for unclosed markdown entities](https://github.com/aiogram/aiogram/issues/197)
- [Aiogram 3 FAQ — Common Questions](https://akchonya.github.io/aiogram-3-faq/common_questions/)
- [Perceptual hash thresholds — Snibgo's ImageMagick pages](https://im.snibgo.com/phashthresh.htm)
- [The Problem with Perceptual Hashes — Rent-a-founder](https://rentafounder.com/the-problem-with-perceptual-hashes/)
- [SoK: Content Moderation for End-to-End Encryption (perceptual hash false-positive rates)](https://arxiv.org/pdf/2303.03979)
- [SQLite concurrent writes and "database is locked" errors](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/)
- [aiosqlite issue #251 — Database is Locked despite timeout](https://github.com/omnilib/aiosqlite/issues/251)
- [The check-then-act race condition hiding in most "AI agent spend gate" designs](https://www.indiehackers.com/post/the-check-then-act-race-condition-hiding-in-most-ai-agent-spend-gate-designs-1823a00a94)
- [one-api issue #2440 — Quota consumption TOCTOU race](https://github.com/songquanpeng/one-api/issues/2440)
- [Telegram compression behavior — tdesktop issue #25676](https://github.com/telegramdesktop/tdesktop/issues/25676)
- [Telegram's Client-Side Image Compression: How It Works and Why It Matters](https://rifqimfahmi.dev/blog/telegram-like-image-optimization-on-android)

---
*Pitfalls research for: Multi-model vision-consensus Telegram bot (SAT verbal, OpenRouter, single VPS)*
*Researched: 2026-09-10*
