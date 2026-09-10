# Feature Research

**Domain:** Telegram study bot / multi-model LLM consensus tool for SAT Reading & Writing
**Researched:** 2026-09-10
**Confidence:** MEDIUM-HIGH (prompt-engineering and ensemble-agreement findings are arxiv-sourced and consistent across papers; Telegram UX and feedback-loop findings are practitioner-sourced, directionally reliable but not academically rigorous)

## Feature Landscape

### Table Stakes (Users Expect These)

Features a 10-40 person allowlisted study group will assume exist. Missing these makes the bot feel broken, not just minimal. None of these violate the Out of Scope list — they are gaps in the current Active requirements, not new capabilities.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `/start` onboarding message | Every Telegram bot needs a first-contact message explaining what it does, how to send a question, and what "document vs photo" means. Currently absent from Active scope — only `/adduser` and `/cost` are specified. | S | Should state the photo-vs-document guidance up front rather than only as a rejection-time warning. |
| `/help` command | Practitioner UX guidance is unanimous: users expect `/help` to exist and to be a shortcut back to onboarding, not a support ticket. Not currently in Active scope. | S | Reuse `/start` copy. |
| Friendly quota-exceeded message | The per-user daily cap (40) is in scope, but what the bot *says* when a user hits it is not specified. Punitive-feeling quota messages are a named failure mode in bot UX research — state the reset time, not just "no." | S | Depends on: per-user daily cap (already planned). |
| Pre-flight image quality gate (blur + resolution check) | The user has already named bad OCR as the dominant failure mode. Research on multimodal-LLM OCR shows accuracy holds up to roughly 300 ppi equivalent and degrades sharply below ~150 ppi (arxiv 2503.23667, MEDIUM confidence — single paper, but consistent with the general OCR literature on resolution thresholds). A cheap Laplacian-variance blur check plus a resolution floor catches unusable images *before* spending six model calls on them. | S | Must run before Inference fires. Complements — does not replace — the existing "prefer document uploads" messaging: the message is advice, the gate is enforcement. |
| Structured "how to photograph a question" guidance | Shown once at `/start` and again on rejection. Concrete guidance (flat angle, full passage and all four choices in frame, avoid shadows/glare) reduces repeat bad submissions more than generic "use good lighting" text. | S | Pairs with the quality gate above — the gate tells the user *why* it was rejected, the guidance tells them what to do differently. |
| Robust MarkdownV2 escaping | The consensus report uses a MarkdownV2 spoiler for the final letter. MarkdownV2 requires escaping ~18 reserved characters, and unescaped model-generated text (which will contain parentheses, hyphens, periods) is one of the most common Telegram bot bugs. Not called out anywhere in Active scope. | S | Blocks: consensus reporting, "Full breakdown" button. Needs a shared escaping utility, not ad hoc escaping per call site. |
| Message-length pagination for "Full breakdown" | Six models' full transcription + four elimination verdicts each will regularly exceed Telegram's 4096-character message cap. Not addressed in Active scope. | S-M | Depends on: "Full breakdown" button (already planned). Split by model (one message or edit-and-page per model) rather than truncating mid-reasoning. |
| Structured correction input (inline A/B/C/D buttons, not free text) | The spec says the "Wrong answer" button "asks for the real letter" but doesn't specify input mode. UX research on error correction favors the lowest-friction input available; a free-text reply invites typos ("b", "B)", "answer is B") that then corrupts `ground_truth`, the exact dataset this feature exists to build cleanly. | S | Depends on: "Wrong answer" button (already planned). This is a refinement of a planned feature, not a new one. |
| Telegram API 429 retry/backoff | Bot API rate limits apply to every method call (sendMessage, editMessageText, answerCallbackQuery, sendPhoto), not just outbound messages. A 6-model fan-out followed by a multi-message breakdown reply is exactly the traffic pattern that trips this. Not addressed anywhere in Active scope. | S | Standard exponential backoff on 429; low effort, high reliability payoff. |

### Differentiators (Competitive Advantage)

These map directly to the Core Value ("honest confidence signaling") and are where this bot earns its premise over a single-model SAT tutor bot or a generic quiz bot.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Consensus + elimination reasoning report (already planned) | This is the core differentiator and matches a validated pattern: a 2026 competitor product (ConvergePanel) exists specifically to show independent multi-model answers "side by side with a consensus score and an explicit disagreement map," on the premise that models responding without seeing each other's output makes agreement/disagreement "a genuine signal rather than one model echoing another" — the same premise this bot is built on. MEDIUM confidence (one product example, but the reasoning is sound and matches the arxiv ensemble literature). | (already planned) | No change needed — validates the existing design. |
| Verbatim transcription before reasoning | Directly supported by grounding/hallucination research: "according-to" prompting and quote-extraction-before-answering measurably reduce hallucination because the model can no longer "fill gaps from probability alone" — it has to work from text it already committed to (arxiv 2305.13252; Claude's own hallucination-reduction guidance recommends the same pattern for long-document tasks). HIGH confidence. | (already planned) | Validates the existing prompt design — no change needed. |
| Forced per-choice elimination verdicts | Directly supported by "BiasPrompting" (arxiv 2511.20086), which shows that generating reasoning for *all* answer choices before selecting a final answer improves multiple-choice accuracy and reduces position/order bias — models otherwise show a measurable preference for certain answer positions independent of content. HIGH confidence. | (already planned) | Validates the existing prompt design — no change needed. |
| Lab-spread-aware consensus annotation | The strongest and most actionable finding from this research pass: "Nine Judges, Two Effective Votes" (arxiv 2605.29800, Apple ML Research) found that a 9-judge, 7-family LLM panel provided only ~2 independent votes' worth of information, because models share correlated errors within and across labs — roughly three-quarters of nominal panel independence was lost. HIGH confidence, directly relevant. **Recommendation:** when reporting "5/6 agree," also surface how many distinct labs are represented in that majority (the boot-time ≥4-lab constraint already tracks lab identity per model, so this is a reporting change, not a new data source). "5/6 agree, spanning 4 labs" is meaningfully stronger evidence than "5/6 agree, spanning 2 labs" would be, and the current 6/6-5/1-4/2-3/3 tiering treats both cases identically. | S-M | Depends on: boot-time lab-diversity validation (already planned), consensus tally (already planned). Does not add a new data source, only a new field in the existing report — compatible with "never assert correctness." |
| Pre-flight image quality gate (see also Table Stakes) | Also a differentiator: it directly attacks the user's own named top failure mode with a measurable, explainable gate ("image too blurry to read reliably — retake and resend") instead of silently sending unusable images to six paid model calls. | S | Same feature as listed above; listed twice because it is both baseline-necessary and a real point of distinction from a naive "just forward the photo" bot. |
| `/cost` transparency for the owner | Cost transparency in a shared-cost study group context builds trust that the daily spend cap and degraded-mode fallback are real, not just decorative. (already planned) | (already planned) | No change needed. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Per-model self-reported confidence score ("Model X: 85% confident") | Feels like it adds precision and is easy to prompt for. | Verbalized-confidence research is consistent and blunt: LLM self-reported confidence is frequently miscalibrated and overconfident, especially when the model lacks sufficient information, and scores exhibit "confidence saturation" — clustering at 80/90/100% regardless of actual task difficulty (arxiv 2412.14737, 2509.25532). A displayed confidence number would mislead users with false precision on top of the honest agreement-based signal the bot already provides. HIGH confidence. | Keep confidence purely as inter-model agreement (already the design). Do not add a confidence field to the per-model JSON contract. |
| Vote-weighting by model self-reported confidence | Seems like a natural refinement of majority voting. | Same calibration problem as above — weighting by an unreliable signal degrades the vote rather than improving it, and reintroduces exactly the "confident, well-argued, wrong answer" failure mode the ensemble exists to catch. | Unweighted vote tally, annotated with lab spread (see Differentiators). |
| Multi-round debate between models before voting | Multi-agent debate research shows accuracy gains in some settings and is a trendy 2026 ensemble pattern. | Directly conflicts with the existing hard constraint "no model ever sees another model's output" — that constraint exists precisely to prevent contamination, which is what debate introduces. Also multiplies latency past the 30s budget across six models. | Independent single-round voting (already planned/locked). |
| Automatic image deblurring / super-resolution before sending to models | Tempting direct fix for the named OCR failure mode. | Algorithmic image enhancement can alter or fabricate fine detail (especially text-adjacent artifacts), which directly undermines the verbatim-transcription integrity the whole prompt design depends on — a model transcribing a super-resolved image is transcribing a partially synthetic image. Also nontrivial extra latency/compute for a use case with a hard 30s budget. | Reject-and-ask-for-retake via the pre-flight quality gate (see Table Stakes/Differentiators). |
| Gamification: streaks, leaderboards, badges | Extremely common in study-group bots — QuizBot and similar Discord/Telegram study tools lean on this heavily, and it's an obvious retention lever for a 10-40 person cohort. | Requires new cross-user aggregate state and a public-facing social surface neither in the current data model nor the Core Value; adds a moderation and privacy surface (public correctness tracking) that this bot's minimal, honest-signal design doesn't need to carry. | If retention becomes a problem post-launch, a private `/mystats` command (self-only, admin-visible) is a much smaller addition than a public leaderboard. |
| Self-consistency resampling (each model queried 2-3x, majority vote per model, before the 6-model ensemble vote) | Has the single strongest published accuracy effect found in this research pass — self-consistency resampling improves multiple-choice/reasoning accuracy by roughly +3 to +23 percentage points depending on model scale and task (arxiv 2503.04104 and related self-consistency literature). HIGH confidence on the underlying effect. | Multiplies the already-expensive 6-model, 2-frontier-model round by 2-3x on both cost and latency, which breaks both the 30s budget and the global spend cap — the two hardest constraints in the project. | See Scope Tensions below — this is the one technique in this research pass worth flagging as a real tradeoff, not a false lead. |
| Free-text reply for "Wrong answer" correction | Simplest to implement — just read the next message. | Free text invites malformed/ambiguous input ("B?", "it's b i think") that corrupts the one dataset (`ground_truth`) this feature exists to build cleanly for the deferred v2 eval harness. | Inline A/B/C/D buttons (see Table Stakes). |

## Feature Dependencies

```
Pre-flight image quality gate
    └──precedes──> Inference (six-model fan-out)
                       └──feeds──> Consensus tally
                                       └──enhanced-by──> Lab-spread-aware annotation
                                                              └──requires──> Boot-time lab-diversity validation (planned)

"Wrong answer" button (planned)
    └──enhanced-by──> Structured A/B/C/D inline input
                           └──feeds──> ground_truth (persistence, planned)

Consensus reporting (planned)
    └──requires──> Robust MarkdownV2 escaping utility
"Full breakdown" button (planned)
    └──requires──> Robust MarkdownV2 escaping utility
    └──requires──> Message-length pagination

/start onboarding ──enhances──> Pre-flight image quality gate (sets expectations before first rejection)

Self-consistency resampling ──conflicts──> 30s latency budget, global spend cap (both locked constraints)
Multi-round model debate ──conflicts──> "no model sees another model's output" (locked constraint)
```

### Dependency Notes

- **Pre-flight image quality gate precedes Inference:** the whole point is to avoid spending six paid model calls (two of them frontier-tier) on an image that will produce garbage transcriptions regardless of model quality. It must sit in the ingestion path before the fan-out, not after.
- **Lab-spread-aware annotation requires boot-time lab-diversity validation:** the per-model lab identity is already computed at startup to enforce the ≥4-distinct-labs rule; reusing that mapping at report time is a display-layer change, not a new subsystem.
- **Structured A/B/C/D input requires the "Wrong answer" button:** it's a refinement of the button's follow-up interaction, not a standalone feature.
- **MarkdownV2 escaping blocks both consensus reporting and full breakdown:** both planned features render model-generated free text inside MarkdownV2 messages; an escaping bug in one will very likely also exist in the other if handled ad hoc rather than through one shared utility.
- **Self-consistency resampling conflicts with the locked cost/latency constraints:** flagged as a real tradeoff, not dismissed — see Scope Tensions.

## MVP Definition

### Launch With (v1)

Everything already Active in PROJECT.md, plus the table-stakes gaps found in this research:

- [ ] `/start` and `/help` onboarding — a bot with no onboarding is not usable by a 10-40 person group without a support channel
- [ ] Pre-flight image quality gate (blur + resolution) — directly attacks the user's own named dominant failure mode, cheap to build (S)
- [ ] Robust MarkdownV2 escaping utility — the consensus spoiler and full breakdown will render model-generated text; this will break silently and confusingly without it
- [ ] Message-length pagination for "Full breakdown" — six models' reasoning will exceed the 4096-char cap in normal operation, not as an edge case
- [ ] Structured A/B/C/D inline buttons for "Wrong answer" corrections — protects the integrity of the one dataset the deferred eval harness will depend on
- [ ] Friendly quota-exceeded messaging — cheap, and the daily cap is already load-bearing for cost control

### Add After Validation (v1.x)

- [ ] Lab-spread-aware consensus annotation ("5/6 agree, spanning 4 labs") — valuable but not launch-blocking; add once the base consensus report is proven out with real study-group usage
- [ ] Telegram API 429 retry/backoff hardening — add once real traffic patterns (burst usage during a study session) are observed

### Future Consideration (v2+)

- [ ] Self-consistency resampling — only worth revisiting if the deferred eval harness (v2) shows per-model accuracy is the bottleneck rather than image quality or elimination-reasoning failures; costly on both axes this project has hard caps on
- [ ] Private `/mystats` — only if retention becomes an observed problem; not needed to validate the core consensus premise

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| `/start` / `/help` onboarding | HIGH | LOW | P1 |
| Pre-flight image quality gate | HIGH | LOW | P1 |
| MarkdownV2 escaping utility | HIGH | LOW | P1 |
| Message pagination for Full breakdown | MEDIUM | LOW | P1 |
| Structured A/B/C/D correction input | MEDIUM | LOW | P1 |
| Friendly quota-exceeded messaging | MEDIUM | LOW | P1 |
| Lab-spread-aware consensus annotation | HIGH | MEDIUM | P2 |
| Telegram 429 retry/backoff | MEDIUM | LOW | P2 |
| Private `/mystats` | LOW | LOW | P3 |
| Self-consistency resampling | HIGH (accuracy) | HIGH (cost/latency) | P3, conditional on v2 eval data |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Scope Tensions

*Per instructions: noted once, not relitigated against the locked Out of Scope list.*

- Self-consistency resampling (2-3x sampling per model, majority vote before ensemble vote) has the strongest published accuracy effect found in this entire research pass (+3 to +23 points depending on model/task), but the "one round, no cascade" decision forecloses it on cost/latency grounds — worth revisiting only if v2 eval data shows per-model reasoning failures, not image quality, are the accuracy bottleneck.

## Competitor Feature Analysis

| Feature | ConvergePanel (multi-LLM comparison product) | Generic Discord/Telegram quiz bots (QuizBot, Studybot) | Our Approach |
|---------|---|---|---|
| Independent multi-model answers, no cross-contamination | Core product: "one question in, five independent model responses out" | N/A — single-source quiz content, not model-generated | Already the core design; validated by this analog existing as a standalone product category |
| Consensus score / disagreement map | Explicit disagreement map alongside consensus score | N/A | Already planned (6/6, 5/1, 4/2, 3/3 tiers); recommend adding lab-spread as a second dimension |
| Gamification (leaderboards, streaks) | Not applicable (general-purpose tool) | Core feature — real-time scoring, leaderboards | Deliberately not building this (see Anti-Features) — study-group trust signal, not competitive gamification, is the goal |
| Image-based question input | Not applicable (text-only comparison tool) | Not typical — quiz content is authored, not photographed | Core to this bot's use case; no direct analog found, which is why the pre-flight quality gate has no off-the-shelf precedent to copy |

## Sources

- [Self-Consistency Prompting: Enhancing AI Accuracy](https://learnprompting.org/docs/intermediate/self_consistency) — MEDIUM
- [LLMs Can Generate a Better Answer by Aggregating Their Own Responses (arxiv 2503.04104)](https://arxiv.org/pdf/2503.04104) — MEDIUM
- [On Verbalized Confidence Scores for LLMs (arxiv 2412.14737)](https://arxiv.org/html/2412.14737v2) — HIGH
- [Calibrating Verbalized Confidence with Self-Generated Distractors (arxiv 2509.25532)](https://arxiv.org/pdf/2509.25532) — MEDIUM
- [Nine Judges, Two Effective Votes: Correlated Errors Undermine LLM Evaluation Panels (arxiv 2605.29800, Apple ML Research)](https://machinelearning.apple.com/research/correlated-llm-evaluation-panels) — HIGH
- [Replacing Judges with Juries: Evaluating LLM Generations with a Panel of Diverse Models (arxiv 2404.18796)](https://arxiv.org/abs/2404.18796) — MEDIUM-HIGH
- [More Bias, Less Bias: BiasPrompting for Enhanced Multiple-Choice Question Answering (arxiv 2511.20086)](https://arxiv.org/html/2511.20086) — MEDIUM-HIGH
- ["According to...": Prompting Language Models Improves Quoting from Pre-Training Data (arxiv 2305.13252)](https://arxiv.org/pdf/2305.13252) — MEDIUM
- [Claude: Reduce hallucinations (official docs)](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations) — HIGH (official)
- [Context-Independent OCR with Multimodal LLMs: Effects of Image Resolution and Visual Complexity (arxiv 2503.23667)](https://arxiv.org/pdf/2503.23667) — MEDIUM
- [How to Check for Blurry Images Using the Laplacian Method](https://www.geeksforgeeks.org/computer-vision/how-to-check-for-blurry-images-in-your-dataset-using-the-laplacian-method/) — MEDIUM (practitioner)
- [10 Best UX Practices for Telegram Bots](https://medium.com/@bsideeffect/10-best-ux-practices-for-telegram-bots-79ffed24b6de) — LOW-MEDIUM (practitioner blog)
- [Telegram Bot API Rate Limits Explained](https://botnamefinder.com/blog/telegram-bot-rate-limits-explained) — LOW-MEDIUM (practitioner)
- [Multi-LLM Answer Comparison: Compare AI Models — ConvergePanel](https://convergepanel.com/use-cases/multi-llm-answer-comparison) — MEDIUM (product page, but directly validates the core premise)
- [QuizBot (Discord study quiz bot, GitHub)](https://github.com/SHJavaheri/QuizBot) — LOW (single example, used for anti-feature contrast only)
- `.planning/PROJECT.md` — project scope, locked constraints, and Out of Scope list (primary source of truth for this research)

---
*Feature research for: Telegram-based multi-model SAT Reading & Writing consensus bot*
*Researched: 2026-09-10*
