from datetime import UTC, datetime

import aiosqlite

from bot.cost.report import build_cost_report

_NOW = datetime(2026, 9, 11, 12, 0, 0, tzinfo=UTC)
_TODAY = "2026-09-11"
_YESTERDAY = "2026-09-10"


async def _insert_question(
    conn: aiosqlite.Connection,
    *,
    created_at: str,
    served_from_cache: bool = False,
    reduced_model_set: bool = False,
) -> int:
    cursor = await conn.execute(
        """
        INSERT INTO questions (
            phash, image_sha256, created_at, consensus_state, user_id,
            consensus_json, served_from_cache, reduced_model_set
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "phash",
            "sha256",
            created_at,
            "strong",
            1,
            "{}",
            int(served_from_cache),
            int(reduced_model_set),
        ),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


async def _insert_attempt(conn: aiosqlite.Connection, *, question_id: int, cost_usd: float) -> None:
    await conn.execute(
        """
        INSERT INTO attempts (question_id, model_id, answer, latency_ms, cost_usd)
        VALUES (?, ?, ?, ?, ?)
        """,
        (question_id, "anthropic/claude-opus-5", "A", 1000, cost_usd),
    )


async def _insert_spend_day(
    conn: aiosqlite.Connection, *, day: str, reserved_usd: float, actual_usd: float
) -> None:
    await conn.execute(
        "INSERT INTO spend_days (day, reserved_usd, actual_usd) VALUES (?, ?, ?)",
        (day, reserved_usd, actual_usd),
    )


async def test_empty_database_returns_zeros(db: aiosqlite.Connection) -> None:
    report = await build_cost_report(db, cap_usd=1.0, now=_NOW)

    assert report.day == _TODAY
    assert report.spend_today == 0.0
    assert report.reserved_today == 0.0
    assert report.spend_week == 0.0
    assert report.questions_today == 0
    assert report.cache_hits_today == 0
    assert report.reduced_rounds_today == 0
    assert report.cost_per_question_today == 0.0
    assert report.cost_per_question_all_time == 0.0
    assert report.cache_hit_rate_today == 0.0
    assert report.cap_usd == 1.0


async def test_spend_today_equals_actual_usd_of_current_day(db: aiosqlite.Connection) -> None:
    await _insert_spend_day(db, day=_TODAY, reserved_usd=2.0, actual_usd=1.23)

    report = await build_cost_report(db, cap_usd=5.0, now=_NOW)

    assert report.spend_today == 1.23
    assert report.reserved_today == 2.0


async def test_spend_week_sums_seven_days_ending_today_inclusive(
    db: aiosqlite.Connection,
) -> None:
    week_days = [
        "2026-09-05",
        "2026-09-06",
        "2026-09-07",
        "2026-09-08",
        "2026-09-09",
        "2026-09-10",
        "2026-09-11",
    ]
    for day in week_days:
        await _insert_spend_day(db, day=day, reserved_usd=0.0, actual_usd=1.0)
    await _insert_spend_day(db, day="2026-09-04", reserved_usd=0.0, actual_usd=100.0)

    report = await build_cost_report(db, cap_usd=5.0, now=_NOW)

    assert report.spend_week == 7.0


async def test_questions_today_counts_including_cache_served(db: aiosqlite.Connection) -> None:
    await _insert_question(db, created_at=f"{_TODAY}T10:00:00+00:00")
    await _insert_question(db, created_at=f"{_TODAY}T11:00:00+00:00")
    await _insert_question(
        db, created_at=f"{_TODAY}T12:00:00+00:00", served_from_cache=True
    )

    report = await build_cost_report(db, cap_usd=5.0, now=_NOW)

    assert report.questions_today == 3
    assert report.cache_hits_today == 1


async def test_cost_per_question_today_divides_by_non_cache_questions(
    db: aiosqlite.Connection,
) -> None:
    await _insert_spend_day(db, day=_TODAY, reserved_usd=0.0, actual_usd=1.0)
    await _insert_question(db, created_at=f"{_TODAY}T10:00:00+00:00")
    await _insert_question(db, created_at=f"{_TODAY}T11:00:00+00:00")

    report = await build_cost_report(db, cap_usd=5.0, now=_NOW)

    assert report.cost_per_question_today == 0.5


async def test_cost_per_question_today_zero_when_no_paid_questions(
    db: aiosqlite.Connection,
) -> None:
    await _insert_spend_day(db, day=_TODAY, reserved_usd=0.0, actual_usd=1.0)
    await _insert_question(db, created_at=f"{_TODAY}T10:00:00+00:00", served_from_cache=True)

    report = await build_cost_report(db, cap_usd=5.0, now=_NOW)

    assert report.cost_per_question_today == 0.0


async def test_cache_hit_rate_today_zero_when_no_questions_today(
    db: aiosqlite.Connection,
) -> None:
    report = await build_cost_report(db, cap_usd=5.0, now=_NOW)

    assert report.cache_hit_rate_today == 0.0


async def test_cache_hit_rate_today_computed_as_percentage(db: aiosqlite.Connection) -> None:
    await _insert_question(db, created_at=f"{_TODAY}T10:00:00+00:00")
    await _insert_question(db, created_at=f"{_TODAY}T11:00:00+00:00", served_from_cache=True)

    report = await build_cost_report(db, cap_usd=5.0, now=_NOW)

    assert report.cache_hit_rate_today == 50.0


async def test_reduced_rounds_today_counts_flagged_rows(db: aiosqlite.Connection) -> None:
    await _insert_question(db, created_at=f"{_TODAY}T10:00:00+00:00", reduced_model_set=True)
    await _insert_question(db, created_at=f"{_TODAY}T11:00:00+00:00")

    report = await build_cost_report(db, cap_usd=5.0, now=_NOW)

    assert report.reduced_rounds_today == 1


async def test_question_from_previous_day_excluded_from_today_figures(
    db: aiosqlite.Connection,
) -> None:
    await _insert_question(db, created_at=f"{_YESTERDAY}T23:59:59+00:00")

    report = await build_cost_report(db, cap_usd=5.0, now=_NOW)

    assert report.questions_today == 0
    assert report.cache_hits_today == 0
    assert report.reduced_rounds_today == 0


async def test_cost_per_question_all_time_uses_attempts_and_non_cache_questions(
    db: aiosqlite.Connection,
) -> None:
    q1 = await _insert_question(db, created_at=f"{_YESTERDAY}T10:00:00+00:00")
    q2 = await _insert_question(db, created_at=f"{_TODAY}T10:00:00+00:00")
    await _insert_question(
        db,
        created_at=f"{_TODAY}T11:00:00+00:00",
        served_from_cache=True,
    )
    await _insert_attempt(db, question_id=q1, cost_usd=0.6)
    await _insert_attempt(db, question_id=q2, cost_usd=0.4)

    report = await build_cost_report(db, cap_usd=5.0, now=_NOW)

    assert report.cost_per_question_all_time == 0.5


async def test_cost_per_question_all_time_zero_when_no_paid_questions(
    db: aiosqlite.Connection,
) -> None:
    report = await build_cost_report(db, cap_usd=5.0, now=_NOW)

    assert report.cost_per_question_all_time == 0.0
