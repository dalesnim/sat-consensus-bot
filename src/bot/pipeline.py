import logging
import time
from dataclasses import dataclass

import httpx
from aiogram.utils.formatting import Text

from bot.config import RosterConfig, Settings
from bot.formatting.reply import build_rejection, build_reply
from bot.images.extract import QualityGrade, grade_image, to_data_url
from bot.orchestrator.consensus import tally
from bot.orchestrator.contract import RejectionReason
from bot.orchestrator.fanout import run_round

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Deps:
    settings: Settings
    roster: RosterConfig
    http: httpx.AsyncClient


async def answer_question(deps: Deps, image_bytes: bytes, *, source_is_photo: bool) -> Text:
    if not image_bytes or len(image_bytes) > deps.settings.max_image_bytes:
        logger.warning("rejecting image on byte ceiling: bytes=%d", len(image_bytes))
        return build_rejection(RejectionReason.unreadable_image, source_is_photo=source_is_photo)

    try:
        report = grade_image(
            image_bytes,
            min_dimension=deps.settings.min_image_dimension,
            blur_warn=deps.settings.blur_variance_warn,
            blur_reject=deps.settings.blur_variance_reject,
        )
    except ValueError:
        logger.warning("rejecting undecodable image: bytes=%d", len(image_bytes))
        return build_rejection(RejectionReason.unreadable_image, source_is_photo=source_is_photo)

    if report.grade is QualityGrade.reject:
        logger.warning("rejecting low-quality image: reason=%s", report.reason)
        return build_rejection(RejectionReason.unreadable_image, source_is_photo=source_is_photo)

    if report.grade is QualityGrade.warn:
        logger.warning(
            "proceeding despite warn-grade image: reason=%s width=%d height=%d "
            "blur_variance=%.2f",
            report.reason,
            report.width,
            report.height,
            report.blur_variance,
        )

    try:
        data_url = to_data_url(image_bytes)
    except ValueError:
        logger.warning("rejecting image undecodable at data-url stage: bytes=%d", len(image_bytes))
        return build_rejection(RejectionReason.unreadable_image, source_is_photo=source_is_photo)

    started = time.monotonic()
    results = await run_round(
        deps.http,
        deps.roster,
        data_url,
        base_url=deps.settings.openrouter_base_url,
        api_key=deps.settings.openrouter_api_key,
        per_model_timeout=deps.settings.per_model_timeout_seconds,
        round_timeout=deps.settings.round_timeout_seconds,
    )

    voters = [r for r in results if r.status == "ok" and r.verdict is not None]
    if len(voters) >= deps.settings.min_valid_responses:
        not_verbal_votes = sum(1 for r in voters if r.verdict.is_sat_verbal is False)
        if not_verbal_votes > len(voters) / 2:
            return build_rejection(
                RejectionReason.not_sat_verbal, source_is_photo=source_is_photo
            )

        multi_question_votes = sum(1 for r in voters if r.verdict.question_count > 1)
        if multi_question_votes > len(voters) / 2:
            return build_rejection(
                RejectionReason.multiple_questions, source_is_photo=source_is_photo
            )

    consensus = tally(results, min_valid=deps.settings.min_valid_responses)
    logger.info(
        "round tallied: tier=%s has_winner=%s total_valid=%d abstentions=%d elapsed_s=%.2f",
        consensus.tier,
        consensus.winning_letter is not None,
        consensus.total_valid,
        consensus.abstentions,
        time.monotonic() - started,
    )
    return build_reply(consensus, source_is_photo=source_is_photo)
