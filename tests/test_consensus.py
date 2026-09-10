import inspect

from bot.orchestrator.consensus import MIN_VALID_RESPONSES_DEFAULT, tally
from bot.orchestrator.contract import AttemptResult, Choices, ChoiceVerdict, Verdict


def make_ok(
    model_id: str,
    lab: str,
    answer: str,
    reason: str = "Supported directly by the passage.",
    transcription: str = "The passage discusses a historical event in detail.",
    question_type: str = "central_ideas_details",
) -> AttemptResult:
    eliminations = [
        ChoiceVerdict(
            choice=letter,
            verdict="selected" if letter == answer else "eliminated",
            reason=reason if letter == answer else f"{letter} is not supported by the passage.",
        )
        for letter in ("A", "B", "C", "D")
    ]
    verdict = Verdict(
        is_sat_verbal=True,
        question_count=1,
        question_type=question_type,
        passage_transcription=transcription,
        choice_transcriptions=Choices(A="a", B="b", C="c", D="d"),
        eliminations=eliminations,
        answer=answer,
    )
    return AttemptResult.ok(model_id, lab, verdict, 1.5)


def make_abstain(model_id: str, lab: str, reason: str = "timeout") -> AttemptResult:
    return AttemptResult.abstain(model_id, lab, reason, 22.0)


def test_six_agree_is_strong() -> None:
    results = [
        make_ok("m1", "anthropic", "B"),
        make_ok("m2", "anthropic", "B"),
        make_ok("m3", "openai", "B"),
        make_ok("m4", "openai", "B"),
        make_ok("m5", "google", "B"),
        make_ok("m6", "deepseek", "B"),
    ]
    result = tally(results)
    assert result.tier == "strong"
    assert result.winning_letter == "B"
    assert len(result.positions) == 1
    assert result.labs_in_majority == 4
    assert result.degraded is False


def test_five_one_is_strong_sorted_descending() -> None:
    results = [
        make_ok("m1", "anthropic", "B"),
        make_ok("m2", "anthropic", "B"),
        make_ok("m3", "openai", "B"),
        make_ok("m4", "openai", "B"),
        make_ok("m5", "google", "B"),
        make_ok("m6", "deepseek", "C"),
    ]
    result = tally(results)
    assert result.tier == "strong"
    assert result.winning_letter == "B"
    assert len(result.positions) == 2
    assert result.positions[0].votes >= result.positions[1].votes


def test_four_two_is_contested() -> None:
    results = [
        make_ok("m1", "anthropic", "B"),
        make_ok("m2", "anthropic", "B"),
        make_ok("m3", "openai", "B"),
        make_ok("m4", "openai", "B"),
        make_ok("m5", "google", "C"),
        make_ok("m6", "deepseek", "C"),
    ]
    result = tally(results)
    assert result.tier == "contested"
    assert result.winning_letter == "B"


def test_three_three_is_unresolved_with_no_winner() -> None:
    results = [
        make_ok("m1", "anthropic", "B"),
        make_ok("m2", "anthropic", "B"),
        make_ok("m3", "openai", "B"),
        make_ok("m4", "openai", "C"),
        make_ok("m5", "google", "C"),
        make_ok("m6", "deepseek", "C"),
    ]
    result = tally(results)
    assert result.tier == "unresolved"
    assert result.winning_letter is None
    assert len(result.positions) == 2


def test_two_two_one_one_is_unresolved_four_positions() -> None:
    results = [
        make_ok("m1", "anthropic", "A"),
        make_ok("m2", "openai", "A"),
        make_ok("m3", "google", "B"),
        make_ok("m4", "deepseek", "B"),
        make_ok("m5", "anthropic", "C"),
        make_ok("m6", "openai", "D"),
    ]
    result = tally(results)
    assert result.tier == "unresolved"
    assert result.winning_letter is None
    assert len(result.positions) == 4


def test_four_ok_two_abstain_is_degraded() -> None:
    results = [
        make_ok("m1", "anthropic", "B"),
        make_ok("m2", "openai", "B"),
        make_ok("m3", "google", "B"),
        make_ok("m4", "deepseek", "B"),
        make_abstain("m5", "anthropic"),
        make_abstain("m6", "openai"),
    ]
    result = tally(results)
    assert result.abstentions == 2
    assert result.degraded is True
    assert result.total_valid == 4


def test_one_ok_five_abstain_is_insufficient() -> None:
    results = [
        make_ok("m1", "anthropic", "B"),
        make_abstain("m2", "openai"),
        make_abstain("m3", "google"),
        make_abstain("m4", "deepseek"),
        make_abstain("m5", "anthropic"),
        make_abstain("m6", "openai"),
    ]
    result = tally(results)
    assert result.tier == "insufficient"
    assert result.winning_letter is None
    assert result.positions == []


def test_two_ok_agreeing_four_abstain_is_insufficient_below_floor() -> None:
    results = [
        make_ok("m1", "anthropic", "B"),
        make_ok("m2", "openai", "B"),
        make_abstain("m3", "google"),
        make_abstain("m4", "deepseek"),
        make_abstain("m5", "anthropic"),
        make_abstain("m6", "openai"),
    ]
    result = tally(results)
    assert result.tier == "insufficient"


def test_three_ok_agreeing_three_abstain_is_strong_and_degraded() -> None:
    results = [
        make_ok("m1", "anthropic", "B"),
        make_ok("m2", "openai", "B"),
        make_ok("m3", "google", "B"),
        make_abstain("m4", "deepseek"),
        make_abstain("m5", "anthropic"),
        make_abstain("m6", "openai"),
    ]
    result = tally(results)
    assert result.tier == "strong"
    assert result.degraded is True


def test_labs_in_majority_counts_distinct_labs_among_winners_only() -> None:
    results = [
        make_ok("m1", "anthropic", "B"),
        make_ok("m2", "anthropic", "B"),
        make_ok("m3", "openai", "B"),
        make_ok("m4", "openai", "B"),
        make_ok("m5", "google", "B"),
    ]
    result = tally(results)
    assert result.labs_in_majority == 3


def test_position_reasoning_is_deduplicated_and_order_stable() -> None:
    results = [
        make_ok("m1", "anthropic", "B", reason="Supported by paragraph two."),
        make_ok("m2", "openai", "B", reason="supported by paragraph two."),
        make_ok("m3", "google", "B", reason="The main claim aligns with choice B."),
    ]
    result = tally(results)
    reasoning = result.positions[0].reasoning
    assert reasoning == [
        "Supported by paragraph two.",
        "The main claim aligns with choice B.",
    ]


def test_transcription_divergence_true_below_threshold() -> None:
    results = [
        make_ok(
            "m1",
            "anthropic",
            "B",
            transcription="The quick brown fox jumps over the lazy dog near the river bank.",
        ),
        make_ok(
            "m2",
            "openai",
            "B",
            transcription="A completely different passage about volcanic rock formations entirely.",
        ),
        make_ok(
            "m3",
            "google",
            "B",
            transcription="The quick brown fox jumps over the lazy dog near the river bank.",
        ),
    ]
    result = tally(results)
    assert result.transcription_divergence is True


def test_transcription_divergence_false_when_identical() -> None:
    same = "The passage discusses a historical event in careful, verbatim detail throughout."
    results = [
        make_ok("m1", "anthropic", "B", transcription=same),
        make_ok("m2", "openai", "B", transcription=same),
        make_ok("m3", "google", "B", transcription=same),
    ]
    result = tally(results)
    assert result.transcription_divergence is False


def test_question_type_is_modal() -> None:
    results = [
        make_ok("m1", "anthropic", "B", question_type="inferences"),
        make_ok("m2", "openai", "B", question_type="inferences"),
        make_ok("m3", "google", "B", question_type="words_in_context"),
    ]
    result = tally(results)
    assert result.question_type == "inferences"


def test_question_type_is_none_on_tie() -> None:
    results = [
        make_ok("m1", "anthropic", "B", question_type="inferences"),
        make_ok("m2", "openai", "B", question_type="words_in_context"),
        make_ok("m3", "google", "B", question_type="central_ideas_details"),
    ]
    result = tally(results)
    assert result.question_type is None


def test_three_three_never_produces_winning_letter() -> None:
    results = [
        make_ok("m1", "anthropic", "A"),
        make_ok("m2", "openai", "A"),
        make_ok("m3", "google", "A"),
        make_ok("m4", "deepseek", "B"),
        make_ok("m5", "anthropic", "B"),
        make_ok("m6", "openai", "B"),
    ]
    result = tally(results)
    assert result.winning_letter is None


def test_min_valid_default_is_three() -> None:
    assert MIN_VALID_RESPONSES_DEFAULT == 3


def test_module_has_no_forbidden_imports() -> None:
    import bot.orchestrator.consensus as consensus_module

    source = inspect.getsource(consensus_module)
    assert "import httpx" not in source
    assert "from aiogram" not in source
    assert "from bot.config" not in source
