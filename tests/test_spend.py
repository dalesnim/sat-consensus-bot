import asyncio

import aiosqlite
import httpx
import pytest

from bot.config import ModelConfig, RosterConfig, Settings, load_settings
from bot.cost.guard import reserve_round
from bot.db.spend import day_totals, reconcile, reserve
from bot.validation.boot import BootValidationError, validate_roster

_MODELS = [
    ModelConfig(
        id="anthropic/claude-opus-5", lab="anthropic", reasoning="omit", est_cost_usd=0.058
    ),
    ModelConfig(
        id="anthropic/claude-sonnet-5",
        lab="anthropic",
        reasoning="omit",
        est_cost_usd=0.019,
        in_reduced_set=True,
    ),
    ModelConfig(id="openai/gpt-6-astra", lab="openai", reasoning="none", est_cost_usd=0.024),
    ModelConfig(
        id="openai/gpt-5.6-sol",
        lab="openai",
        reasoning="none",
        est_cost_usd=0.004,
        in_reduced_set=True,
    ),
    ModelConfig(
        id="google/gemini-3.7-flash",
        lab="google",
        reasoning="none",
        est_cost_usd=0.004,
        in_reduced_set=True,
    ),
    ModelConfig(
        id="mistralai/mistral-large-2512",
        lab="mistralai",
        reasoning="minimal",
        est_cost_usd=0.002,
        in_reduced_set=True,
    ),
]
_ROSTER = RosterConfig(models=_MODELS, min_distinct_labs=4, max_tokens=2000)
_REDUCED_IDS = [
    "anthropic/claude-sonnet-5",
    "openai/gpt-5.6-sol",
    "google/gemini-3.7-flash",
    "mistralai/mistral-large-2512",
]


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-telegram-token")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    return load_settings()


def _with_cap(settings: Settings, cap: float) -> Settings:
    return settings.model_copy(update={"daily_spend_cap_usd": cap})


async def test_reserve_creates_row_and_admits_when_amount_fits(
    db: aiosqlite.Connection,
) -> None:
    admitted = await reserve(db, day="2026-09-11", amount=0.5, cap=1.0)
    assert admitted is True
    reserved, actual = await day_totals(db, "2026-09-11")
    assert reserved == pytest.approx(0.5)
    assert actual == pytest.approx(0.0)


async def test_reserve_refuses_when_amount_alone_exceeds_cap(
    db: aiosqlite.Connection,
) -> None:
    admitted = await reserve(db, day="2026-09-11", amount=1.5, cap=1.0)
    assert admitted is False


async def test_reserve_admits_until_the_cap_then_refuses(db: aiosqlite.Connection) -> None:
    day = "2026-09-11"
    assert await reserve(db, day=day, amount=0.4, cap=1.0) is True
    assert await reserve(db, day=day, amount=0.4, cap=1.0) is True
    assert await reserve(db, day=day, amount=0.4, cap=1.0) is False


async def test_reserved_usd_unchanged_after_a_refused_reserve(db: aiosqlite.Connection) -> None:
    day = "2026-09-11"
    await reserve(db, day=day, amount=0.9, cap=1.0)
    reserved_before, _ = await day_totals(db, day)
    admitted = await reserve(db, day=day, amount=0.2, cap=1.0)
    assert admitted is False
    reserved_after, _ = await day_totals(db, day)
    assert reserved_after == reserved_before


async def test_twenty_concurrent_reserves_admit_exactly_seven(db: aiosqlite.Connection) -> None:
    day = "2026-09-11"
    results = await asyncio.gather(
        *[reserve(db, day=day, amount=0.14, cap=1.00) for _ in range(20)]
    )
    assert sum(1 for admitted in results if admitted) == 7
    reserved, _ = await day_totals(db, day)
    assert reserved == pytest.approx(0.98)


async def test_reconcile_releases_reservation_and_books_actual(db: aiosqlite.Connection) -> None:
    day = "2026-09-11"
    await reserve(db, day=day, amount=0.5, cap=1.0)
    await reconcile(db, day=day, estimate=0.5, actual=0.3)
    reserved, actual = await day_totals(db, day)
    # reserved_usd = reserved(0.5) - estimate(0.5) + actual(0.3): the estimate's hold is
    # released and the real cost is booked, so reserved_usd converges to actual spend
    # once nothing is left in flight.
    assert reserved == pytest.approx(0.3)
    assert actual == pytest.approx(0.3)


async def test_reconcile_never_drives_reserved_below_zero(db: aiosqlite.Connection) -> None:
    day = "2026-09-11"
    await reserve(db, day=day, amount=0.2, cap=1.0)
    await reconcile(db, day=day, estimate=0.5, actual=0.1)
    reserved, actual = await day_totals(db, day)
    assert reserved == pytest.approx(0.0)
    assert actual == pytest.approx(0.1)


async def test_day_totals_returns_zeros_for_missing_day(db: aiosqlite.Connection) -> None:
    reserved, actual = await day_totals(db, "2099-01-01")
    assert reserved == 0.0
    assert actual == 0.0


def test_reduced_models_returns_only_flagged_models_in_roster_order() -> None:
    ids = [m.id for m in _ROSTER.reduced_models]
    assert ids == _REDUCED_IDS


def test_estimate_usd_sums_and_applies_multiplier() -> None:
    estimate = _ROSTER.estimate_usd(_ROSTER.models, multiplier=1.25)
    assert estimate == pytest.approx(0.111 * 1.25, rel=1e-6)


def test_reduced_estimate_usd_sums_and_applies_multiplier() -> None:
    estimate = _ROSTER.estimate_usd(_ROSTER.reduced_models, multiplier=1.25)
    assert estimate == pytest.approx(0.029 * 1.25, rel=1e-6)


async def test_validate_roster_raises_when_a_model_has_no_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = [m.model_copy(update={"est_cost_usd": 0.0}) if m.id == "openai/gpt-6-astra" else m
              for m in _MODELS]
    roster = RosterConfig(models=models, min_distinct_labs=4, max_tokens=2000)
    async with httpx.AsyncClient() as client:
        with pytest.raises(BootValidationError) as exc_info:
            await validate_roster(
                roster, base_url="https://openrouter.ai/api/v1", client=client
            )
    assert "openai/gpt-6-astra" in str(exc_info.value)


async def test_validate_roster_raises_when_reduced_set_spans_too_few_labs() -> None:
    models = [
        m.model_copy(update={"in_reduced_set": m.lab == "anthropic"}) for m in _MODELS
    ]
    roster = RosterConfig(models=models, min_distinct_labs=4, max_tokens=2000)
    async with httpx.AsyncClient() as client:
        with pytest.raises(BootValidationError) as exc_info:
            await validate_roster(
                roster, base_url="https://openrouter.ai/api/v1", client=client
            )
    assert "reduced set" in str(exc_info.value)


async def test_validate_roster_raises_when_reduced_set_too_small() -> None:
    models = [m.model_copy(update={"in_reduced_set": False}) for m in _MODELS]
    roster = RosterConfig(models=models, min_distinct_labs=1, max_tokens=2000)
    async with httpx.AsyncClient() as client:
        with pytest.raises(BootValidationError) as exc_info:
            await validate_roster(
                roster,
                base_url="https://openrouter.ai/api/v1",
                client=client,
                min_valid_responses=3,
            )
    assert "reduced set" in str(exc_info.value)


async def test_reserve_round_returns_full_set_with_headroom(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    current = _with_cap(settings, 1.0)
    decision = await reserve_round(db, _ROSTER, current, day="2026-09-11")
    assert decision.reduced is False
    assert decision.exhausted is False
    assert [m.id for m in decision.models] == [m.id for m in _ROSTER.models]
    assert decision.estimate_usd == pytest.approx(0.111 * current.round_cost_safety_multiplier)


async def test_reserve_round_falls_back_to_reduced_set_above_cap(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    current = _with_cap(settings, 0.1)
    decision = await reserve_round(db, _ROSTER, current, day="2026-09-11")
    assert decision.reduced is True
    assert decision.exhausted is False
    assert [m.id for m in decision.models] == _REDUCED_IDS
    reserved, _ = await day_totals(db, "2026-09-11")
    assert reserved == pytest.approx(decision.estimate_usd)


async def test_reserve_round_exhausted_when_neither_fits(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    current = _with_cap(settings, 0.01)
    decision = await reserve_round(db, _ROSTER, current, day="2026-09-11")
    assert decision.exhausted is True
    assert decision.models == ()
    reserved, _ = await day_totals(db, "2026-09-11")
    assert reserved == pytest.approx(0.0)


async def test_reserve_round_reserves_exactly_once_on_fallback(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    current = _with_cap(settings, 0.1)
    await reserve_round(db, _ROSTER, current, day="2026-09-11")
    reserved, _ = await day_totals(db, "2026-09-11")
    reduced_estimate = _ROSTER.estimate_usd(
        _ROSTER.reduced_models, multiplier=current.round_cost_safety_multiplier
    )
    assert reserved == pytest.approx(reduced_estimate)
