"""Чёрный список: человека в игнор — бот его сообщения просто не видит.

Команды только для id из ADMIN_IDS (config.py):
    /ignore [id] [причина]   — или ответом на сообщение человека
    /unignore <id>           — или ответом на сообщение
    /ignorelist              — кто в игноре

BlacklistMiddleware вешается на диспетчер в run.py и режет сообщения
игнорируемых до всех роутеров. Админы из игнора исключены — иначе можно
заблокировать самого себя и не найти команду /unignore.
"""

import logging
import time
from datetime import datetime

from aiogram import BaseMiddleware, Router
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.filters import Command
from aiogram.types import Chat, Message, MessageId, TelegramObject
from typing import Any, Awaitable, Callable

from config import ADMIN_IDS

from database import (
    add_blacklist,
    get_user_card,
    is_blacklisted,
    list_blacklist,
    remove_blacklist,
)
from maintenance import is_admin

logger = logging.getLogger(__name__)

router = Router(name="blacklist")

ADMIN_DENY = "⛔ Команда только для владельца бота и ассистентов."
USAGE = (
    "Напиши так: <code>/ignore 123456789 причина</code>\n"
    "Или ответь этой командой на сообщение человека — id возьму из него."
)


class BlacklistMiddleware(BaseMiddleware):
    """Молча пропускает сообщения тех, кто в игноре."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is not None and not is_admin(user) and is_blacklisted(user.id):
            logger.info("Игнор: %s (@%s)", user.id, user.username)
            return None
        return await handler(event, data)


class SilentForIgnored(BaseRequestMiddleware):
    """Не даёт боту отправить человеку из игнора вообще ничего.

    Стоит на сессии бота в run.py: bot.session.middleware(SilentForIgnored())
    Поэтому режет любую отправку из любого хендлера и любой фоновой задачи,
    а не только те, что в owner.py.

    Группы и каналы (chat_id < 0) и админы пропускаются: в группе бот пишет
    всем, и один игнор не должен глушить чат.
    """

    # Сколько секунд держать список игнора в памяти, чтобы не лезть в базу
    # на каждое сообщение.
    TTL = 5.0

    def __init__(self, ttl: float | None = None) -> None:
        self._ttl = self.TTL if ttl is None else ttl
        self._ids: set[int] = set()
        self._expires = 0.0

    def _ignored(self) -> set[int]:
        now = time.monotonic()
        if now >= self._expires:
            try:
                self._ids = {row["user_id"] for row in list_blacklist()}
            except Exception as exc:  # база занята — лучше отправить, чем потерять
                logger.warning("Список игнора не прочитан: %s", exc)
            self._expires = now + self._ttl
        return self._ids

    @staticmethod
    def _stub(method: Any, chat_id: int) -> Any:
        """Пустой ответ вместо настоящего сообщения, чтобы хендлер не упал."""
        returning = getattr(type(method), "__returning__", bool)
        try:
            if returning is Message:
                return Message(
                    message_id=0,
                    date=datetime.now(),
                    chat=Chat(id=chat_id, type="private"),
                )
            if returning is MessageId:
                return MessageId(message_id=0)
            if returning is list:
                return []
        except Exception:  # noqa: BLE001 — пусть будет True, главное не падать
            pass
        return True

    async def __call__(
        self,
        make_request: Callable[..., Awaitable[Any]],
        bot: Any,
        method: Any,
    ) -> Any:
        chat_id = getattr(method, "chat_id", None)
        if (
            isinstance(chat_id, int)
            and chat_id > 0
            and chat_id not in ADMIN_IDS
            and chat_id in self._ignored()
        ):
            logger.info(
                "Игнор: %s в %s не отправляю", type(method).__name__, chat_id
            )
            return self._stub(method, chat_id)
        return await make_request(bot, method)


def _raw_args(msg: Message) -> str:
    parts = (msg.text or "").split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _target(msg: Message) -> tuple[int | None, Any, str]:
    """Кого трогаем и что осталось причиной.

    Возвращает (user_id, объект пользователя или None, причина/остаток).
    """
    replied = msg.reply_to_message
    if replied and replied.from_user:
        return replied.from_user.id, replied.from_user, _raw_args(msg)

    rest = _raw_args(msg)
    if not rest:
        return None, None, ""

    first, _, tail = rest.partition(" ")
    first = first.lstrip("@")
    if first.isdigit():
        return int(first), None, tail.strip()
    return None, None, rest


def _pretty(uid: int, user: Any = None, fallback: str | None = None) -> str:
    name = fallback or ""
    username = getattr(user, "username", None) if user else None
    if user:
        name = user.full_name or name
    if not name:
        try:
            card = get_user_card(uid)
        except Exception:  # noqa: BLE001 — база может быть занята
            card = None
        if card:
            name = (
                card.get("first_name")
                or card.get("name")
                or card.get("username")
                or ""
            )
    label = f"<b>{name}</b> " if name else ""
    handle = f" @{username}" if username else ""
    return f"{label}<code>{uid}</code>{handle}"


@router.message(Command("ignore", "чс", "blacklist_add"))
async def ignore_cmd(msg: Message) -> None:
    if not is_admin(msg.from_user):
        await msg.reply(ADMIN_DENY)
        return

    uid, user, reason = _target(msg)
    if uid is None:
        await msg.reply(USAGE)
        return
    if uid == msg.from_user.id:
        await msg.reply("Себя в игнор ставить не надо — ты и так админ.")
        return
    if getattr(user, "is_bot", False):
        await msg.reply("Ботов в игнор добавлять бессмысленно.")
        return

    add_blacklist(
        uid,
        username=getattr(user, "username", None) if user else None,
        first_name=getattr(user, "full_name", None) if user else None,
        reason=reason or "без причины",
        added_by=msg.from_user.id,
    )
    await msg.reply(
        f"🚫 {_pretty(uid, user)} в игноре.\n"
        f"Причина: {reason or 'без причины'}\n"
        "<i>Бот больше не отвечает на его сообщения. Вернуть: /unignore</i>"
    )


@router.message(Command("unignore", "разчс", "blacklist_del"))
async def unignore_cmd(msg: Message) -> None:
    if not is_admin(msg.from_user):
        await msg.reply(ADMIN_DENY)
        return

    uid, user, _rest = _target(msg)
    if uid is None:
        await msg.reply("Кого убрать? <code>/unignore 123456789</code> или ответом.")
        return

    if remove_blacklist(uid):
        await msg.reply(f"✅ {_pretty(uid, user)} больше не в игноре.")
    else:
        await msg.reply(f"🤷 {_pretty(uid, user)} и не был в игноре.")


@router.message(Command("ignorelist", "списокчс", "blacklist"))
async def ignorelist_cmd(msg: Message) -> None:
    if not is_admin(msg.from_user):
        await msg.reply(ADMIN_DENY)
        return

    rows = list_blacklist()
    if not rows:
        await msg.reply("📋 Игнор пуст — никто никого не обидел.")
        return

    lines = [f"📋 <b>Игнор: {len(rows)}</b>", ""]
    for row in rows[:50]:
        who = _pretty(
            row["user_id"],
            None,
            fallback=row.get("first_name") or "",
        )
        handle = f" @{row['username']}" if row.get("username") else ""
        lines.append(
            f"{who}{handle}\n"
            f"   причина: {row.get('reason') or 'без причины'} · {row.get('created_at', '')}"
        )
    if len(rows) > 50:
        lines.append(f"\n… и ещё {len(rows) - 50}")
    await msg.reply("\n".join(lines))
