from pathlib import Path

import aiosqlite

from bot.db.connection import open_connection


async def test_open_connection_sets_wal_journal_mode(tmp_path: Path) -> None:
    conn = await open_connection(tmp_path / "a.db")
    try:
        async with conn.execute("PRAGMA journal_mode") as cursor:
            row = await cursor.fetchone()
        assert row[0] == "wal"
    finally:
        await conn.close()


async def test_open_connection_sets_foreign_keys_on(tmp_path: Path) -> None:
    conn = await open_connection(tmp_path / "a.db")
    try:
        async with conn.execute("PRAGMA foreign_keys") as cursor:
            row = await cursor.fetchone()
        assert row[0] == 1
    finally:
        await conn.close()


async def test_open_connection_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "dir" / "a.db"
    conn = await open_connection(nested)
    try:
        assert nested.parent.is_dir()
    finally:
        await conn.close()


async def test_open_connection_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "a.db"
    first = await open_connection(path)
    await first.close()
    second = await open_connection(path)
    try:
        pass
    finally:
        await second.close()


async def test_open_connection_creates_all_four_tables(tmp_path: Path) -> None:
    conn = await open_connection(tmp_path / "a.db")
    try:
        async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
            rows = await cursor.fetchall()
        names = {row[0] for row in rows}
        assert {"questions", "attempts", "users", "spend_days"} <= names
    finally:
        await conn.close()


async def test_db_fixture_connection_is_aiosqlite(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA journal_mode") as cursor:
        row = await cursor.fetchone()
    assert row[0] == "wal"
