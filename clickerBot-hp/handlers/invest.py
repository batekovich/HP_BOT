import asyncio
import random
import time
from html import escape

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from basic_utils import STR, format_with_names, human_time_left
from config import (
    INVEST_GROWTH_MAX,
    INVEST_GROWTH_MIN,
    INVEST_LOSE_CHANCE,
    INVEST_MAX_HOURS,
    INVEST_MIN_HOURS,
    INVEST_WATCH_INTERVAL,
)
from database import (
    add_chat,
    complete_investment,
    create_investment,
    get_active_investments,
    get_finished_investments,
    touch_user,
)


router = Router(name="investments")


@router.message(Command("invest"))
async def invest_cmd(msg: Message) -> None:
    if msg.chat.type in {"group", "supergroup"}:
        add_chat(msg.chat.id)

    parts = (msg.text or "").split()
    if len(parts) != 3:
        await msg.reply(STR("invest_usage"))
        return
    try:
        amount = int(parts[1])
        hours = int(parts[2])
    except ValueError:
        await msg.reply(STR("invest_usage"))
        return

    if amount <= 0:
        await msg.reply(STR("invest_positive_amount"))
        return
    if hours < INVEST_MIN_HOURS or hours > INVEST_MAX_HOURS:
        await msg.reply(
            STR("invest_hours_range").format(
                min_h=INVEST_MIN_HOURS,
                max_h=INVEST_MAX_HOURS,
            )
        )
        return

    user_id, name = msg.from_user.id, msg.from_user.full_name
    touch_user(user_id, name, msg.chat.id)
    if not create_investment(user_id, name, msg.chat.id, amount, hours):
        await msg.reply(format_with_names(STR("invest_not_enough")))
        return

    await msg.reply(
        format_with_names(
            STR("invest_created"), name=escape(name), amount=amount, hours=hours
        )
    )


@router.message(Command("invest_status"))
async def invest_status(msg: Message) -> None:
    data = get_active_investments(msg.from_user.id)
    if not data:
        await msg.reply(STR("invest_status_empty"))
        return

    lines = [STR("invest_status_header")]
    now = time.time()
    for index, investment in enumerate(data, 1):
        left = int(investment["end_time"] - now)
        lines.append(
            format_with_names(
                STR("invest_status_line"),
                index=index,
                amount=investment["amount"],
                time=human_time_left(left),
            )
        )
    await msg.reply("\n".join(lines))


async def investments_watcher(bot: Bot) -> None:
    """Settle due investments and notify players without losing payouts."""
    while True:
        for investment in get_finished_investments():
            user_id = investment["user_id"]
            name = escape(investment["name"] or "Игрок")
            chat_id = investment["chat_id"]
            amount = investment["amount"]

            if random.random() < INVEST_LOSE_CHANCE:
                if not complete_investment(investment["id"], user_id):
                    continue
                text = format_with_names(
                    STR("invest_finished_fail"), name=name, amount=amount
                )
            else:
                multiplier = round(
                    random.uniform(INVEST_GROWTH_MIN, INVEST_GROWTH_MAX), 2
                )
                profit = int(amount * multiplier)
                if not complete_investment(investment["id"], user_id, profit):
                    continue
                text = format_with_names(
                    STR("invest_finished_success"),
                    name=name,
                    profit=profit,
                    multiplier=multiplier,
                )

            try:
                await bot.send_message(chat_id, text)
            except Exception:
                # The investment is already settled; delivery must not duplicate payout.
                pass

        await asyncio.sleep(INVEST_WATCH_INTERVAL)
