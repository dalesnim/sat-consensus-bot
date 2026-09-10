import io
from dataclasses import dataclass

import pytest
from PIL import Image, ImageFilter

from bot.images.extract import (
    ImageSource,
    QualityGrade,
    grade_image,
    select_file_id,
    to_data_url,
)

MIN_DIMENSION = 1000
BLUR_WARN = 100.0
BLUR_REJECT = 5.0


def _sharp_page(width: int = 1200, height: int = 1600) -> Image.Image:
    return Image.effect_noise((width, height), 60).convert("L")


def _sharp_page_bytes(width: int = 1200, height: int = 1600) -> bytes:
    buffer = io.BytesIO()
    _sharp_page(width, height).save(buffer, format="PNG")
    return buffer.getvalue()


def _blurred_page_bytes(radius: float, width: int = 1200, height: int = 1600) -> bytes:
    image = _sharp_page(width, height).filter(ImageFilter.GaussianBlur(radius=radius))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


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


class TestGradeImage:
    def test_sharp_full_size_image_grades_ok(self) -> None:
        report = grade_image(
            _sharp_page_bytes(),
            min_dimension=MIN_DIMENSION,
            blur_warn=BLUR_WARN,
            blur_reject=BLUR_REJECT,
        )
        assert report.grade == QualityGrade.ok
        assert report.reason is None
        assert (report.width, report.height) == (1200, 1600)

    def test_small_sharp_image_grades_reject_on_resolution(self) -> None:
        report = grade_image(
            _sharp_page_bytes(200, 260),
            min_dimension=MIN_DIMENSION,
            blur_warn=BLUR_WARN,
            blur_reject=BLUR_REJECT,
        )
        assert report.grade == QualityGrade.reject
        assert "resolution" in report.reason
        assert (report.width, report.height) == (200, 260)

    def test_heavily_blurred_image_grades_reject_on_blur(self) -> None:
        report = grade_image(
            _blurred_page_bytes(radius=8),
            min_dimension=MIN_DIMENSION,
            blur_warn=BLUR_WARN,
            blur_reject=BLUR_REJECT,
        )
        assert report.grade == QualityGrade.reject
        assert "blur" in report.reason

    def test_mildly_blurred_image_grades_warn(self) -> None:
        report = grade_image(
            _blurred_page_bytes(radius=2),
            min_dimension=MIN_DIMENSION,
            blur_warn=BLUR_WARN,
            blur_reject=BLUR_REJECT,
        )
        assert report.grade == QualityGrade.warn

    def test_blur_variance_strictly_greater_for_sharp_image(self) -> None:
        sharp = grade_image(
            _sharp_page_bytes(),
            min_dimension=MIN_DIMENSION,
            blur_warn=BLUR_WARN,
            blur_reject=BLUR_REJECT,
        )
        blurred = grade_image(
            _blurred_page_bytes(radius=8),
            min_dimension=MIN_DIMENSION,
            blur_warn=BLUR_WARN,
            blur_reject=BLUR_REJECT,
        )
        assert sharp.blur_variance > blurred.blur_variance

    def test_undecodable_bytes_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            grade_image(
                b"not an image",
                min_dimension=MIN_DIMENSION,
                blur_warn=BLUR_WARN,
                blur_reject=BLUR_REJECT,
            )

    def test_respects_caller_supplied_min_dimension(self) -> None:
        report = grade_image(
            _sharp_page_bytes(),
            min_dimension=3000,
            blur_warn=BLUR_WARN,
            blur_reject=BLUR_REJECT,
        )
        assert report.grade == QualityGrade.reject
