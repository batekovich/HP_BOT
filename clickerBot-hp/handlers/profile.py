from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from basic_utils import STR, format_with_names
from database import add_chat, get_counts, touch_user


router = Router(name="profile")


@router.message(Command("profile"))
async def profile_cmd(msg: Message) -> None:
    if msg.chat.type in {"group", "supergroup"}:
        add_chat(msg.chat.id)

    user_id, name = msg.from_user.id, msg.from_user.full_name
    touch_user(user_id, name, msg.chat.id)
    normal, fast, sup, sosatel, exp = get_counts(user_id)
    text = format_with_names(
        STR("profile_header"),
        user=escape(name),
        normal=normal,
        fast=fast,
        super=sup,
        sosatel=sosatel,
        exp=exp,
    )
    await msg.reply(text)
