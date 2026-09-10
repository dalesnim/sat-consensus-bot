import logging
import os

from aiogram import Bot, Dispatcher

from bot.handlers.ingest import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


async def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    bot = Bot(token=token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)
