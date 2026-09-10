from dataclasses import dataclass
from datetime import datetime, timedelta

import aiosqlite


@dataclass(frozen=True)
class CostReport:
    day: str
    spend_today: float
    reserved_today: float
    cap_usd: float
    spend_week: float
    questions_today: int
    cache_hits_today: int
    reduced_rounds_today: int
    cost_per_question_today: float
    cost_per_question_all_time: float
    cache_hit_rate_today: float


async def build_cost_report(
    conn: aiosqlite.Connection, *, cap_usd: float, now: datetime
) -> CostReport:
    day = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=6)).strftime("%Y-%m-%d")

    cursor = await conn.execute(
        "SELECT day, reserved_usd, actual_usd FROM spend_days WHERE day BETWEEN ? AND ?",
        (week_start, day),
    )
    spend_rows = await cursor.fetchall()
    spend_today = 0.0
    reserved_today = 0.0
    spend_week = 0.0
    for row_day, reserved_usd, actual_usd in spend_rows:
        spend_week += actual_usd
        if row_day == day:
            spend_today = actual_usd
            reserved_today = reserved_usd

    cursor = await conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(served_from_cache), 0), "
        "COALESCE(SUM(reduced_model_set), 0) FROM questions "
        "WHERE substr(created_at, 1, 10) = ?",
        (day,),
    )
    questions_row = await cursor.fetchone()
    questions_today = questions_row[0] if questions_row else 0
    cache_hits_today = questions_row[1] if questions_row else 0
    reduced_rounds_today = questions_row[2] if questions_row else 0

    paid_questions_today = questions_today - cache_hits_today
    cost_per_question_today = (
        spend_today / paid_questions_today if paid_questions_today > 0 else 0.0
    )
    cache_hit_rate_today = (
        (cache_hits_today / questions_today) * 100 if questions_today > 0 else 0.0
    )

    cursor = await conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM attempts")
    cost_row = await cursor.fetchone()
    total_cost = cost_row[0] if cost_row else 0.0

    cursor = await conn.execute("SELECT COUNT(*) FROM questions WHERE served_from_cache = 0")
    paid_row = await cursor.fetchone()
    paid_questions_all_time = paid_row[0] if paid_row else 0
    cost_per_question_all_time = (
        total_cost / paid_questions_all_time if paid_questions_all_time > 0 else 0.0
    )

    return CostReport(
        day=day,
        spend_today=spend_today,
        reserved_today=reserved_today,
        cap_usd=cap_usd,
        spend_week=spend_week,
        questions_today=questions_today,
        cache_hits_today=cache_hits_today,
        reduced_rounds_today=reduced_rounds_today,
        cost_per_question_today=cost_per_question_today,
        cost_per_question_all_time=cost_per_question_all_time,
        cache_hit_rate_today=cache_hit_rate_today,
    )
