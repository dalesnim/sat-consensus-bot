from dataclasses import dataclass
from unittest.mock import AsyncMock

import aiosqlite
import httpx
from aiogram.filters import CommandObject
from pydantic import SecretStr

from bot.config import ModelConfig, RosterConfig, Settings
from bot.db.users import ensure_user, try_consume_daily
from bot.handlers.owner import handle_adduser
from bot.pipeline import Deps

ROSTER = RosterConfig(
    models=[ModelConfig(id="anthropic/claude-opus-5", lab="anthropic", reasoning="omit")],
    min_distinct_labs=1,
    max_tokens=2000,
)


def _settings(*, owner_id: int | None) -> Settings:
    return Settings(
        telegram_bot_token=SecretStr("test-telegram-token"),
        openrouter_api_key=SecretStr("test-openrouter-key"),
        owner_id=owner_id,
    )


@dataclass
class _FakeUser:
    id: int


class _FakeMessage:
    def __init__(self, *, from_user: _FakeUser | None) -> None:
        self.from_user = from_user
        self.answer = AsyncMock()


async def test_adduser_from_owner_creates_row_and_confirms(db: aiosqlite.Connection) -> None:
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_settings(owner_id=999), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=999))
        await handle_adduser(message, CommandObject(args="12345"), deps)

    message.answer.assert_called_once()
    assert "12345" in message.answer.call_args.kwargs["text"]
    cursor = await db.execute("SELECT is_allowed FROM users WHERE telegram_id = 12345")
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1


async def test_adduser_from_non_owner_creates_no_row(db: aiosqlite.Connection) -> None:
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_settings(owner_id=999), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=1))
        await handle_adduser(message, CommandObject(args="12345"), deps)

    cursor = await db.execute("SELECT COUNT(*) FROM users WHERE telegram_id = 12345")
    row = await cursor.fetchone()
    assert row[0] == 0
    message.answer.assert_called_once()
    assert "invite-only" in message.answer.call_args.kwargs["text"]


async def test_adduser_no_argument_replies_with_usage(db: aiosqlite.Connection) -> None:
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_settings(owner_id=999), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=999))
        await handle_adduser(message, CommandObject(args=None), deps)

    assert "Usage" in message.answer.call_args.kwargs["text"]
    cursor = await db.execute("SELECT COUNT(*) FROM users")
    row = await cursor.fetchone()
    assert row[0] == 0


async def test_adduser_non_numeric_argument_replies_with_usage(db: aiosqlite.Connection) -> None:
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_settings(owner_id=999), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=999))
        await handle_adduser(message, CommandObject(args="abc"), deps)

    assert "Usage" in message.answer.call_args.kwargs["text"]
    cursor = await db.execute("SELECT COUNT(*) FROM users")
    row = await cursor.fetchone()
    assert row[0] == 0


async def test_adduser_already_allowlisted_id_does_not_reset_daily_count(
    db: aiosqlite.Connection,
) -> None:
    await ensure_user(db, 12345)
    await try_consume_daily(db, 12345, cap=40, day="2026-09-10")
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_settings(owner_id=999), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=999))
        await handle_adduser(message, CommandObject(args="12345"), deps)

    assert "already" in message.answer.call_args.kwargs["text"].lower()
    cursor = await db.execute("SELECT daily_count FROM users WHERE telegram_id = 12345")
    row = await cursor.fetchone()
    assert row[0] == 1


async def test_adduser_with_owner_id_unset_refuses_everyone(db: aiosqlite.Connection) -> None:
    async with httpx.AsyncClient() as client:
        deps = Deps(settings=_settings(owner_id=None), roster=ROSTER, http=client, db=db)
        message = _FakeMessage(from_user=_FakeUser(id=999))
        await handle_adduser(message, CommandObject(args="12345"), deps)

    cursor = await db.execute("SELECT COUNT(*) FROM users")
    row = await cursor.fetchone()
    assert row[0] == 0
