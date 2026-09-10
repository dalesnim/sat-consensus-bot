import io

import pytest
from PIL import Image


@pytest.fixture
def sample_image_bytes() -> bytes:
    image = Image.new("RGB", (200, 100), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
