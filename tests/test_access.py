import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import aiosqlite
import httpx
import pytest
from pydantic import SecretStr

from bot.config import ModelConfig, RosterConfig, Settings, load_settings
from bot.db.users import ensure_user, try_consume_daily
from bot.middleware.access import AccessMiddleware
from bot.pipeline import Deps


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


ROSTER = RosterConfig(
    models=[ModelConfig(id="anthropic/claude-opus-5", lab="anthropic", reasoning="omit")],
    min_distinct_labs=1,
    max_tokens=2000,
)


def _middleware_settings(*, owner_id: int | None = None, cap: int = 40) -> Settings:
    return Settings(
        telegram_bot_token=SecretStr("test-telegram-token"),
        openrouter_api_key=SecretStr("test-openrouter-key"),
        owner_id=owner_id,
        per_user_daily_cap=cap,
    )


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeChat:
    id: int = 1


class _FakeMessage:
    def __init__(
        self,
        *,
        from_user: _FakeUser | None,
        photo: object = None,
        document: object = None,
    ) -> None:
        self.from_user = from_user
        self.photo = photo
        self.document = document
        self.chat = _FakeChat()
        self.answer = AsyncMock()


async def _run_middleware(deps: Deps, message: _FakeMessage) -> AsyncMock:
    handler = AsyncMock(return_value="handled")
    await AccessMiddleware()(handler, message, {"deps": deps})
    return handler


async def test_middleware_blocks_unknown_photo_user_zero_http(db: aiosqlite.Connection) -> None:
    request_log: list[str] = []

    def transport_handler(request: httpx.Request) -> httpx.Response:
        request_log.append(request.url.path)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport_handler)) as client:
        deps = Deps(settings=_middleware_settings(), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=1), photo=["p"])
        handler = await _run_middleware(deps, message)

    handler.assert_not_called()
    assert request_log == []


async def test_middleware_photo_refusal_copy_for_unallowlisted_user(
    db: aiosqlite.Connection,
) -> None:
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_middleware_settings(), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=1), photo=["p"])
        await _run_middleware(deps, message)

    message.answer.assert_called_once()
    assert "invite-only" in message.answer.call_args.kwargs["text"]


async def test_middleware_allowlisted_user_under_cap_reaches_handler(
    db: aiosqlite.Connection,
) -> None:
    await ensure_user(db, 7)
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_middleware_settings(cap=40), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=7), photo=["p"])
        handler = await _run_middleware(deps, message)

    handler.assert_called_once()


async def test_middleware_allowlisted_user_at_cap_refused(db: aiosqlite.Connection) -> None:
    await ensure_user(db, 8)
    # Must be the same UTC day the middleware computes at call time. A literal date here
    # makes the test pass only on that one calendar day and silently stop covering the
    # cap on every other day.
    await try_consume_daily(db, 8, cap=1, day=datetime.now(UTC).strftime("%Y-%m-%d"))
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_middleware_settings(cap=1), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=8), photo=["p"])
        handler = await _run_middleware(deps, message)

    handler.assert_not_called()
    message.answer.assert_called_once()
    assert "today's questions" in message.answer.call_args.kwargs["text"]


async def test_middleware_drops_message_with_no_from_user(db: aiosqlite.Connection) -> None:
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_middleware_settings(), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=None, photo=["p"])
        handler = await _run_middleware(deps, message)

    handler.assert_not_called()
    message.answer.assert_not_called()


async def test_middleware_owner_bypasses_without_users_row(db: aiosqlite.Connection) -> None:
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_middleware_settings(owner_id=999), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=999), photo=["p"])
        handler = await _run_middleware(deps, message)

    handler.assert_called_once()


async def test_middleware_refuses_adduser_from_non_allowlisted_non_owner(
    db: aiosqlite.Connection,
) -> None:
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_middleware_settings(owner_id=999), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=1))
        handler = await _run_middleware(deps, message)

    handler.assert_not_called()
    message.answer.assert_called_once()


async def test_middleware_text_message_does_not_consume_daily_slot(
    db: aiosqlite.Connection,
) -> None:
    await ensure_user(db, 9)
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_middleware_settings(cap=1), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=9))
        handler = await _run_middleware(deps, message)

    handler.assert_called_once()
    cursor = await db.execute("SELECT daily_count FROM users WHERE telegram_id = 9")
    row = await cursor.fetchone()
    assert row[0] == 0


async def test_middleware_database_error_refuses_not_pass_through(db: aiosqlite.Connection) -> None:
    await ensure_user(db, 10)
    await db.close()
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_middleware_settings(), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=10), photo=["p"])
        handler = await _run_middleware(deps, message)

    handler.assert_not_called()
