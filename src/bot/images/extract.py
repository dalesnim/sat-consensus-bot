import base64
import io
from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

from PIL import Image, UnidentifiedImageError

_MIME_BY_FORMAT = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}


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
