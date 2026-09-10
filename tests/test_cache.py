import io
import logging

import aiosqlite
import httpx
import pytest
from PIL import Image, ImageDraw

from bot import pipeline as pipeline_module
from bot.config import Settings, load_settings
from bot.db.questions import find_cached_question, insert_question
from bot.images.extract import compute_phash
from bot.orchestrator.contract import ConsensusResult, ModelVote, Position
from bot.pipeline import answer_question
from tests.fixtures.verdicts import valid_verdict_json
from tests.test_images import _blurred_page_bytes, _png_bytes, _sharp_page_bytes
from tests.test_pipeline import MODEL_IDS, _deps, _transport


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-telegram-token")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("MIN_IMAGE_DIMENSION", "1000")
    monkeypatch.setenv("BLUR_VARIANCE_WARN", "100.0")
    monkeypatch.setenv("BLUR_VARIANCE_REJECT", "5.0")
    monkeypatch.setenv("MIN_VALID_RESPONSES", "3")
    return load_settings()


def _consensus(*, tier: str = "strong", winning_letter: str | None = "B") -> ConsensusResult:
    return ConsensusResult(
        tier=tier,
        winning_letter=winning_letter,
        positions=[Position(letter="B", votes=6, labs=4, reasoning=["Because."])]
        if winning_letter
        else [],
        model_votes=[
            ModelVote(model_id=m, lab="anthropic", letter=winning_letter) for m in MODEL_IDS
        ],
        total_valid=6 if winning_letter else 0,
        abstentions=0,
        labs_in_majority=4,
        degraded=False,
        transcription_divergence=False,
        question_type=None,
    )


def _template_bytes(text: str, width: int = 400, height: int = 300) -> bytes:
    image = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, width - 10, 120), outline=0)
    draw.text((20, 30), text, fill=0)
    for i, letter in enumerate("ABCD"):
        draw.text((20, 150 + i * 30), f"{letter}. choice text", fill=0)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class TestComputePhash:
    def test_deterministic_on_same_bytes(self) -> None:
        data = _sharp_page_bytes()
        assert compute_phash(data) == compute_phash(data)

    def test_returns_64_char_lowercase_hex_string(self) -> None:
        digest = compute_phash(_png_bytes())
        assert len(digest) == 64
        assert digest == digest.lower()
        int(digest, 16)

    def test_png_and_jpeg_of_same_content_match(self) -> None:
        image = Image.new("RGB", (400, 300), color=(250, 250, 250))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 390, 120), outline=(0, 0, 0))
        draw.text((20, 30), "Same rendered page", fill=(0, 0, 0))

        png_buffer = io.BytesIO()
        image.save(png_buffer, format="PNG")
        jpeg_buffer = io.BytesIO()
        image.save(jpeg_buffer, format="JPEG", quality=95)

        assert compute_phash(png_buffer.getvalue()) == compute_phash(jpeg_buffer.getvalue())

    def test_different_text_yields_different_hash(self) -> None:
        one = _template_bytes("The passage discusses a historical event that changed policy.")
        two = _template_bytes("A completely different topic about marine biology research.")
        assert compute_phash(one) != compute_phash(two)

    def test_undecodable_bytes_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            compute_phash(b"not an image")


class TestFindCachedQuestion:
    async def test_returns_none_when_no_row_shares_phash(self, db) -> None:
        assert await find_cached_question(db, "deadbeef" * 8) is None

    async def test_returns_most_recent_matching_row(self, db) -> None:
        phash = "a" * 64
        consensus = _consensus()
        first_id = await insert_question(
            db,
            phash=phash,
            image_sha256="sha1",
            image_file_id="f1",
            user_id=1,
            consensus=consensus,
        )
        second_id = await insert_question(
            db,
            phash=phash,
            image_sha256="sha2",
            image_file_id="f2",
            user_id=1,
            consensus=consensus,
        )
        await db.commit()

        result = await find_cached_question(db, phash)
        assert result is not None
        assert result.id == second_id
        assert result.id != first_id

    async def test_ignores_rows_with_served_from_cache(self, db) -> None:
        phash = "b" * 64
        consensus = _consensus()
        await insert_question(
            db,
            phash=phash,
            image_sha256="sha1",
            image_file_id="f1",
            user_id=1,
            consensus=consensus,
            served_from_cache=True,
        )
        await db.commit()

        assert await find_cached_question(db, phash) is None

    async def test_ignores_insufficient_rows(self, db) -> None:
        phash = "c" * 64
        consensus = _consensus(tier="insufficient", winning_letter=None)
        await insert_question(
            db,
            phash=phash,
            image_sha256="sha1",
            image_file_id="f1",
            user_id=1,
            consensus=consensus,
        )
        await db.commit()

        assert await find_cached_question(db, phash) is None


async def _question_rows(db: aiosqlite.Connection) -> list[aiosqlite.Row]:
    cursor = await db.execute(
        "SELECT id, served_from_cache, source_question_id FROM questions ORDER BY id"
    )
    return await cursor.fetchall()


async def _attempt_count(db: aiosqlite.Connection) -> int:
    cursor = await db.execute("SELECT COUNT(*) FROM attempts")
    row = await cursor.fetchone()
    return row[0]


class TestPipelineCacheBranch:
    async def test_second_identical_call_performs_zero_requests_and_matches_first_reply(
        self, settings: Settings, db: aiosqlite.Connection
    ) -> None:
        request_log: list[str] = []
        responses = {model_id: valid_verdict_json("C") for model_id in MODEL_IDS}
        image_bytes = _sharp_page_bytes()

        async with httpx.AsyncClient(
            transport=_transport(responses, request_log=request_log)
        ) as client:
            first = await answer_question(
                _deps(settings, client, db),
                image_bytes,
                source_is_photo=True,
                user_id=1,
                image_file_id="file123",
            )
            assert len(request_log) == 6

            second = await answer_question(
                _deps(settings, client, db),
                image_bytes,
                source_is_photo=True,
                user_id=2,
                image_file_id="file456",
            )

        assert len(request_log) == 6
        assert second.as_kwargs()["text"] == first.as_kwargs()["text"]

        rows = await _question_rows(db)
        assert len(rows) == 2
        first_id, first_cache_flag, first_source = rows[0]
        second_id, second_cache_flag, second_source = rows[1]
        assert first_cache_flag == 0
        assert second_cache_flag == 1
        assert second_source == first_id

        assert await _attempt_count(db) == 6

    async def test_sha_mismatch_still_serves_cache_and_logs_warning(
        self,
        settings: Settings,
        db: aiosqlite.Connection,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        consensus = _consensus()
        source_id = await insert_question(
            db,
            phash="fixedhash",
            image_sha256="stale-sha",
            image_file_id="f1",
            user_id=1,
            consensus=consensus,
        )
        await db.commit()

        monkeypatch.setattr(pipeline_module, "compute_phash", lambda data: "fixedhash")

        request_log: list[str] = []
        async with httpx.AsyncClient(transport=_transport(request_log=request_log)) as client:
            with caplog.at_level(logging.WARNING, logger="bot.pipeline"):
                result = await answer_question(
                    _deps(settings, client, db),
                    _sharp_page_bytes(),
                    source_is_photo=True,
                    user_id=2,
                    image_file_id="file789",
                )

        assert request_log == []
        assert "Answer: B" in result.as_kwargs()["text"]

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert str(source_id) in warnings[0].getMessage()

    async def test_quality_rejected_image_never_reaches_cache_lookup(
        self, settings: Settings, db: aiosqlite.Connection
    ) -> None:
        request_log: list[str] = []
        heavily_blurred = _blurred_page_bytes(radius=8)

        async with httpx.AsyncClient(transport=_transport(request_log=request_log)) as client:
            await answer_question(
                _deps(settings, client, db),
                heavily_blurred,
                source_is_photo=True,
                user_id=1,
                image_file_id="file123",
            )

        assert request_log == []
        assert await _question_rows(db) == []

    async def test_cache_lookup_failure_falls_through_to_normal_round(
        self,
        settings: Settings,
        db: aiosqlite.Connection,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def _raise(*args: object, **kwargs: object) -> None:
            raise RuntimeError("db exploded")

        monkeypatch.setattr(pipeline_module.questions_repo, "find_cached_question", _raise)

        request_log: list[str] = []
        responses = {model_id: valid_verdict_json("C") for model_id in MODEL_IDS}
        async with httpx.AsyncClient(
            transport=_transport(responses, request_log=request_log)
        ) as client:
            result = await answer_question(
                _deps(settings, client, db),
                _sharp_page_bytes(),
                source_is_photo=True,
                user_id=1,
                image_file_id="file123",
            )

        assert len(request_log) == 6
        assert "Answer: C" in result.as_kwargs()["text"]
