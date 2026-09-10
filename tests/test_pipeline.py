import json
import logging
from datetime import UTC, datetime

import aiosqlite
import httpx
import pytest

from bot.config import ModelConfig, RosterConfig, Settings, load_settings
from bot.db.spend import day_totals
from bot.formatting import reply as reply_module
from bot.pipeline import Deps, answer_question
from tests.fixtures.verdicts import (
    abstaining_verdict_json,
    multi_question_verdict_json,
    valid_verdict_json,
)
from tests.test_images import _blurred_page_bytes, _sharp_page_bytes

MODELS = [
    ModelConfig(
        id="anthropic/claude-opus-5", lab="anthropic", reasoning="omit", est_cost_usd=0.058
    ),
    ModelConfig(
        id="anthropic/claude-sonnet-5",
        lab="anthropic",
        reasoning="omit",
        est_cost_usd=0.019,
        in_reduced_set=True,
    ),
    ModelConfig(id="openai/gpt-6-astra", lab="openai", reasoning="none", est_cost_usd=0.024),
    ModelConfig(
        id="openai/gpt-5.6-sol",
        lab="openai",
        reasoning="none",
        est_cost_usd=0.004,
        in_reduced_set=True,
    ),
    ModelConfig(
        id="google/gemini-3.7-flash",
        lab="google",
        reasoning="none",
        est_cost_usd=0.004,
        in_reduced_set=True,
    ),
    ModelConfig(
        id="deepseek/deepseek-v4.1-flash",
        lab="deepseek",
        reasoning="minimal",
        est_cost_usd=0.002,
        in_reduced_set=True,
    ),
]
MODEL_IDS = [m.id for m in MODELS]
REDUCED_MODEL_IDS = [m.id for m in MODELS if m.in_reduced_set]
ROSTER = RosterConfig(models=MODELS, min_distinct_labs=4, max_tokens=2000)


def _with_cap(current_settings: Settings, cap: float) -> Settings:
    return current_settings.model_copy(update={"daily_spend_cap_usd": cap})


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


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
    usage: dict[str, float | None] | None = None,
) -> httpx.MockTransport:
    responses = responses or {}
    error_models = error_models or set()
    usage = usage or {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        model_id = payload["model"]
        if request_log is not None:
            request_log.append(model_id)
        if model_id in error_models:
            return httpx.Response(500, json={"error": "boom"})
        body: dict = {"choices": [{"message": {"content": responses[model_id]}}]}
        if model_id in usage and usage[model_id] is not None:
            body["usage"] = {"cost": usage[model_id]}
        return httpx.Response(200, json=body)

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


async def test_under_cap_fires_all_six_and_no_downgrade_disclosure(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    request_log: list[str] = []
    responses = {model_id: valid_verdict_json("B") for model_id in MODEL_IDS}

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

    assert request_log == MODEL_IDS
    assert "reduced" not in result.as_kwargs()["text"].lower()


async def test_above_cap_fires_only_reduced_set_and_discloses_it(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    request_log: list[str] = []
    responses = {model_id: valid_verdict_json("B") for model_id in REDUCED_MODEL_IDS}
    reduced_settings = _with_cap(settings, 0.05)

    async with httpx.AsyncClient(
        transport=_transport(responses, request_log=request_log)
    ) as client:
        result = await answer_question(
            Deps(settings=reduced_settings, roster=ROSTER, http=client, db=db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    assert "anthropic/claude-opus-5" not in request_log
    assert "openai/gpt-6-astra" not in request_log
    assert len(request_log) == 4
    text = result.as_kwargs()["text"]
    assert "smaller, cheaper model set" in text


def test_reduced_set_disclosure_states_no_model_count() -> None:
    """The line must not hardcode a roster size — models.yaml's reduced set has
    already changed once (6-model roster -> 7), and a stale count in the reply
    would tell the user something false about how their answer was produced.
    The tally footer already reports how many models actually voted."""
    assert not any(char.isdigit() for char in reply_module._REDUCED_SET_LINE)


async def test_exhausted_cap_makes_no_request_and_states_budget_exhausted(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    request_log: list[str] = []
    exhausted_settings = _with_cap(settings, 0.001)

    async with httpx.AsyncClient(transport=_transport(request_log=request_log)) as client:
        result = await answer_question(
            Deps(settings=exhausted_settings, roster=ROSTER, http=client, db=db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    assert request_log == []
    assert "budget" in result.as_kwargs()["text"].lower()


async def test_cache_hit_makes_no_reservation(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    responses = {model_id: valid_verdict_json("B") for model_id in MODEL_IDS}
    image_bytes = _sharp_page_bytes()

    async with httpx.AsyncClient(transport=_transport(responses)) as client:
        await answer_question(
            _deps(settings, client, db),
            image_bytes,
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )
        reserved_after_paid_round, _ = await day_totals(db, _today())

        await answer_question(
            _deps(settings, client, db),
            image_bytes,
            source_is_photo=True,
            user_id=2,
            image_file_id="file456",
        )
        reserved_after_cache_hit, _ = await day_totals(db, _today())

    assert reserved_after_cache_hit == reserved_after_paid_round


async def test_actual_spend_reconciled_after_a_completed_round(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    responses = {model_id: valid_verdict_json("B") for model_id in MODEL_IDS}
    usage = {
        "anthropic/claude-opus-5": 0.06,
        "anthropic/claude-sonnet-5": 0.02,
        "openai/gpt-6-astra": 0.03,
        "openai/gpt-5.6-sol": 0.005,
        "google/gemini-3.7-flash": 0.005,
        "deepseek/deepseek-v4.1-flash": 0.002,
    }

    async with httpx.AsyncClient(transport=_transport(responses, usage=usage)) as client:
        await answer_question(
            _deps(settings, client, db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    _, actual = await day_totals(db, _today())
    assert actual == pytest.approx(sum(usage.values()))


async def test_missing_cost_usd_falls_back_to_est_cost_usd(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    responses = {model_id: valid_verdict_json("B") for model_id in MODEL_IDS}
    usage = {
        "anthropic/claude-opus-5": None,
        "anthropic/claude-sonnet-5": 0.02,
        "openai/gpt-6-astra": 0.03,
        "openai/gpt-5.6-sol": 0.005,
        "google/gemini-3.7-flash": 0.005,
        "deepseek/deepseek-v4.1-flash": 0.002,
    }

    async with httpx.AsyncClient(transport=_transport(responses, usage=usage)) as client:
        await answer_question(
            _deps(settings, client, db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    _, actual = await day_totals(db, _today())
    opus_est_cost = next(m.est_cost_usd for m in MODELS if m.id == "anthropic/claude-opus-5")
    expected = opus_est_cost + sum(v for k, v in usage.items() if v is not None)
    assert actual == pytest.approx(expected)


async def test_reduced_round_persists_reduced_model_set_flag(
    settings: Settings, db: aiosqlite.Connection
) -> None:
    responses = {model_id: valid_verdict_json("B") for model_id in REDUCED_MODEL_IDS}
    reduced_settings = _with_cap(settings, 0.05)

    async with httpx.AsyncClient(transport=_transport(responses)) as client:
        await answer_question(
            Deps(settings=reduced_settings, roster=ROSTER, http=client, db=db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    cursor = await db.execute("SELECT reduced_model_set FROM questions ORDER BY id DESC LIMIT 1")
    row = await cursor.fetchone()
    assert row[0] == 1


async def test_rejected_round_still_reconciles_actual_spend(
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
    usage = {model_id: 0.01 for model_id in MODEL_IDS}

    async with httpx.AsyncClient(transport=_transport(responses, usage=usage)) as client:
        result = await answer_question(
            _deps(settings, client, db),
            _sharp_page_bytes(),
            source_is_photo=True,
            user_id=1,
            image_file_id="file123",
        )

    assert "doesn't look like an SAT" in result.as_kwargs()["text"]
    _, actual = await day_totals(db, _today())
    assert actual == pytest.approx(sum(usage.values()))
