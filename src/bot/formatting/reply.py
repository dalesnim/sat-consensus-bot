from aiogram.utils.formatting import Spoiler, Text

from bot.orchestrator.contract import ConsensusResult, Position, RejectionReason

_INSUFFICIENT_APOLOGY = (
    "Sorry, not enough models answered to report a consensus this time. Please try again."
)
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


def _header_line(consensus: ConsensusResult) -> str:
    positions = consensus.positions
    if consensus.tier == "strong":
        line = (
            f"{positions[0].votes}/{consensus.total_valid} agree · "
            f"{consensus.labs_in_majority} labs"
        )
    elif consensus.tier == "contested":
        line = (
            f"{positions[0].votes}/{positions[1].votes} majority contested · "
            f"{consensus.labs_in_majority} labs"
        )
    else:
        line = f"{positions[0].votes}/{positions[1].votes} unresolved · no consensus"

    if consensus.degraded:
        line += f" · {consensus.abstentions} models did not answer"
    return line


def _labelled_reasoning(position: Position) -> list[str]:
    return [f"{position.letter}:", *position.reasoning]


def build_reply(consensus: ConsensusResult, *, source_is_photo: bool) -> Text:
    if consensus.tier == "insufficient":
        return Text(_INSUFFICIENT_APOLOGY)

    positions = consensus.positions
    lines: list[str] = [_header_line(consensus)]

    if consensus.tier == "strong":
        lines.append("")
        lines.extend(positions[0].reasoning)
    elif consensus.tier == "contested":
        lines.append("")
        lines.extend(_labelled_reasoning(positions[0]))
        lines.append("")
        lines.extend(_labelled_reasoning(positions[1]))
    elif consensus.tier == "unresolved":
        for position in positions:
            lines.append("")
            lines.extend(_labelled_reasoning(position))
        lines.append("")
        lines.append(_TEACHER_LINE)

    if source_is_photo:
        lines.append("")
        lines.append(_PHOTO_TIP)

    body = "\n".join(lines)

    if consensus.tier in ("strong", "contested"):
        return Text(body, "\n", Spoiler(consensus.winning_letter))
    return Text(body)


def build_rejection(reason: RejectionReason, *, source_is_photo: bool) -> Text:
    return Text(_REJECTION_COPY[reason])
