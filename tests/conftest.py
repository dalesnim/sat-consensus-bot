import io
from collections.abc import AsyncGenerator
from pathlib import Path

import aiosqlite
import pytest
from PIL import Image

from bot.db.connection import open_connection


@pytest.fixture
def sample_image_bytes() -> bytes:
    image = Image.new("RGB", (200, 100), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
async def db(tmp_path: Path) -> AsyncGenerator[aiosqlite.Connection]:
    conn = await open_connection(tmp_path / "test.db")
    try:
        yield conn
    finally:
        await conn.close()
