import inspect

from bot.formatting import reply as reply_module
from bot.formatting.reply import build_rejection, build_reply
from bot.orchestrator.contract import ConsensusResult, ModelVote, Position, RejectionReason

_RESERVED_CHARS_REASON = (
    "This is _emphasis_ *bold* [link](url) ~tilde~ `code` >quote #tag +plus "
    "-minus =equals |pipe {brace} .period !bang and a bare \\ backslash."
)


def entity_text(text: str, entity: object) -> str:
    """Telegram entity offsets are UTF-16 code units; Python slices by code point."""
    buffer = text.encode("utf-16-le")
    start = entity.offset * 2  # type: ignore[attr-defined]
    end = (entity.offset + entity.length) * 2  # type: ignore[attr-defined]
    return buffer[start:end].decode("utf-16-le")


def make_consensus(
    tier: str,
    *,
    positions: list[Position],
    total_valid: int,
    winning_letter: str | None = None,
    abstentions: int = 0,
    labs_in_majority: int = 0,
    degraded: bool = False,
    model_votes: list[ModelVote] | None = None,
) -> ConsensusResult:
    if model_votes is None:
        model_votes = []
        index = 0
        for position in positions:
            for _ in range(position.votes):
                model_votes.append(
                    ModelVote(model_id=f"lab{index}/model-{index}", lab=f"lab{index}",
                              letter=position.letter)
                )
                index += 1
        for _ in range(abstentions):
            model_votes.append(
                ModelVote(model_id=f"lab{index}/model-{index}", lab=f"lab{index}", letter=None)
            )
            index += 1
    return ConsensusResult(
        tier=tier,
        winning_letter=winning_letter,
        positions=positions,
        model_votes=model_votes,
        total_valid=total_valid,
        abstentions=abstentions,
        labs_in_majority=labs_in_majority,
        degraded=degraded,
        transcription_divergence=False,
        question_type=None,
    )


def test_strong_six_six_header_exact() -> None:
    consensus = make_consensus(
        "strong",
        positions=[
            Position(letter="B", votes=6, labs=4, reasoning=["Supported by the passage."]),
        ],
        total_valid=6,
        winning_letter="B",
        labs_in_majority=4,
    )
    text = build_reply(consensus, source_is_photo=False).as_kwargs()["text"]
    assert text.splitlines()[0].startswith("📋 ")
    assert "Answer: B" in text
    assert "100% agreement" in text
    assert "(6/6 agree · 4 labs)" in text


def test_strong_five_one_header_exact() -> None:
    consensus = make_consensus(
        "strong",
        positions=[
            Position(letter="B", votes=5, labs=3, reasoning=["Supported by the passage."]),
            Position(letter="C", votes=1, labs=1, reasoning=["Plausible but unsupported."]),
        ],
        total_valid=6,
        winning_letter="B",
        labs_in_majority=3,
    )
    text = build_reply(consensus, source_is_photo=False).as_kwargs()["text"]
    assert "Answer: B" in text
    assert "83% agreement" in text
    assert "(5/6 agree · 3 labs)" in text


def test_contested_four_two_header_prefix() -> None:
    consensus = make_consensus(
        "contested",
        positions=[
            Position(letter="B", votes=4, labs=3, reasoning=["Supported by the passage."]),
            Position(letter="C", votes=2, labs=2, reasoning=["Plausible but unsupported."]),
        ],
        total_valid=6,
        winning_letter="B",
        labs_in_majority=3,
    )
    text = build_reply(consensus, source_is_photo=False).as_kwargs()["text"]
    assert "Answer: B" in text
    assert "Contested — 2 models said C" in text
    assert "(4/6 agree · 3 labs)" in text


def test_unresolved_three_three_header_and_teacher_line() -> None:
    consensus = make_consensus(
        "unresolved",
        positions=[
            Position(letter="B", votes=3, labs=2, reasoning=["Supported by the passage."]),
            Position(letter="C", votes=3, labs=2, reasoning=["Also plausible."]),
        ],
        total_valid=6,
        winning_letter=None,
        labs_in_majority=4,
    )
    text = build_reply(consensus, source_is_photo=False).as_kwargs()["text"]
    assert "Answer: unresolved" in text
    assert "worth asking a teacher" in text.lower()


def test_unresolved_produces_zero_spoiler_entities() -> None:
    consensus = make_consensus(
        "unresolved",
        positions=[
            Position(letter="B", votes=3, labs=2, reasoning=["Reason B."]),
            Position(letter="C", votes=3, labs=2, reasoning=["Reason C."]),
        ],
        total_valid=6,
        winning_letter=None,
    )
    result = build_reply(consensus, source_is_photo=False)
    entities = result.as_kwargs()["entities"]
    assert not [entity for entity in entities if entity.type == "spoiler"]


def test_unresolved_has_no_standalone_letter_line() -> None:
    consensus = make_consensus(
        "unresolved",
        positions=[
            Position(letter="B", votes=3, labs=2, reasoning=["Reason B."]),
            Position(letter="C", votes=3, labs=2, reasoning=["Reason C."]),
        ],
        total_valid=6,
        winning_letter=None,
    )
    text = build_reply(consensus, source_is_photo=False).as_kwargs()["text"]
    for line in text.splitlines():
        assert line.strip() not in ("B", "C")


def test_strong_states_answer_plainly_before_the_model_breakdown() -> None:
    consensus = make_consensus(
        "strong",
        positions=[Position(letter="B", votes=6, labs=4, reasoning=["Reason B."])],
        total_valid=6,
        winning_letter="B",
        labs_in_majority=4,
    )
    kwargs = build_reply(consensus, source_is_photo=False).as_kwargs()
    text = kwargs["text"]
    assert not [entity for entity in kwargs["entities"] if entity.type == "spoiler"]
    assert "Answer: B" in text
    assert text.index("Answer: B") < text.index("• ")


def test_contested_renders_both_sides_reasoning_before_the_breakdown() -> None:
    consensus = make_consensus(
        "contested",
        positions=[
            Position(letter="B", votes=4, labs=3, reasoning=["B side reasoning."]),
            Position(letter="C", votes=2, labs=2, reasoning=["C side reasoning."]),
        ],
        total_valid=6,
        winning_letter="B",
        labs_in_majority=3,
    )
    text = build_reply(consensus, source_is_photo=False).as_kwargs()["text"]
    first_bullet = text.index("• ")
    assert text.index("B side reasoning.") < first_bullet
    assert text.index("C side reasoning.") < first_bullet


def test_degraded_header_appends_abstention_note() -> None:
    consensus = make_consensus(
        "strong",
        positions=[Position(letter="B", votes=4, labs=3, reasoning=["Reason B."])],
        total_valid=4,
        winning_letter="B",
        labs_in_majority=3,
        abstentions=2,
        degraded=True,
    )
    text = build_reply(consensus, source_is_photo=False).as_kwargs()["text"]
    assert text.count("I couldn't generate an answer for that.") == 2
    assert "(4/6 agree · 3 labs)" in text


def test_insufficient_renders_apology_and_no_spoiler() -> None:
    consensus = make_consensus(
        "insufficient",
        positions=[],
        total_valid=2,
        winning_letter=None,
        abstentions=4,
    )
    result = build_reply(consensus, source_is_photo=False)
    kwargs = result.as_kwargs()
    assert "try again" in kwargs["text"].lower()
    assert not [e for e in kwargs["entities"] if e.type == "spoiler"]


def test_photo_source_appends_footer() -> None:
    consensus = make_consensus(
        "strong",
        positions=[Position(letter="B", votes=6, labs=4, reasoning=["Reason B."])],
        total_valid=6,
        winning_letter="B",
        labs_in_majority=4,
    )
    text = build_reply(consensus, source_is_photo=True).as_kwargs()["text"]
    assert "send it as a file instead of a photo" in text.lower()


def test_document_source_omits_footer() -> None:
    consensus = make_consensus(
        "strong",
        positions=[Position(letter="B", votes=6, labs=4, reasoning=["Reason B."])],
        total_valid=6,
        winning_letter="B",
        labs_in_majority=4,
    )
    text = build_reply(consensus, source_is_photo=False).as_kwargs()["text"]
    assert "send it as a file instead of a photo" not in text.lower()


def test_adversarial_reasoning_renders_without_raising() -> None:
    consensus = make_consensus(
        "strong",
        positions=[Position(letter="B", votes=6, labs=4, reasoning=[_RESERVED_CHARS_REASON])],
        total_valid=6,
        winning_letter="B",
        labs_in_majority=4,
    )
    result = build_reply(consensus, source_is_photo=False)
    text = result.as_kwargs()["text"]
    assert _RESERVED_CHARS_REASON in text


def test_no_correctness_claims_in_any_tier() -> None:
    strong = make_consensus(
        "strong",
        positions=[Position(letter="B", votes=6, labs=4, reasoning=["Reason B."])],
        total_valid=6,
        winning_letter="B",
        labs_in_majority=4,
    )
    unresolved = make_consensus(
        "unresolved",
        positions=[
            Position(letter="B", votes=3, labs=2, reasoning=["Reason B."]),
            Position(letter="C", votes=3, labs=2, reasoning=["Reason C."]),
        ],
        total_valid=6,
        winning_letter=None,
    )
    insufficient = make_consensus("insufficient", positions=[], total_valid=1, winning_letter=None)
    for consensus in (strong, unresolved, insufficient):
        text = build_reply(consensus, source_is_photo=False).as_kwargs()["text"].lower()
        assert "correct answer" not in text
        assert "the answer is" not in text
        assert "right answer" not in text


def test_rejection_multiple_questions_copy() -> None:
    result = build_rejection(RejectionReason.multiple_questions, source_is_photo=True)
    text = result.as_kwargs()["text"]
    assert "one question per image" in text


def test_module_source_has_no_forbidden_phrases() -> None:
    source = inspect.getsource(reply_module).lower()
    for phrase in ("correct answer", "the answer is", "right answer", "high confidence"):
        assert phrase not in source


def test_strong_body_capped_at_four_bulleted_lines() -> None:
    consensus = make_consensus(
        "strong",
        positions=[
            Position(
                letter="B",
                votes=6,
                labs=4,
                reasoning=[
                    "Reason one.",
                    "Reason two.",
                    "Reason three.",
                    "Reason four.",
                    "Reason five.",
                ],
            ),
        ],
        total_valid=6,
        winning_letter="B",
        labs_in_majority=4,
    )
    text = build_reply(consensus, source_is_photo=False).as_kwargs()["text"]
    for reason in ("Reason one.", "Reason two.", "Reason three.", "Reason four."):
        assert reason in text
    assert "Reason five." not in text
    bullet_lines = [line for line in text.splitlines() if line.startswith("• ")]
    assert len(bullet_lines) == 6
    assert all(": " in line for line in bullet_lines)


def test_contested_uses_bold_entities_for_position_labels() -> None:
    consensus = make_consensus(
        "contested",
        positions=[
            Position(letter="B", votes=4, labs=3, reasoning=["B side reasoning."]),
            Position(letter="C", votes=2, labs=2, reasoning=["C side reasoning."]),
        ],
        total_valid=6,
        winning_letter="B",
        labs_in_majority=3,
    )
    kwargs = build_reply(consensus, source_is_photo=False).as_kwargs()
    text = kwargs["text"]
    bold_entities = [e for e in kwargs["entities"] if e.type == "bold"]
    bold_texts = {entity_text(text, e) for e in bold_entities}
    assert "Answer: B" in bold_texts
    assert "Contested — 2 models said C" in bold_texts


def test_unresolved_uses_bold_entities_for_every_position_label() -> None:
    consensus = make_consensus(
        "unresolved",
        positions=[
            Position(letter="B", votes=3, labs=2, reasoning=["Reason B."]),
            Position(letter="C", votes=3, labs=2, reasoning=["Reason C."]),
        ],
        total_valid=6,
        winning_letter=None,
    )
    kwargs = build_reply(consensus, source_is_photo=False).as_kwargs()
    text = kwargs["text"]
    bold_entities = [e for e in kwargs["entities"] if e.type == "bold"]
    bold_texts = {entity_text(text, e) for e in bold_entities}
    assert "B — 3 models" in bold_texts
    assert "C — 3 models" in bold_texts


def test_insufficient_apology_exact_text() -> None:
    consensus = make_consensus(
        "insufficient",
        positions=[],
        total_valid=2,
        winning_letter=None,
        abstentions=4,
    )
    text = build_reply(consensus, source_is_photo=False).as_kwargs()["text"]
    assert text == (
        "Only 2 of 6 models answered in time, which isn't enough to report a consensus. "
        "Please try again."
    )
