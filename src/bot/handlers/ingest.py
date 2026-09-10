import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender
from aiogram.utils.formatting import Text

from bot.formatting.reply import build_rejection
from bot.images.extract import ImageSource, select_file_id
from bot.orchestrator.contract import RejectionReason
from bot.pipeline import Deps, answer_question
from bot.runtime_state import is_paused

logger = logging.getLogger(__name__)

router = Router()


async def _send(message: Message, content: Text) -> None:
    kwargs = content.as_kwargs()
    try:
        await message.answer(**kwargs)
    except TelegramBadRequest:
        logger.error("formatted reply failed to send, falling back to plain text")
        await message.answer(text=kwargs["text"])


_PAUSED_TEXT = "The bot is paused right now. Try again a bit later."


async def _handle_update(message: Message, deps: Deps) -> None:
    if is_paused():
        await _send(message, Text(_PAUSED_TEXT))
        return

    selection = select_file_id(message.photo, message.document)
    if selection is None:
        rejection = build_rejection(RejectionReason.no_image, source_is_photo=bool(message.photo))
        await _send(message, rejection)
        return

    if message.from_user is None:
        logger.warning("received update with no from_user chat_id=%s", message.chat.id)
        return

    file_id, source = selection
    buffer = await message.bot.download(file_id)
    data = buffer.read()
    logger.info("received update chat_id=%s bytes=%d", message.chat.id, len(data))

    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        content = await answer_question(
            deps,
            data,
            source_is_photo=(source is ImageSource.photo),
            user_id=message.from_user.id,
            image_file_id=file_id,
        )
    await _send(message, content)


@router.message(F.photo)
async def handle_photo(message: Message, deps: Deps) -> None:
    await _handle_update(message, deps)


@router.message(F.document)
async def handle_document(message: Message, deps: Deps) -> None:
    await _handle_update(message, deps)
