from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from basic_utils import STR, format_with_names
from database import get_top


router = Router(name="top")


async def _send_top(msg: Message, column: str, score_name: str) -> None:
    data = get_top(column)
    if not data:
        await msg.reply(STR("top_empty"))
        return

    lines = [format_with_names(STR("top_header"), type=score_name)]
    for index, (name, count) in enumerate(data, 1):
        lines.append(
            STR("top_entry").format(
                index=index,
                name=escape(name or "Неизвестный игрок"),
                count=count,
            )
        )
    await msg.reply("\n".join(lines))


@router.message(Command("top"))
async def top_cmd(msg: Message) -> None:
    # Keep the old `/top bistro` form working while exposing named commands.
    args = (msg.text or "").split()
    mode = args[1].lower() if len(args) > 1 else "normal"
    if mode in {"bistro", "super", "superclick"}:
        await _send_top(msg, "superclicks", format_with_names("{super_name}"))
        return
    if mode in {"sosatel", "sosatel_clicks"}:
        await _send_top(msg, "sosatel_clicks", format_with_names("{sosatel_name}"))
        return
    await _send_top(msg, "clicks", format_with_names("{normal_name}"))


@router.message(Command("topbistro"))
async def top_bistro_cmd(msg: Message) -> None:
    await _send_top(msg, "superclicks", format_with_names("{super_name}"))


@router.message(Command("topsosatel"))
async def top_sosatel_cmd(msg: Message) -> None:
    await _send_top(msg, "sosatel_clicks", format_with_names("{sosatel_name}"))
