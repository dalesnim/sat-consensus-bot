import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.utils.formatting import Text

from bot.db.users import add_user
from bot.pipeline import Deps

logger = logging.getLogger(__name__)

router = Router()

_USAGE_TEXT = "Usage: /adduser <telegram_id>"
_REFUSAL_TEXT = (
    "This bot is invite-only. If you've paid for access, message the owner with your "
    "Telegram ID and they'll add you."
)


async def _send(message: Message, text: str) -> None:
    kwargs = Text(text).as_kwargs()
    try:
        await message.answer(**kwargs)
    except TelegramBadRequest:
        logger.error("owner reply failed to send, falling back to plain text")
        await message.answer(text=kwargs["text"])


@router.message(Command("adduser"))
async def handle_adduser(message: Message, command: CommandObject, deps: Deps) -> None:
    if deps.settings.owner_id is None:
        logger.critical("OWNER_ID is unset; /adduser is disabled for everyone")
        await _send(message, _REFUSAL_TEXT)
        return

    if message.from_user is None or message.from_user.id != deps.settings.owner_id:
        await _send(message, _REFUSAL_TEXT)
        return

    if command.args is None:
        await _send(message, _USAGE_TEXT)
        return

    try:
        telegram_id = int(command.args.strip())
    except ValueError:
        await _send(message, _USAGE_TEXT)
        return

    created = await add_user(deps.db, telegram_id)
    if created:
        await _send(message, f"Added {telegram_id}. They can start sending questions now.")
    else:
        await _send(message, f"{telegram_id} already has access.")
