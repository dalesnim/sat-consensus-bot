from aiogram.utils.formatting import Bold, Spoiler, Text

from bot.orchestrator.contract import ConsensusResult, Position, RejectionReason

_STRONG_REASONING_CAP = 4
_PHOTO_TIP = (
    "Tip: send it as a file instead of a photo — Telegram compresses photos and that costs "
    "accuracy."
)
_TEACHER_LINE = "Worth asking a teacher about."

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


def _header_line(consensus: ConsensusResult) -> str:
    positions = consensus.positions
    if consensus.tier == "strong":
        top = positions[0].votes if positions else 0
        line = f"{top}/{consensus.total_valid} agree · {consensus.labs_in_majority} labs"
    elif consensus.tier == "contested":
        line = (
            f"{positions[0].votes}/{positions[1].votes} majority contested · "
            f"{consensus.labs_in_majority} labs"
        )
    else:
        top = positions[0].votes if positions else 0
        runner_up = positions[1].votes if len(positions) > 1 else 0
        line = f"{top}/{runner_up} unresolved · no consensus"

    if consensus.degraded:
        line += f" · {consensus.abstentions} models did not answer"
    return line


def _bulleted_lines(reasoning: list[str], *, cap: int | None = None) -> str:
    lines = reasoning[:cap] if cap else reasoning
    return "\n".join(f"• {line}" for line in lines)


def _position_block(position: Position) -> list[str | Bold]:
    return [
        Bold(f"{position.letter} — {position.votes} models"),
        "\n",
        _bulleted_lines(position.reasoning),
    ]


def build_reply(consensus: ConsensusResult, *, source_is_photo: bool) -> Text:
    if consensus.tier == "insufficient":
        return Text(_insufficient_apology(consensus.total_valid))

    positions = consensus.positions
    nodes: list[str | Bold | Spoiler] = [_header_line(consensus)]

    if consensus.tier == "strong":
        nodes.append("\n\n")
        nodes.append(_bulleted_lines(positions[0].reasoning, cap=_STRONG_REASONING_CAP))
    elif consensus.tier == "contested":
        nodes.append("\n\n")
        nodes.extend(_position_block(positions[0]))
        nodes.append("\n\n")
        nodes.extend(_position_block(positions[1]))
    else:  # unresolved
        for position in positions:
            nodes.append("\n\n")
            nodes.extend(_position_block(position))
        nodes.append("\n\n")
        nodes.append(_TEACHER_LINE)

    if source_is_photo:
        nodes.append("\n\n")
        nodes.append(_PHOTO_TIP)

    if consensus.tier in ("strong", "contested"):
        nodes.append("\n\n")
        nodes.append(Spoiler(consensus.winning_letter))

    return Text(*nodes)


def build_rejection(reason: RejectionReason, *, source_is_photo: bool) -> Text:
    return Text(_REJECTION_COPY[reason])
