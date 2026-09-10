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
