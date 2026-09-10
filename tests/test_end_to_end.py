import httpx
from pydantic import SecretStr

from bot.config import ModelConfig, RosterConfig, Settings
from bot.formatting.reply import build_rejection
from bot.orchestrator.contract import RejectionReason
from bot.pipeline import Deps, answer_question
from tests.fixtures.verdicts import valid_verdict_json
from tests.test_images import _sharp_page_bytes

MODELS = [
    ModelConfig(id="anthropic/claude-opus-5", lab="anthropic", reasoning="omit"),
    ModelConfig(id="anthropic/claude-sonnet-5", lab="anthropic", reasoning="omit"),
    ModelConfig(id="openai/gpt-6-astra", lab="openai", reasoning="none"),
    ModelConfig(id="openai/gpt-5.6-sol", lab="openai", reasoning="none"),
    ModelConfig(id="google/gemini-3.7-flash", lab="google", reasoning="none"),
    ModelConfig(id="deepseek/deepseek-v4.1-flash", lab="deepseek", reasoning="minimal"),
]
ROSTER = RosterConfig(models=MODELS, min_distinct_labs=4, max_tokens=2000)


def _settings() -> Settings:
    return Settings(
        telegram_bot_token=SecretStr("test-telegram-token"),
        openrouter_api_key=SecretStr("test-openrouter-key"),
    )


def _agreeing_transport(answer: str = "B") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": valid_verdict_json(answer)}}]},
        )

    return httpx.MockTransport(handler)


async def test_photo_produces_consensus_reply() -> None:
    async with httpx.AsyncClient(transport=_agreeing_transport()) as client:
        deps = Deps(settings=_settings(), roster=ROSTER, http=client)
        result = await answer_question(deps, _sharp_page_bytes(), source_is_photo=True)

    kwargs = result.as_kwargs()
    text = kwargs["text"]
    entities = kwargs["entities"]

    assert "agree" in text or "contested" in text or "unresolved" in text

    spoilers = [entity for entity in entities if entity.type == "spoiler"]
    assert len(spoilers) == 1

    spoiler = spoilers[0]
    letter = text[spoiler.offset : spoiler.offset + spoiler.length]
    assert letter in ("A", "B", "C", "D")
    assert spoiler.offset + spoiler.length == len(text)

    lowered = text.lower()
    assert "correct answer" not in lowered
    assert "the answer is" not in lowered


async def test_document_reply_omits_photo_tip() -> None:
    async with httpx.AsyncClient(transport=_agreeing_transport()) as client:
        deps = Deps(settings=_settings(), roster=ROSTER, http=client)
        result = await answer_question(deps, _sharp_page_bytes(), source_is_photo=False)

    text = result.as_kwargs()["text"]
    assert "send it as a file" not in text.lower()


async def test_multiple_questions_rejection_copy() -> None:
    result = build_rejection(RejectionReason.multiple_questions, source_is_photo=True)
    text = result.as_kwargs()["text"]
    assert "one question per image" in text


async def test_six_model_round_produces_exact_agreement_header() -> None:
    async with httpx.AsyncClient(transport=_agreeing_transport()) as client:
        deps = Deps(settings=_settings(), roster=ROSTER, http=client)
        result = await answer_question(deps, _sharp_page_bytes(), source_is_photo=True)

    text = result.as_kwargs()["text"]
    assert text.startswith("6/6 agree · 4 labs")
