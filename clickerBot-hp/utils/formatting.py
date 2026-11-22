from html import escape

from aiogram.types import User


def format_user_link(user: User) -> str:
    name = escape(user.full_name)
    if user.username:
        return f"<a href='https://t.me/{user.username}'><b>{name}</b></a>"
    return f"<a href='tg://user?id={user.id}'><b>{name}</b></a>"
