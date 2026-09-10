import io
from dataclasses import dataclass

import pytest
from PIL import Image

from bot.images.extract import ImageSource, select_file_id, to_data_url


@dataclass
class FakePhotoSize:
    file_id: str


@dataclass
class FakeDocument:
    file_id: str
    mime_type: str | None


def _png_bytes(width: int = 10, height: int = 10) -> bytes:
    image = Image.new("L", (width, height), color=200)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg_bytes(width: int = 100, height: int = 100) -> bytes:
    image = Image.new("RGB", (width, height), color=(120, 40, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class TestSelectFileId:
    def test_photo_only_returns_largest(self) -> None:
        photos = [FakePhotoSize("small"), FakePhotoSize("medium"), FakePhotoSize("large")]
        assert select_file_id(photos, None) == ("large", ImageSource.photo)

    def test_document_preferred_over_photo(self) -> None:
        photos = [FakePhotoSize("small")]
        document = FakeDocument("doc1", "image/jpeg")
        assert select_file_id(photos, document) == ("doc1", ImageSource.document)

    def test_pdf_document_returns_none(self) -> None:
        document = FakeDocument("doc1", "application/pdf")
        assert select_file_id(None, document) is None

    def test_document_with_no_mime_type_returns_none(self) -> None:
        document = FakeDocument("doc1", None)
        assert select_file_id(None, document) is None

    def test_neither_photos_nor_document_returns_none(self) -> None:
        assert select_file_id(None, None) is None
        assert select_file_id([], None) is None


class TestToDataUrl:
    def test_png_data_url(self) -> None:
        url = to_data_url(_png_bytes())
        assert url.startswith("data:image/png;base64,")

    def test_jpeg_data_url(self) -> None:
        url = to_data_url(_jpeg_bytes())
        assert url.startswith("data:image/jpeg;base64,")

    def test_undecodable_bytes_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            to_data_url(b"not an image")
