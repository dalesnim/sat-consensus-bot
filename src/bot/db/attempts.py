import json
from collections.abc import Sequence

import aiosqlite

from bot.orchestrator.contract import AttemptResult

_RAW_FIRST_RESPONSE_LIMIT = 4000


def _row_for(result: AttemptResult) -> tuple[object, ...]:
    answer = result.verdict.answer if result.status == "ok" and result.verdict else None
    raw_first_response = (
        result.raw_first_response[:_RAW_FIRST_RESPONSE_LIMIT]
        if result.raw_first_response is not None
        else None
    )
    raw_json = json.dumps(
        {
            "verdict": result.verdict.model_dump(mode="json") if result.verdict else None,
            "raw_first_response": raw_first_response,
            "repaired": result.repaired,
        }
    )
    return (
        result.model_id,
        'single',
        answer,
        None,
        raw_json,
        round(result.latency_s * 1000),
        result.prompt_tokens,
        result.completion_tokens,
        result.cost_usd,
        result.abstain_reason,
    )


async def insert_attempts(
    conn: aiosqlite.Connection, question_id: int, results: Sequence[AttemptResult]
) -> None:
    rows = [(question_id, *_row_for(result)) for result in results]
    await conn.executemany(
        """
        INSERT INTO attempts (
            question_id, model_id, tier, answer, confidence, raw_json,
            latency_ms, input_tokens, output_tokens, cost_usd, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
