import asyncio
from pathlib import Path

import aiosqlite
import pytest

from bot.config import Settings, load_settings
from bot.db.users import ensure_user, try_consume_daily


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OWNER_ID", raising=False)
    monkeypatch.delenv("ALLOWED_USER_IDS", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-telegram-token")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    return load_settings()


def test_settings_allowlist_ids_parses_comma_separated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "y")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1,2, 3")
    loaded = load_settings()
    assert loaded.allowlist_ids == frozenset({1, 2, 3})


def test_settings_allowlist_ids_empty_string_returns_empty_frozenset(settings: Settings) -> None:
    assert settings.allowlist_ids == frozenset()


def test_settings_owner_id_defaults_to_none(settings: Settings) -> None:
    assert settings.owner_id is None


async def test_ensure_user_idempotent_preserves_daily_count(db: aiosqlite.Connection) -> None:
    await ensure_user(db, 42)
    await try_consume_daily(db, 42, cap=40, day="2026-09-10")
    await ensure_user(db, 42)
    cursor = await db.execute("SELECT COUNT(*), daily_count FROM users WHERE telegram_id = 42")
    row = await cursor.fetchone()
    assert row[0] == 1
    assert row[1] == 1


async def test_try_consume_daily_true_for_fresh_allowlisted_user(db: aiosqlite.Connection) -> None:
    await ensure_user(db, 1)
    assert await try_consume_daily(db, 1, cap=40, day="2026-09-10") is True
    cursor = await db.execute("SELECT daily_count FROM users WHERE telegram_id = 1")
    row = await cursor.fetchone()
    assert row[0] == 1


async def test_try_consume_daily_false_when_user_not_allowed(db: aiosqlite.Connection) -> None:
    await ensure_user(db, 2, is_allowed=False)
    assert await try_consume_daily(db, 2, cap=40, day="2026-09-10") is False


async def test_try_consume_daily_false_for_user_with_no_row(db: aiosqlite.Connection) -> None:
    assert await try_consume_daily(db, 999, cap=40, day="2026-09-10") is False


async def test_try_consume_daily_false_past_cap(db: aiosqlite.Connection) -> None:
    await ensure_user(db, 3)
    for _ in range(2):
        assert await try_consume_daily(db, 3, cap=2, day="2026-09-10") is True
    assert await try_consume_daily(db, 3, cap=2, day="2026-09-10") is False


async def test_try_consume_daily_resets_on_new_day(db: aiosqlite.Connection) -> None:
    await ensure_user(db, 4)
    assert await try_consume_daily(db, 4, cap=1, day="2026-09-10") is True
    assert await try_consume_daily(db, 4, cap=1, day="2026-09-10") is False
    assert await try_consume_daily(db, 4, cap=1, day="2026-09-11") is True
    cursor = await db.execute("SELECT daily_count FROM users WHERE telegram_id = 4")
    row = await cursor.fetchone()
    assert row[0] == 1


async def test_try_consume_daily_concurrent_admits_exactly_one(db: aiosqlite.Connection) -> None:
    await ensure_user(db, 5)
    results = await asyncio.gather(
        *[try_consume_daily(db, 5, cap=1, day="2026-09-10") for _ in range(10)]
    )
    assert results.count(True) == 1
