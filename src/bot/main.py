import logging
import os
import sys
from pathlib import Path

import httpx
from aiogram import Bot, Dispatcher

from bot.config import Settings, load_roster, load_settings
from bot.db.connection import open_connection
from bot.db.users import seed_allowlist
from bot.handlers.ingest import router
from bot.handlers.owner import router as owner_router
from bot.middleware.access import AccessMiddleware
from bot.pipeline import Deps
from bot.validation.boot import BootValidationError, validate_roster

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _http_timeout(per_model_timeout: float) -> httpx.Timeout:
    """httpx defaults every phase to 5s, which silently overrides the far longer
    per-model budget enforced by asyncio.wait_for in the fan-out. Reasoning models
    routinely take 15-30s to first byte, so the default kills them mid-round and the
    round degrades to `insufficient` for a reason that has nothing to do with the models.
    Read is set above the per-model budget so wait_for stays the authoritative governor
    and abstentions are reported as `timeout` rather than `transport_error:ReadTimeout`.
    """
    return httpx.Timeout(connect=10.0, read=per_model_timeout + 5.0, write=30.0, pool=10.0)


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
        min_valid_responses = int(
            os.environ.get(
                "MIN_VALID_RESPONSES", str(Settings.model_fields["min_valid_responses"].default)
            )
        )
        per_model_timeout = int(
            os.environ.get(
                "PER_MODEL_TIMEOUT_SECONDS",
                str(Settings.model_fields["per_model_timeout_seconds"].default),
            )
        )
    else:
        settings = load_settings()
        base_url = settings.openrouter_base_url
        models_config_path = settings.models_config_path
        min_valid_responses = settings.min_valid_responses
        per_model_timeout = settings.per_model_timeout_seconds

    roster = load_roster(models_config_path)

    async with httpx.AsyncClient(timeout=_http_timeout(per_model_timeout)) as client:
        try:
            await validate_roster(
                roster,
                base_url=base_url,
                client=client,
                min_valid_responses=min_valid_responses,
            )
        except BootValidationError as exc:
            logger.critical("roster validation failed: %s", exc)
            raise SystemExit(1) from exc

        if validate_only:
            labs = {m.lab for m in roster.models}
            print(f"roster ok: {len(roster.models)} models, {len(labs)} labs")
            return

        conn = await open_connection(settings.db_path)
        try:
            await seed_allowlist(conn, settings.allowlist_ids)
            deps = Deps(settings=settings, roster=roster, http=client, db=conn)
            token = settings.telegram_bot_token.get_secret_value()
            bot = Bot(token=token)
            dispatcher = Dispatcher(deps=deps)
            dispatcher.message.outer_middleware(AccessMiddleware())
            dispatcher.include_router(owner_router)
            dispatcher.include_router(router)
            await dispatcher.start_polling(bot)
        finally:
            await conn.close()
