from bot.formatting.reply import build_rejection
from bot.orchestrator.contract import RejectionReason
from bot.pipeline import answer_question


async def test_photo_produces_consensus_reply(sample_image_bytes: bytes) -> None:
    result = await answer_question(sample_image_bytes, source_is_photo=True)
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


async def test_document_reply_omits_photo_tip(sample_image_bytes: bytes) -> None:
    result = await answer_question(sample_image_bytes, source_is_photo=False)
    text = result.as_kwargs()["text"]
    assert "send it as a file" not in text.lower()


async def test_multiple_questions_rejection_copy() -> None:
    result = build_rejection(RejectionReason.multiple_questions, source_is_photo=True)
    text = result.as_kwargs()["text"]
    assert "one question per image" in text
