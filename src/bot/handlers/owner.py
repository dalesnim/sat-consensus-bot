import logging
from datetime import UTC, datetime

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.utils.formatting import Bold, Text

from bot.cost.report import CostReport, build_cost_report
from bot.db.users import add_user
from bot.pipeline import Deps
from bot.runtime_state import is_paused, set_paused

logger = logging.getLogger(__name__)

router = Router()

_USAGE_TEXT = "Usage: /adduser <telegram_id>"
_REFUSAL_TEXT = (
    "This bot is invite-only. If you've paid for access, message the owner with your "
    "Telegram ID and they'll add you."
)


async def _send(message: Message, content: str | Text) -> None:
    text_obj = content if isinstance(content, Text) else Text(content)
    kwargs = text_obj.as_kwargs()
    try:
        await message.answer(**kwargs)
    except TelegramBadRequest:
        logger.error("owner reply failed to send, falling back to plain text")
        await message.answer(text=kwargs["text"])


@router.message(Command("adduser"))
async def handle_adduser(message: Message, command: CommandObject, deps: Deps) -> None:
    if deps.settings.owner_id is None:
        logger.critical("OWNER_ID is unset; /adduser is disabled for everyone")
        await _send(message, _REFUSAL_TEXT)
        return

    if message.from_user is None or message.from_user.id != deps.settings.owner_id:
        await _send(message, _REFUSAL_TEXT)
        return

    if command.args is None:
        await _send(message, _USAGE_TEXT)
        return

    try:
        telegram_id = int(command.args.strip())
    except ValueError:
        await _send(message, _USAGE_TEXT)
        return

    created = await add_user(deps.db, telegram_id)
    if created:
        await _send(message, f"Added {telegram_id}. They can start sending questions now.")
    else:
        await _send(message, f"{telegram_id} already has access.")


def _is_owner(message: Message, deps: Deps) -> bool:
    if deps.settings.owner_id is None:
        logger.critical("OWNER_ID is unset; owner commands are disabled for everyone")
        return False
    return message.from_user is not None and message.from_user.id == deps.settings.owner_id


@router.message(Command("pause"))
async def handle_pause(message: Message, deps: Deps) -> None:
    if not _is_owner(message, deps):
        await _send(message, _REFUSAL_TEXT)
        return
    set_paused(True)
    logger.warning("owner paused the bot")
    await _send(message, "Paused. Questions are refused until you send /resume.")


@router.message(Command("resume"))
async def handle_resume(message: Message, deps: Deps) -> None:
    if not _is_owner(message, deps):
        await _send(message, _REFUSAL_TEXT)
        return
    set_paused(False)
    logger.warning("owner resumed the bot")
    await _send(message, "Resumed. Send a question whenever you're ready.")


@router.message(Command("status"))
async def handle_status(message: Message, deps: Deps) -> None:
    if not _is_owner(message, deps):
        await _send(message, _REFUSAL_TEXT)
        return
    state = "PAUSED" if is_paused() else "RUNNING"
    models = len(deps.roster.models)
    tiebreak = deps.roster.tiebreak_model.id if deps.roster.tiebreak_model else "none"
    await _send(
        message,
        f"{state}\n{models} models in the round\ntiebreak: {tiebreak}",
    )


def _cost_report_nodes(report: CostReport) -> list[str | Bold]:
    nodes: list[str | Bold] = [
        Bold(f"Today (UTC {report.day})"),
        "\n",
        f"${report.spend_today:.4f} spent of ${report.cap_usd:.4f} cap",
    ]
    if report.reserved_today > report.spend_today:
        nodes.append(f", ${report.reserved_today:.4f} reserved")
    nodes.extend(
        [
            "\n\n",
            Bold("Last 7 days"),
            "\n",
            f"${report.spend_week:.4f}",
            "\n\n",
            Bold("Questions today"),
            "\n",
            f"{report.questions_today} asked, {report.cache_hits_today} from cache "
            f"({report.cache_hit_rate_today:.1f}%)",
        ]
    )
    if report.reduced_rounds_today:
        nodes.append(f", {report.reduced_rounds_today} on the reduced set")
    nodes.extend(
        [
            "\n\n",
            Bold("Cost per question"),
            "\n",
            f"${report.cost_per_question_today:.4f} today, "
            f"${report.cost_per_question_all_time:.4f} all time",
            "\n\n",
            "Daily figures reset at 00:00 UTC.",
        ]
    )
    return nodes


@router.message(Command("cost"))
async def handle_cost(message: Message, deps: Deps) -> None:
    if not _is_owner(message, deps):
        await _send(message, _REFUSAL_TEXT)
        return
    report = await build_cost_report(
        deps.db, cap_usd=deps.settings.daily_spend_cap_usd, now=datetime.now(UTC)
    )
    await _send(message, Text(*_cost_report_nodes(report)))
