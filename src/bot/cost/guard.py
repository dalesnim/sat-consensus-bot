import logging
from dataclasses import dataclass

import aiosqlite

from bot.config import ModelConfig, RosterConfig, Settings
from bot.db.spend import reserve

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpendDecision:
    models: tuple[ModelConfig, ...]
    reduced: bool
    estimate_usd: float
    exhausted: bool


async def reserve_round(
    conn: aiosqlite.Connection, roster: RosterConfig, settings: Settings, *, day: str
) -> SpendDecision:
    cap = settings.daily_spend_cap_usd
    multiplier = settings.round_cost_safety_multiplier

    full_estimate = roster.estimate_usd(roster.models, multiplier=multiplier)
    if await reserve(conn, day=day, amount=full_estimate, cap=cap):
        return SpendDecision(
            models=tuple(roster.models),
            reduced=False,
            estimate_usd=full_estimate,
            exhausted=False,
        )

    reduced_estimate = roster.estimate_usd(roster.reduced_models, multiplier=multiplier)
    if await reserve(conn, day=day, amount=reduced_estimate, cap=cap):
        logger.warning(
            "daily spend cap reached for day=%s, falling back to reduced model set", day
        )
        return SpendDecision(
            models=tuple(roster.reduced_models),
            reduced=True,
            estimate_usd=reduced_estimate,
            exhausted=False,
        )

    logger.error("daily spend cap exhausted for day=%s even for the reduced set", day)
    return SpendDecision(models=(), reduced=True, estimate_usd=0.0, exhausted=True)
