from aiogram import Router
from aiogram.types import Message

from database import add_chat, touch_user


router = Router(name="autosave")


@router.message()
async def on_group_message(msg: Message) -> None:
    if msg.chat.type in {"group", "supergroup"} and msg.from_user:
        add_chat(msg.chat.id)
        touch_user(msg.from_user.id, msg.from_user.full_name, msg.chat.id)
