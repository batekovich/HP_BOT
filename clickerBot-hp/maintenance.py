"""Режим технического обслуживания.

Флаг — файл maintenance.flag рядом с ботом. Пока он лежит на диске, бот
отвечает «технические работы» всем, кроме ADMIN_IDS и ADMIN_USERNAMES,
а они продолжают пользоваться ботом и командой /test.

Состояние живёт в файле, поэтому переживает перезапуск. Включение и
выключение — командой /test on | /test off (или вручную: создать/удалить
maintenance.flag).
"""

import logging
import time

from aiogram import BaseMiddleware
from aiogram.types import Message

from config import ADMIN_IDS, ADMIN_USERNAMES, MAINTENANCE_FLAG

logger = logging.getLogger(__name__)

GROUP_TYPES = {"group", "supergroup"}

# Чтобы не залить группу ответами, в один чат напоминаем не чаще раза в минуту.
NOTICE_EVERY = 60

NOTICE = (
    "🛠 <b>Технические работы</b>\n"
    "Бот обновляется, команды пока не работают.\n"
    "Вернусь совсем скоро ✅"
)

_last_notice: dict[int, float] = {}


def is_maintenance() -> bool:
    """True, если включён режим техобслуживания."""
    return MAINTENANCE_FLAG.is_file()


def maintenance_since() -> float | None:
    """Когда включили техработы (unix время) или None, если режим выключен."""
    try:
        return MAINTENANCE_FLAG.stat().st_mtime
    except OSError:
        return None


def set_maintenance(enabled: bool) -> bool:
    """Включает или выключает режим. Возвращает True, если состояние изменилось."""
    active = is_maintenance()
    if enabled == active:
        return False
    if enabled:
        MAINTENANCE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        MAINTENANCE_FLAG.write_text(str(int(time.time())), encoding="utf-8")
        logger.warning("Режим техобслуживания включён")
    else:
        MAINTENANCE_FLAG.unlink(missing_ok=True)
        _last_notice.clear()
        logger.warning("Режим техобслуживания выключен")
    return True


def is_admin(user) -> bool:
    """Владелец или ассистент: числовой id из ADMIN_IDS либо юзернейм из ADMIN_USERNAMES."""
    if user is None:
        return False
    if ADMIN_IDS and user.id in ADMIN_IDS:
        return True
    username = (getattr(user, "username", None) or "").lstrip("@").lower()
    return bool(username) and username in ADMIN_USERNAMES


class MaintenanceMiddleware(BaseMiddleware):
    """Пускает дальше только админов, пока включены техработы.

    Ставится на сообщения перед роутерами: обычный пользователь не доходит
    ни до одной команды, а админ работает как обычно (в том числе /test off).
    """

    async def __call__(self, handler, event: Message, data):
        if not is_maintenance():
            return await handler(event, data)

        user = getattr(event, "from_user", None)
        chat = getattr(event, "chat", None)
        if user is None or chat is None:  # служебные сообщения без автора
            return await handler(event, data)

        if is_admin(user):
            return await handler(event, data)

        text = (getattr(event, "text", None) or "").lstrip()
        # В группах молчим на обычную болтовню — отвечаем только на команды.
        if chat.type in GROUP_TYPES and not text.startswith("/"):
            return None

        now = time.monotonic()
        last = _last_notice.get(chat.id)
        if last is not None and now - last < NOTICE_EVERY:
            return None
        _last_notice[chat.id] = now

        try:
            await event.reply(NOTICE)
        except Exception as exc:  # бот может быть заблокирован или без прав
            logger.warning("Не удалось ответить про техработы: %s", exc)
        return None
