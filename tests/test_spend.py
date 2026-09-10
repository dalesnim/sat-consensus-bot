import asyncio

import aiosqlite
import pytest

from bot.db.spend import day_totals, reconcile, reserve


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
    assert reserved == pytest.approx(0.0)
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
