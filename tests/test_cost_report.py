from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import aiosqlite
import httpx
from pydantic import SecretStr

from bot.config import ModelConfig, RosterConfig, Settings
from bot.cost.report import build_cost_report
from bot.handlers.owner import handle_cost
from bot.pipeline import Deps

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


_ROSTER = RosterConfig(
    models=[ModelConfig(id="anthropic/claude-opus-5", lab="anthropic", reasoning="omit")],
    min_distinct_labs=1,
    max_tokens=2000,
)


def _settings(*, owner_id: int | None) -> Settings:
    return Settings(
        telegram_bot_token=SecretStr("test-telegram-token"),
        openrouter_api_key=SecretStr("test-openrouter-key"),
        owner_id=owner_id,
        daily_spend_cap_usd=5.0,
    )


@dataclass
class _FakeUser:
    id: int


class _FakeMessage:
    def __init__(self, *, from_user: _FakeUser | None) -> None:
        self.from_user = from_user
        self.answer = AsyncMock()


async def test_cost_from_owner_reports_spend_and_cache_hit_rate(
    db: aiosqlite.Connection,
) -> None:
    handler_today = datetime.now(UTC).strftime("%Y-%m-%d")
    await _insert_spend_day(db, day=handler_today, reserved_usd=0.0, actual_usd=1.5)
    await _insert_question(db, created_at=f"{handler_today}T10:00:00+00:00")
    await _insert_question(
        db, created_at=f"{handler_today}T11:00:00+00:00", served_from_cache=True
    )

    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_settings(owner_id=999), roster=_ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=999))
        await handle_cost(message, deps)

    message.answer.assert_called_once()
    text = message.answer.call_args.kwargs["text"]
    assert "1.5000" in text
    assert "5.0000" in text
    assert "50.0" in text


async def test_cost_from_owner_reply_contains_utc(db: aiosqlite.Connection) -> None:
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_settings(owner_id=999), roster=_ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=999))
        await handle_cost(message, deps)

    text = message.answer.call_args.kwargs["text"]
    assert "UTC" in text


async def test_cost_from_non_owner_refuses_with_no_numbers(db: aiosqlite.Connection) -> None:
    await _insert_spend_day(db, day=_TODAY, reserved_usd=0.0, actual_usd=1.5)

    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_settings(owner_id=999), roster=_ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=1))
        await handle_cost(message, deps)

    text = message.answer.call_args.kwargs["text"]
    assert "invite-only" in text
    assert "$" not in text


async def test_cost_with_owner_id_unset_refuses_everyone(db: aiosqlite.Connection) -> None:
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_settings(owner_id=None), roster=_ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=999))
        await handle_cost(message, deps)

    text = message.answer.call_args.kwargs["text"]
    assert "invite-only" in text


async def test_cost_against_empty_database_replies_with_zeroed_figures(
    db: aiosqlite.Connection,
) -> None:
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_settings(owner_id=999), roster=_ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=999))
        await handle_cost(message, deps)

    message.answer.assert_called_once()
    text = message.answer.call_args.kwargs["text"]
    assert "0.0000" in text
