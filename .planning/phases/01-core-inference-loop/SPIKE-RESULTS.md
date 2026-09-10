## Spike run: 2026-09-10T17:01:33.218744+00:00

| model | lab | reasoning | wall_s | prompt_tok | compl_tok | cost_usd | chars | parsed_first_try | error |
|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-opus-5 | anthropic | omit | 32.56 | 4745 | 1904 | 0.0713 | 1287 | yes |  |
| anthropic/claude-sonnet-5 | anthropic | omit | 15.10 | 4745 | 899 | 0.0185 | 1320 | yes |  |
| openai/gpt-5.6-sol | openai | none | 3.42 | - | - | - | - | no | HTTPStatusError |
| deepseek/deepseek-v4.1-flash | deepseek | minimal | 1.76 | - | - | - | - | no | HTTPStatusError |
| openai/gpt-6-astra | openai | none | 1.20 | - | - | - | - | no | HTTPStatusError |
| google/gemini-3.7-flash | google | none | 1.11 | - | - | - | - | no | HTTPStatusError |

- Round wall clock (max across models): 32.56s
- Models returned successfully: 2/6
- cost found at usage.cost

## Decision

Recommended `max_tokens`: 2000 (ceil(max observed completion_tokens * 1.3), rounded up to the nearest 100, capped at 2000)

## Spike run: 2026-09-10T17:04:08.327875+00:00

| model | lab | reasoning | wall_s | prompt_tok | compl_tok | cost_usd | chars | parsed_first_try | error |
|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-opus-5 | anthropic | omit | 19.37 | 4797 | 1143 | 0.0526 | 1356 | yes |  |
| anthropic/claude-sonnet-5 | anthropic | omit | 13.98 | 4797 | 867 | 0.0183 | 1250 | yes |  |
| openai/gpt-6-astra | openai | minimal | 10.42 | 3302 | 428 | 0.0627 | 1391 | yes |  |
| google/gemini-3.7-flash | google | minimal | 5.76 | 2413 | 435 | 0.0034 | 1625 | yes |  |
| openai/gpt-5.6-sol | openai | none | 5.49 | 3302 | 301 | 0.0113 | 1281 | yes |  |
| deepseek/deepseek-v4.1-flash | deepseek | minimal | 1.28 | - | - | - | - | no | HTTPStatusError |

- Round wall clock (max across models): 19.37s
- Models returned successfully: 5/6
- cost found at usage.cost

## Decision

Recommended `max_tokens`: 1500 (ceil(max observed completion_tokens * 1.3), rounded up to the nearest 100, capped at 2000)

## Spike run: 2026-09-10T17:07:55.700689+00:00

| model | lab | reasoning | wall_s | prompt_tok | compl_tok | cost_usd | chars | parsed_first_try | error |
|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-opus-5 | anthropic | omit | 22.10 | 4797 | 1361 | 0.0580 | 1501 | yes |  |
| anthropic/claude-sonnet-5 | anthropic | omit | 13.51 | 4797 | 902 | 0.0186 | 1370 | yes |  |
| openai/gpt-6-astra | openai | minimal | 9.34 | 3302 | 412 | 0.0239 | 1498 | yes |  |
| mistralai/mistral-large-2512 | mistralai | minimal | 6.13 | 3121 | 356 | 0.0021 | 1402 | yes |  |
| openai/gpt-5.6-sol | openai | none | 5.88 | 3302 | 301 | 0.0037 | 1309 | yes |  |
| google/gemini-3.7-flash | google | minimal | 5.30 | 2413 | 452 | 0.0035 | 1674 | yes |  |

- Round wall clock (max across models): 22.10s
- Models returned successfully: 6/6
- cost found at usage.cost

## Decision

Recommended `max_tokens`: 1800 (ceil(max observed completion_tokens * 1.3), rounded up to the nearest 100, capped at 2000)

