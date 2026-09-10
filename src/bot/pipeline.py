from aiogram.utils.formatting import Text

from bot.formatting.reply import build_reply
from bot.orchestrator.contract import ConsensusResult, Position

_STUB_CONSENSUS = ConsensusResult(
    tier="strong",
    winning_letter="B",
    positions=[
        Position(
            letter="B",
            votes=4,
            labs=4,
            reasoning=[
                "A is eliminated: the passage never supports this claim.",
                "C is eliminated: contradicted by the second sentence.",
                "D is eliminated: too broad for what the passage states.",
                "B is supported directly by the passage's central claim.",
            ],
        )
    ],
    total_valid=6,
    abstentions=0,
    labs_in_majority=4,
    degraded=False,
    transcription_divergence=False,
    question_type=None,
)


async def answer_question(image_bytes: bytes, *, source_is_photo: bool) -> Text:
    """Stub for plan 01: hardcoded consensus. Plan 06 replaces this with the live round."""
    return build_reply(_STUB_CONSENSUS, source_is_photo=source_is_photo)
