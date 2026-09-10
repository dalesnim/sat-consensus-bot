from collections.abc import Sequence
from enum import StrEnum
from typing import Any


class ImageSource(StrEnum):
    photo = "photo"
    document = "document"


def select_file_id(
    photo_sizes: Sequence[Any] | None, document: Any | None
) -> tuple[str, ImageSource] | None:
    raise NotImplementedError


def to_data_url(data: bytes) -> str:
    raise NotImplementedError
