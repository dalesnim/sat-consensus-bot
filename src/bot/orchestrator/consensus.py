import logging
from collections import Counter
from collections.abc import Sequence

from bot.orchestrator.contract import (
    AttemptResult,
    ConsensusResult,
    ConsensusTier,
    ModelVote,
    Position,
    QuestionType,
)

logger = logging.getLogger(__name__)

MIN_VALID_RESPONSES_DEFAULT = 3

_DIVERGENCE_THRESHOLD = 0.9


def _normalize_tokens(text: str) -> set[str]:
    cleaned = "".join(char if char.isalnum() or char.isspace() else " " for char in text.lower())
    return {token for token in cleaned.split() if token}


def _jaccard(tokens_a: set[str], tokens_b: set[str]) -> float:
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    union = len(tokens_a | tokens_b)
    if union == 0:
        return 1.0
    return len(tokens_a & tokens_b) / union


def _transcription_divergence(ok_results: Sequence[AttemptResult]) -> bool:
    token_sets = [
        (result, _normalize_tokens(result.verdict.passage_transcription))
        for result in ok_results
        if result.verdict is not None
    ]
    for i in range(len(token_sets)):
        result_a, tokens_a = token_sets[i]
        for j in range(i + 1, len(token_sets)):
            result_b, tokens_b = token_sets[j]
            if result_a.lab == result_b.lab:
                continue
            score = _jaccard(tokens_a, tokens_b)
            if score < _DIVERGENCE_THRESHOLD:
                logger.warning(
                    "Transcription divergence between %s and %s: overlap %.3f",
                    result_a.model_id,
                    result_b.model_id,
                    score,
                )
                return True
    return False


def _selected_reason(result: AttemptResult) -> str | None:
    if result.verdict is None:
        return None
    for choice in result.verdict.eliminations:
        if choice.verdict == "selected":
            return choice.reason
    return None


def _modal_question_type(ok_results: Sequence[AttemptResult]) -> QuestionType | None:
    counts: Counter[QuestionType] = Counter(
        result.verdict.question_type
        for result in ok_results
        if result.verdict is not None and result.verdict.question_type is not None
    )
    if not counts:
        return None
    ranked = counts.most_common()
    top_count = ranked[0][1]
    tied = [question_type for question_type, count in ranked if count == top_count]
    if len(tied) > 1:
        return None
    return ranked[0][0]


def _model_votes(results: Sequence[AttemptResult]) -> list[ModelVote]:
    votes: list[ModelVote] = []
    for result in results:
        letter = None
        if result.status == "ok" and result.verdict is not None:
            letter = result.verdict.answer
        votes.append(ModelVote(model_id=result.model_id, lab=result.lab, letter=letter))
    return votes


def tally(
    results: Sequence[AttemptResult], *, min_valid: int = MIN_VALID_RESPONSES_DEFAULT
) -> ConsensusResult:
    ok_results = [result for result in results if result.status == "ok"]
    abstain_results = [result for result in results if result.status == "abstain"]
    abstentions = len(abstain_results)
    total_valid = len(ok_results)
    degraded = abstentions >= 2

    if total_valid < min_valid:
        return ConsensusResult(
            tier="insufficient",
            winning_letter=None,
            positions=[],
            model_votes=_model_votes(results),
            total_valid=total_valid,
            abstentions=abstentions,
            labs_in_majority=0,
            degraded=degraded,
            transcription_divergence=False,
            question_type=None,
        )

    voters_by_letter: dict[str, list[AttemptResult]] = {}
    for result in ok_results:
        if result.verdict is None or result.verdict.answer is None:
            continue
        voters_by_letter.setdefault(result.verdict.answer, []).append(result)

    positions: list[Position] = []
    for letter, voters in voters_by_letter.items():
        labs = len({voter.lab for voter in voters})
        reasoning: list[str] = []
        seen_lower: set[str] = set()
        for voter in voters:
            reason = _selected_reason(voter)
            if reason is None:
                continue
            key = reason.strip().lower()
            if key in seen_lower:
                continue
            seen_lower.add(key)
            reasoning.append(reason)
        positions.append(Position(letter=letter, votes=len(voters), labs=labs, reasoning=reasoning))

    positions.sort(key=lambda position: (-position.votes, position.letter))

    tier: ConsensusTier
    winning_letter: str | None

    if not positions:
        tier = "unresolved"
        winning_letter = None
    else:
        top = positions[0]
        tie_at_top = len(positions) > 1 and positions[1].votes == top.votes
        if tie_at_top:
            tier = "unresolved"
            winning_letter = None
        elif top.votes == total_valid or top.votes / total_valid >= 5 / 6:
            tier = "strong"
            winning_letter = top.letter
        elif top.votes > total_valid / 2:
            tier = "contested"
            winning_letter = top.letter
        else:
            tier = "unresolved"
            winning_letter = None

    if winning_letter is not None:
        labs_in_majority = positions[0].labs
    else:
        labs_in_majority = len({result.lab for result in ok_results})

    return ConsensusResult(
        tier=tier,
        winning_letter=winning_letter,
        positions=positions,
        model_votes=_model_votes(results),
        total_valid=total_valid,
        abstentions=abstentions,
        labs_in_majority=labs_in_majority,
        degraded=degraded,
        transcription_divergence=_transcription_divergence(ok_results),
        question_type=_modal_question_type(ok_results),
    )
