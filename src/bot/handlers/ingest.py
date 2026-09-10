import logging

from aiogram import F, Router
from aiogram.types import Message

from bot.formatting.reply import build_rejection
from bot.orchestrator.contract import RejectionReason
from bot.pipeline import answer_question

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.photo)
async def handle_photo(message: Message) -> None:
    photo = message.photo[-1]
    buffer = await message.bot.download(photo.file_id)
    data = buffer.read()
    logger.info(
        "received photo chat_id=%s file_unique_id=%s bytes=%d",
        message.chat.id,
        photo.file_unique_id,
        len(data),
    )
    content = await answer_question(data, source_is_photo=True)
    await message.answer(**content.as_kwargs())


@router.message(F.document)
async def handle_document(message: Message) -> None:
    document = message.document
    if not document.mime_type or not document.mime_type.startswith("image/"):
        rejection = build_rejection(RejectionReason.no_image, source_is_photo=False)
        await message.answer(**rejection.as_kwargs())
        return

    buffer = await message.bot.download(document.file_id)
    data = buffer.read()
    logger.info(
        "received document chat_id=%s file_unique_id=%s bytes=%d",
        message.chat.id,
        document.file_unique_id,
        len(data),
    )
    content = await answer_question(data, source_is_photo=False)
    await message.answer(**content.as_kwargs())
