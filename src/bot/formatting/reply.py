from aiogram.utils.formatting import Bold, Italic, Text

from bot.orchestrator.contract import (
    ConsensusResult,
    ModelVote,
    Position,
    QuestionType,
    RejectionReason,
)

_REASONING_CAP = 4
_PHOTO_TIP = (
    "Tip: send it as a file instead of a photo — Telegram compresses photos and that costs "
    "accuracy."
)
_TEACHER_LINE = "The models don't agree here — worth asking a teacher about."
_NO_ANSWER = "I couldn't generate an answer for that."

_QUESTION_TYPE_LABELS: dict[QuestionType, str] = {
    QuestionType.central_ideas_details: "central ideas and details",
    QuestionType.command_of_evidence_textual: "command of evidence (textual)",
    QuestionType.command_of_evidence_quantitative: "command of evidence (quantitative)",
    QuestionType.inferences: "inferences",
    QuestionType.words_in_context: "words in context",
    QuestionType.text_structure_purpose: "text structure and purpose",
    QuestionType.cross_text_connections: "cross-text connections",
    QuestionType.rhetorical_synthesis: "rhetorical synthesis",
    QuestionType.transitions: "transitions",
    QuestionType.boundaries: "boundaries",
    QuestionType.form_structure_sense: "form, structure, and sense",
}

_REJECTION_COPY: dict[RejectionReason, str] = {
    RejectionReason.unreadable_image: (
        "I can't read this clearly. Try sending it as a file instead of a photo."
    ),
    RejectionReason.not_sat_verbal: "That doesn't look like an SAT Reading & Writing question.",
    RejectionReason.multiple_questions: (
        "I see more than one question here. Send one question per image."
    ),
    RejectionReason.no_image: (
        "Send me a photo or an image file of one SAT Reading & Writing question."
    ),
}


def _insufficient_apology(total_valid: int) -> str:
    return (
        f"Only {total_valid} of 6 models answered in time, which isn't enough to report a "
        "consensus. Please try again."
    )


def _topic_line(consensus: ConsensusResult) -> str:
    if consensus.question_type is None:
        return "📋 SAT Reading & Writing"
    return f"📋 {_QUESTION_TYPE_LABELS[consensus.question_type]}"


def _agreement_percent(consensus: ConsensusResult) -> int:
    total = consensus.total_valid + consensus.abstentions
    if total == 0 or not consensus.positions:
        return 0
    return round(consensus.positions[0].votes / total * 100)


def _vote_line(vote: ModelVote) -> str:
    return f"• {vote.model_id}: {vote.letter or _NO_ANSWER}"


def _breakdown(consensus: ConsensusResult) -> list[str]:
    return [_vote_line(vote) for vote in consensus.model_votes]


def _tally_footer(consensus: ConsensusResult) -> str:
    total = consensus.total_valid + consensus.abstentions
    top = consensus.positions[0].votes if consensus.positions else 0
    footer = f"({top}/{total} agree · {consensus.labs_in_majority} labs)"
    if consensus.transcription_divergence:
        footer += " · models read the image differently — check it's legible"
    return footer


def _prose(reasoning: list[str], *, cap: int | None = None) -> str:
    lines = reasoning[:cap] if cap else reasoning
    return "\n".join(lines)


def _plural_models(count: int) -> str:
    return "1 model" if count == 1 else f"{count} models"


def _position_block(position: Position) -> list[str | Bold]:
    return [
        Bold(f"{position.letter} — {_plural_models(position.votes)}"),
        "\n",
        _prose(position.reasoning),
    ]


def build_reply(consensus: ConsensusResult, *, source_is_photo: bool) -> Text:
    if consensus.tier == "insufficient":
        return Text(_insufficient_apology(consensus.total_valid))

    nodes: list[str | Bold | Italic] = [Bold(_topic_line(consensus)), "\n\n"]

    if consensus.winning_letter is not None:
        nodes.append(Bold(f"Answer: {consensus.winning_letter}"))
        nodes.append("\n\n")
        nodes.append(f"{_agreement_percent(consensus)}% agreement")
        nodes.append("\n\n")
        nodes.append(_prose(consensus.positions[0].reasoning, cap=_REASONING_CAP))
        if consensus.tier == "contested" and len(consensus.positions) > 1:
            runner_up = consensus.positions[1]
            nodes.append("\n\n")
            nodes.append(
                Bold(f"Contested — {_plural_models(runner_up.votes)} said {runner_up.letter}")
            )
            nodes.append("\n")
            nodes.append(_prose(runner_up.reasoning, cap=_REASONING_CAP))
    else:
        nodes.append(Bold("Answer: unresolved"))
        for position in consensus.positions:
            nodes.append("\n\n")
            nodes.extend(_position_block(position))
        nodes.append("\n\n")
        nodes.append(_TEACHER_LINE)

    nodes.append("\n\n")
    nodes.append("\n".join(_breakdown(consensus)))
    nodes.append("\n")
    nodes.append(Italic(_tally_footer(consensus)))

    if source_is_photo:
        nodes.append("\n\n")
        nodes.append(_PHOTO_TIP)

    return Text(*nodes)


def build_rejection(reason: RejectionReason, *, source_is_photo: bool) -> Text:
    return Text(_REJECTION_COPY[reason])
