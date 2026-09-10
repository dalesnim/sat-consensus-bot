import json
import logging

import aiosqlite
import httpx
import pytest

from bot.config import ModelConfig, RosterConfig, Settings, load_settings
from bot.pipeline import Deps, answer_question
from tests.fixtures.verdicts import (
    abstaining_verdict_json,
    multi_question_verdict_json,
    valid_verdict_json,
)
from tests.test_images import _blurred_page_bytes, _sharp_page_bytes

MODELS = [
    ModelConfig(id="anthropic/claude-opus-5", lab="anthropic", reasoning="omit"),
    ModelConfig(id="anthropic/claude-sonnet-5", lab="anthropic", reasoning="omit"),
    ModelConfig(id="openai/gpt-6-astra", lab="openai", reasoning="none"),
    ModelConfig(id="openai/gpt-5.6-sol", lab="openai", reasoning="none"),
    ModelConfig(id="google/gemini-3.7-flash", lab="google", reasoning="none"),
    ModelConfig(id="deepseek/deepseek-v4.1-flash", lab="deepseek", reasoning="minimal"),
]
MODEL_IDS = [m.id for m in MODELS]
ROSTER = RosterConfig(models=MODELS, min_distinct_labs=4, max_tokens=2000)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-telegram-token")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("MIN_IMAGE_DIMENSION", "1000")
    monkeypatch.setenv("BLUR_VARIANCE_WARN", "100.0")
    monkeypatch.setenv("BLUR_VARIANCE_REJECT", "5.0")
    monkeypatch.setenv("MIN_VALID_RESPONSES", "3")
    return load_settings()


def _transport(
    responses: dict[str, str] | None = None,
    *,
    error_models: set[str] | None = None,
    request_log: list[str] | None = None,
) -> httpx.MockTransport:
    responses = responses or {}
    error_models = error_models or set()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        model_id = payload["model"]
        if request_log is not None:
            request_log.append(model_id)
        if model_id in error_models:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": responses[model_id]}}]}
        )

    return httpx.MockTransport(handler)


def _deps(current_settings: Settings, client: httpx.AsyncClient, db: aiosqlite.Connection) -> Deps:
    return Deps(settings=current_settings, roster=ROSTER, http=client, db=db)


async def test_oversized_image_rejected_before_any_request(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    request_log: list[str] = []
    oversized = b"x" * (settings.max_image_bytes + 1)

    async with httpx.AsyncClient(transport=_transport(request_log=request_log)) as client:
        result = await answer_question(
            _deps(settings, client, db),
            oversized,
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    assert "can't read this clearly" in result.as_kwargs()["text"]
    assert request_log == []


async def test_reject_grade_image_rejected_before_any_request(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    request_log: list[str] = []
    heavily_blurred = _blurred_page_bytes(radius=8)

    async with httpx.AsyncClient(transport=_transport(request_log=request_log)) as client:
        result = await answer_question(
            _deps(settings, client, db),
            heavily_blurred,
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    assert "can't read this clearly" in result.as_kwargs()["text"]
    assert request_log == []


async def test_warn_grade_image_proceeds_and_logs_warning(
    settings: Settings, caplog: pytest.LogCaptureFixture, db: aiosqlite.Connection
) -> None:
    mildly_blurred = _blurred_page_bytes(radius=2)
    responses = {model_id: valid_verdict_json("B") for model_id in MODEL_IDS}

    with caplog.at_level(logging.WARNING, logger="bot.pipeline"):
        async with httpx.AsyncClient(transport=_transport(responses)) as client:
            result = await answer_question(
                _deps(settings, client, db),
                mildly_blurred,
                source_is_photo=True,
                user_id=1,
                image_file_id="file123",
            )

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "agree" in result.as_kwargs()["text"]


async def test_not_sat_verbal_majority_rejects(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    responses = {
        MODEL_IDS[0]: abstaining_verdict_json(),
        MODEL_IDS[1]: abstaining_verdict_json(),
        MODEL_IDS[2]: abstaining_verdict_json(),
        MODEL_IDS[3]: abstaining_verdict_json(),
        MODEL_IDS[4]: valid_verdict_json("B"),
        MODEL_IDS[5]: valid_verdict_json("B"),
    }

    async with httpx.AsyncClient(transport=_transport(responses)) as client:
        result = await answer_question(
            _deps(settings, client, db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    assert "doesn't look like an SAT" in result.as_kwargs()["text"]


async def test_multiple_questions_majority_rejects(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    responses = {
        MODEL_IDS[0]: multi_question_verdict_json(),
        MODEL_IDS[1]: multi_question_verdict_json(),
        MODEL_IDS[2]: multi_question_verdict_json(),
        MODEL_IDS[3]: multi_question_verdict_json(),
        MODEL_IDS[4]: valid_verdict_json("B"),
        MODEL_IDS[5]: valid_verdict_json("B"),
    }

    async with httpx.AsyncClient(transport=_transport(responses)) as client:
        result = await answer_question(
            _deps(settings, client, db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    assert "more than one question" in result.as_kwargs()["text"]


async def test_not_verbal_decision_ignores_abstaining_models(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    responses = {
        MODEL_IDS[0]: abstaining_verdict_json(),
        MODEL_IDS[1]: abstaining_verdict_json(),
    }
    errors = set(MODEL_IDS[2:])

    async with httpx.AsyncClient(transport=_transport(responses, error_models=errors)) as client:
        result = await answer_question(
            _deps(settings, client, db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    text = result.as_kwargs()["text"]
    assert "doesn't look like an SAT" not in text
    assert "of 6 models answered" in text


async def test_insufficient_apology_for_two_ok_four_abstain(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    responses = {
        MODEL_IDS[0]: valid_verdict_json("B"),
        MODEL_IDS[1]: valid_verdict_json("B"),
    }
    errors = set(MODEL_IDS[2:])

    async with httpx.AsyncClient(transport=_transport(responses, error_models=errors)) as client:
        result = await answer_question(
            _deps(settings, client, db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    kwargs = result.as_kwargs()
    assert "2 of 6 models answered" in kwargs["text"]
    assert not kwargs["entities"]


async def test_strong_consensus_six_agree(settings: Settings, db: aiosqlite.Connection) -> None:
    responses = {model_id: valid_verdict_json("C") for model_id in MODEL_IDS}

    async with httpx.AsyncClient(transport=_transport(responses)) as client:
        result = await answer_question(
            _deps(settings, client, db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    text = result.as_kwargs()["text"]
    assert "Answer: C" in text
    assert "(6/6 agree" in text
    for model_id in MODEL_IDS:
        assert f"• {model_id}: C" in text


async def test_degraded_header_names_abstention_count(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    responses = {model_id: valid_verdict_json("B") for model_id in MODEL_IDS[:4]}
    errors = set(MODEL_IDS[4:])

    async with httpx.AsyncClient(transport=_transport(responses, error_models=errors)) as client:
        result = await answer_question(
            _deps(settings, client, db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    text = result.as_kwargs()["text"]
    assert "(4/6 agree" in text
    assert text.count("I couldn't generate an answer for that.") == 2


async def test_never_raises_on_undecodable_bytes(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    request_log: list[str] = []
    async with httpx.AsyncClient(transport=_transport(request_log=request_log)) as client:
        result = await answer_question(
            _deps(settings, client, db),
            b"not an image at all",
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    assert "can't read this clearly" in result.as_kwargs()["text"]
    assert request_log == []


async def test_never_raises_on_zero_length_bytes(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    request_log: list[str] = []
    async with httpx.AsyncClient(transport=_transport(request_log=request_log)) as client:
        result = await answer_question(
            _deps(settings, client, db),
            b"",
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    assert "can't read this clearly" in result.as_kwargs()["text"]
    assert request_log == []


async def test_never_raises_when_all_six_models_error(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    async with httpx.AsyncClient(transport=_transport(error_models=set(MODEL_IDS))) as client:
        result = await answer_question(
            _deps(settings, client, db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    assert "0 of 6 models answered" in result.as_kwargs()["text"]


async def test_clean_round_issues_exactly_six_requests(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    request_log: list[str] = []
    responses = {model_id: valid_verdict_json("B") for model_id in MODEL_IDS}

    async with httpx.AsyncClient(
        transport=_transport(responses, request_log=request_log)
    ) as client:
        await answer_question(
            _deps(settings, client, db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    assert len(request_log) == 6


async def test_unresolved_split_escalates_to_the_tiebreak_model(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    """Fable is not in the round; it is called only when the round fails to decide."""
    responses = {
        MODEL_IDS[0]: valid_verdict_json("A"),
        MODEL_IDS[1]: valid_verdict_json("A"),
        MODEL_IDS[2]: valid_verdict_json("B"),
        MODEL_IDS[3]: valid_verdict_json("B"),
        MODEL_IDS[4]: valid_verdict_json("C"),
        MODEL_IDS[5]: valid_verdict_json("C"),
        "anthropic/claude-fable-5.1": valid_verdict_json("D"),
    }
    roster = ROSTER.model_copy(
        update={
            "tiebreak_model": ModelConfig(
                id="anthropic/claude-fable-5.1", lab="anthropic", reasoning="omit"
            )
        }
    )
    async with httpx.AsyncClient(transport=_transport(responses)) as client:
        result = await answer_question(
            Deps(settings=settings, roster=roster, http=client, db=db),
            _sharp_page_bytes(),
            source_is_photo=False,
            user_id=1,
            image_file_id="fid",
        )

    text = result.as_kwargs()["text"]
    assert "Answer: D" in text
    assert "Tiebreak" in text
    assert "claude-fable-5.1" in text


async def test_clear_majority_never_calls_the_tiebreak_model(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    responses = {model_id: valid_verdict_json("C") for model_id in MODEL_IDS}
    roster = ROSTER.model_copy(
        update={
            "tiebreak_model": ModelConfig(
                id="anthropic/claude-fable-5.1", lab="anthropic", reasoning="omit"
            )
        }
    )
    async with httpx.AsyncClient(transport=_transport(responses)) as client:
        result = await answer_question(
            Deps(settings=settings, roster=roster, http=client, db=db),
            _sharp_page_bytes(),
            source_is_photo=False,
            user_id=1,
            image_file_id="fid",
        )

    text = result.as_kwargs()["text"]
    assert "Answer: C" in text
    assert "Tiebreak" not in text
    assert "fable" not in text.lower()
