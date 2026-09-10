import base64
import io
from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError
from pydantic import BaseModel

Image.MAX_IMAGE_PIXELS = 50_000_000

_MIME_BY_FORMAT = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}

_LAPLACIAN_KERNEL = ImageFilter.Kernel(
    size=(3, 3), kernel=(0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128
)


class ImageSource(StrEnum):
    photo = "photo"
    document = "document"


class _PhotoSizeLike(Protocol):
    file_id: str


class _DocumentLike(Protocol):
    file_id: str
    mime_type: str | None


def select_file_id(
    photo_sizes: Sequence[_PhotoSizeLike] | None, document: _DocumentLike | None
) -> tuple[str, ImageSource] | None:
    if document is not None:
        if document.mime_type is not None and document.mime_type.startswith("image/"):
            return document.file_id, ImageSource.document
        return None
    if photo_sizes:
        return photo_sizes[-1].file_id, ImageSource.photo
    return None


def to_data_url(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = image.format
    except UnidentifiedImageError as exc:
        raise ValueError(f"could not identify image format: {exc}") from exc

    mime = _MIME_BY_FORMAT.get(image_format or "")
    if mime is None:
        raise ValueError(f"unsupported image format: {image_format}")

    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


class QualityGrade(StrEnum):
    ok = "ok"
    warn = "warn"
    reject = "reject"


class QualityReport(BaseModel):
    grade: QualityGrade
    width: int
    height: int
    blur_variance: float
    reason: str | None


def grade_image(
    data: bytes, *, min_dimension: int, blur_warn: float, blur_reject: float
) -> QualityReport:
    try:
        with Image.open(io.BytesIO(data)) as image:
            grayscale = image.convert("L")
    except UnidentifiedImageError as exc:
        raise ValueError(f"could not identify image format: {exc}") from exc

    width, height = grayscale.size
    filtered = grayscale.filter(_LAPLACIAN_KERNEL)
    blur_variance = ImageStat.Stat(filtered).stddev[0] ** 2

    hard_floor = min_dimension // 2
    if min(width, height) < hard_floor:
        return QualityReport(
            grade=QualityGrade.reject,
            width=width,
            height=height,
            blur_variance=blur_variance,
            reason=f"resolution {width}x{height} is below the hard floor of {hard_floor}px",
        )
    if blur_variance < blur_reject:
        return QualityReport(
            grade=QualityGrade.reject,
            width=width,
            height=height,
            blur_variance=blur_variance,
            reason=(
                f"blur variance {blur_variance:.2f} is below the reject "
                f"threshold {blur_reject}"
            ),
        )
    if min(width, height) < min_dimension:
        return QualityReport(
            grade=QualityGrade.warn,
            width=width,
            height=height,
            blur_variance=blur_variance,
            reason=f"resolution {width}x{height} is below the recommended {min_dimension}px",
        )
    if blur_variance < blur_warn:
        return QualityReport(
            grade=QualityGrade.warn,
            width=width,
            height=height,
            blur_variance=blur_variance,
            reason=f"blur variance {blur_variance:.2f} is below the recommended {blur_warn}",
        )
    return QualityReport(
        grade=QualityGrade.ok,
        width=width,
        height=height,
        blur_variance=blur_variance,
        reason=None,
    )
