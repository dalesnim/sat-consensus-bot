from collections.abc import Iterable
from datetime import UTC, datetime

import aiosqlite


async def ensure_user(
    conn: aiosqlite.Connection, telegram_id: int, *, is_allowed: bool = True
) -> None:
    await conn.execute(
        """
        INSERT INTO users (telegram_id, added_at, is_allowed)
        VALUES (?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET is_allowed = excluded.is_allowed
        """,
        (telegram_id, datetime.now(UTC).isoformat(), int(is_allowed)),
    )


async def seed_allowlist(conn: aiosqlite.Connection, ids: Iterable[int]) -> None:
    for telegram_id in ids:
        await ensure_user(conn, telegram_id)


async def add_user(conn: aiosqlite.Connection, telegram_id: int) -> bool:
    cursor = await conn.execute(
        """
        INSERT INTO users (telegram_id, added_at, is_allowed)
        VALUES (?, ?, 1)
        ON CONFLICT(telegram_id) DO NOTHING
        RETURNING telegram_id
        """,
        (telegram_id, datetime.now(UTC).isoformat()),
    )
    row = await cursor.fetchone()
    if row is None:
        await conn.execute("UPDATE users SET is_allowed = 1 WHERE telegram_id = ?", (telegram_id,))
        return False
    return True


async def is_allowed(conn: aiosqlite.Connection, telegram_id: int) -> bool:
    cursor = await conn.execute(
        "SELECT is_allowed FROM users WHERE telegram_id = ?", (telegram_id,)
    )
    row = await cursor.fetchone()
    return row is not None and bool(row[0])


async def try_consume_daily(
    conn: aiosqlite.Connection, telegram_id: int, *, cap: int, day: str
) -> bool:
    cursor = await conn.execute(
        """
        UPDATE users
        SET daily_count = CASE WHEN daily_count_date = ? THEN daily_count + 1 ELSE 1 END,
            daily_count_date = ?
        WHERE telegram_id = ?
          AND is_allowed = 1
          AND (daily_count_date IS NULL OR daily_count_date <> ? OR daily_count < ?)
        """,
        (day, day, telegram_id, day, cap),
    )
    return cursor.rowcount == 1
