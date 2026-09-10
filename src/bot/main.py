import logging
import os
import sys
from pathlib import Path

import httpx
from aiogram import Bot, Dispatcher

from bot.config import Settings, load_roster, load_settings
from bot.db.connection import open_connection
from bot.handlers.ingest import router
from bot.pipeline import Deps
from bot.validation.boot import BootValidationError, validate_roster

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    validate_only = "--validate-only" in sys.argv

    if validate_only:
        base_url = os.environ.get(
            "OPENROUTER_BASE_URL", Settings.model_fields["openrouter_base_url"].default
        )
        models_config_path = Path(
            os.environ.get(
                "MODELS_CONFIG_PATH", str(Settings.model_fields["models_config_path"].default)
            )
        )
    else:
        settings = load_settings()
        base_url = settings.openrouter_base_url
        models_config_path = settings.models_config_path

    roster = load_roster(models_config_path)

    async with httpx.AsyncClient() as client:
        try:
            await validate_roster(roster, base_url=base_url, client=client)
        except BootValidationError as exc:
            logger.critical("roster validation failed: %s", exc)
            raise SystemExit(1) from exc

        if validate_only:
            labs = {m.lab for m in roster.models}
            print(f"roster ok: {len(roster.models)} models, {len(labs)} labs")
            return

        conn = await open_connection(settings.db_path)
        try:
            deps = Deps(settings=settings, roster=roster, http=client, db=conn)
            token = settings.telegram_bot_token.get_secret_value()
            bot = Bot(token=token)
            dispatcher = Dispatcher(deps=deps)
            dispatcher.include_router(router)
            await dispatcher.start_polling(bot)
        finally:
            await conn.close()
