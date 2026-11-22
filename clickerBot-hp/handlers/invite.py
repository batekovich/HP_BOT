import asyncio
import random

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from basic_utils import STR
from config import (
    INVITE_INTERVAL,
    INVITE_SUPERCLICK_CHANCE,
    INVITE_TIMEOUT,
)
from database import (
    get_all_chats,
    inc_click,
    inc_exp,
    inc_superclick,
    touch_user,
)
from utils.media import send_click_image


router = Router(name="invite")


active_invites: dict[int, bool] = {}


async def invite_task(bot: Bot) -> None:
    while True:
        await asyncio.sleep(INVITE_INTERVAL)
        chats = get_all_chats()
        for chat_id in chats:
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text=STR("invite_accept"), callback_data="accept"
                ),
                InlineKeyboardButton(
                    text=STR("invite_decline"), callback_data="decline"
                ),
            )
            active_invites[chat_id] = True
            try:
                await bot.send_message(
                    chat_id,
                    STR("invite_message"),
                    reply_markup=builder.as_markup(),
                )
            except Exception:
                # The chat may have been deleted or the bot removed.
                active_invites.pop(chat_id, None)
                continue

        # Active invites expire after a short window.
        await asyncio.sleep(INVITE_TIMEOUT)
        for chat_id in list(active_invites.keys()):
            active_invites.pop(chat_id, None)


@router.callback_query(F.data == "accept")
async def accept_invite(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id
    if not active_invites.get(chat_id):
        await callback.answer(STR("invite_expired"), show_alert=True)
        return

    # The first user to accept closes the invite.
    active_invites.pop(chat_id, None)

    user = callback.from_user
    touch_user(user.id, user.full_name, chat_id)
    inc_exp(user.id)

    if random.random() <= INVITE_SUPERCLICK_CHANCE:
        inc_superclick(user.id)
        await send_click_image(
            callback.message,
            caption="НАПЕЧАТАЛ ДОКУМЕНТОВ! 💖🤤💖🤤",
            image_name="superclick.jpg",
            user=user,
        )
    else:
        inc_click(user.id)
        await send_click_image(
            callback.message,
            caption="НАПЕЧАТАЛ ЧЛЕНОВ БИСТРА! 💖🤤",
            image_name="clicked.jpg",
            user=user,
        )
    await callback.answer()


@router.callback_query(F.data == "decline")
async def decline_invite(callback: CallbackQuery) -> None:
    await callback.answer(STR("invite_declined_toast"), show_alert=True)
