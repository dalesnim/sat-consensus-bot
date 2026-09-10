import aiosqlite


async def reserve(conn: aiosqlite.Connection, *, day: str, amount: float, cap: float) -> bool:
    await conn.execute("INSERT OR IGNORE INTO spend_days (day) VALUES (?)", (day,))
    cursor = await conn.execute(
        "UPDATE spend_days SET reserved_usd = reserved_usd + ? "
        "WHERE day = ? AND reserved_usd + ? <= ?",
        (amount, day, amount, cap),
    )
    return cursor.rowcount == 1


async def reconcile(
    conn: aiosqlite.Connection, *, day: str, estimate: float, actual: float
) -> None:
    await conn.execute(
        "UPDATE spend_days SET reserved_usd = MAX(0, reserved_usd - ? + ?), "
        "actual_usd = actual_usd + ? WHERE day = ?",
        (estimate, actual, actual, day),
    )


async def day_totals(conn: aiosqlite.Connection, day: str) -> tuple[float, float]:
    cursor = await conn.execute(
        "SELECT reserved_usd, actual_usd FROM spend_days WHERE day = ?", (day,)
    )
    row = await cursor.fetchone()
    if row is None:
        return (0.0, 0.0)
    return (row[0], row[1])
