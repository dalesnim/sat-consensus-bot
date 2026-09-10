import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from aiogram.utils.formatting import Text

from bot.db import users as users_repo
from bot.pipeline import Deps

logger = logging.getLogger(__name__)

_NOT_ALLOWLISTED_TEXT = (
    "This bot is invite-only. If you've paid for access, message the owner with your "
    "Telegram ID and they'll add you."
)


def _cap_reached_text(cap: int) -> str:
    return f"You've used all {cap} of today's questions. The limit resets at midnight UTC."


async def _send(message: Message, text: str) -> None:
    kwargs = Text(text).as_kwargs()
    try:
        await message.answer(**kwargs)
    except TelegramBadRequest:
        logger.error("access refusal reply failed to send, falling back to plain text")
        await message.answer(text=kwargs["text"])


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:  # noqa: ANN401 — overrides aiogram.BaseMiddleware's own Any-typed signature
        if event.from_user is None:
            logger.warning("dropping update with no from_user chat_id=%s", event.chat.id)
            return None

        deps: Deps = data["deps"]
        uid = event.from_user.id

        try:
            if deps.settings.owner_id is not None and uid == deps.settings.owner_id:
                return await handler(event, data)

            if not (event.photo or event.document):
                if await users_repo.is_allowed(deps.db, uid):
                    return await handler(event, data)
                await _send(event, _NOT_ALLOWLISTED_TEXT)
                return None

            day = datetime.now(UTC).strftime("%Y-%m-%d")
            admitted = await users_repo.try_consume_daily(
                deps.db, uid, cap=deps.settings.per_user_daily_cap, day=day
            )
            if admitted:
                return await handler(event, data)

            if await users_repo.is_allowed(deps.db, uid):
                await _send(event, _cap_reached_text(deps.settings.per_user_daily_cap))
            else:
                await _send(event, _NOT_ALLOWLISTED_TEXT)
            return None
        except Exception:
            logger.error(
                "access middleware database error for uid=%s, refusing", uid, exc_info=True
            )
            return None
