"""Команды владельца: бэкап базы, редактор печатей и факсов, праздники.

Всё здесь доступно только id из ADMIN_IDS (config.py).
"""

import asyncio
import logging
import sqlite3
import time
from datetime import datetime
from functools import wraps
from html import escape
from pathlib import Path

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from basic_utils import STR, format_with_names
from config import (
    ADMIN_IDS,
    BASE_DIR,
    DATABASE_PATH,
    DB_BACKUP_INTERVAL_DAYS,
    HOLIDAY_CHECK_INTERVAL,
    NORMAL_NAME,
    SOSATEL_NAME,
    SUPER_NAME,
)
from database import (
    apply_holiday,
    change_scores,
    find_users,
    get_all_user_ids,
    get_user_card,
    holiday_add,
    holiday_delete,
    holiday_list,
    holidays_for_date,
    list_blacklist,
    set_scores,
    transfer_scores,
)
from maintenance import is_admin

logger = logging.getLogger(__name__)

router = Router(name="owner")

# Отметка, когда база уходила в последний раз: переживает перезапуск бота.
BACKUP_MARKER = BASE_DIR / "last_db_sent.txt"
# Снимок базы для отправки (сама clicker.db во время работы бывает занята).
SNAPSHOT_PATH = BASE_DIR / "clicker_backup.db"

ADMIN_DENY = "⛔ Команда только для владельца бота и ассистентов."


def _help_text() -> str:
    return (
        "🧰 <b>Админ-команды</b>\n"
        "\n"
        "🗄 /db — прислать clicker.db прямо сейчас\n"
        "👤 /bal <code>id</code> — карточка человека (или ответом на его сообщение)\n"
        "➕ /give <code>id 50 10 5</code> — прибавить: печати, факсы, супер\n"
        "🎯 /setbal <code>id 90 90 0</code> — поставить точные значения\n"
        "🔁 /transfer <code>111 222</code> — перенести всё на новый аккаунт\n"
        "🔍 /find <code>котёнок</code> — поиск по имени\n"
        "🚫 /ignore <code>id причина</code> — в игнор "
        "(или ответом на сообщение)\n"
        "✅ /unignore <code>id</code> — убрать из игнора\n"
        "📋 /ignorelist — кто в игноре\n"
        "🎉 /holiday — праздники и бонусы\n"
        "📨 /sendall <code>текст</code> — рассылка всем в личку, кроме игнора "
        "(можно ответом на сообщение)\n"
        "\n"
        "<i>Порядок чисел везде: печати, факсы, суперклики.</i>\n"
        f"<i>Бэкап базы уходит сам раз в {DB_BACKUP_INTERVAL_DAYS} дн.</i>"
    )


def admin_only(func):
    """Пускать дальше только владельца и ассистентов."""

    @wraps(func)
    async def wrapper(msg: Message, *args, **kwargs):
        if not is_admin(msg.from_user):
            await msg.reply(ADMIN_DENY)
            return None
        return await func(msg, *args, **kwargs)

    return wrapper


# ─── помощники ──────────────────────────────────────────────────────────────

def _args(msg: Message) -> list[str]:
    parts = (msg.text or "").split()
    return parts[1:]


def _split_id(msg: Message, args: list[str]) -> tuple[int | None, list[str]]:
    """Первый аргумент — id, иначе берём автора сообщения, на которое ответили."""
    if args and args[0].lstrip("-").isdigit():
        return int(args[0]), args[1:]
    reply = getattr(msg, "reply_to_message", None)
    author = getattr(reply, "from_user", None)
    if author is not None:
        return author.id, args
    return None, args


def _nums(items: list[str]) -> list[int] | None:
    """Все аргументы — числа? Тогда список, иначе None."""
    numbers: list[int] = []
    for item in items:
        try:
            numbers.append(int(item.replace("+", "").strip()))
        except ValueError:
            return None
    return numbers


def _ts(value: float) -> str:
    if not value:
        return "—"
    return datetime.fromtimestamp(value).strftime("%d.%m.%Y %H:%M")


def _card(card: dict, header: str = "") -> str:
    lines = [header, ""] if header else []
    lines += [
        f"👤 <b>{escape(card['name'] or 'без имени')}</b>  "
        f"<code>{card['user_id']}</code>",
        "",
        f"🖨 печати: <b>{card['clicks']}</b>",
        f"📠 факсы: <b>{card['sosatel_clicks']}</b>",
        f"⚡ суперклики: <b>{card['superclicks']}</b>",
        f"✨ опыт: {card['exp']}",
        f"🕒 был(а): {_ts(card['last_seen'])}",
    ]
    return "\n".join(lines)


def _snapshot() -> Path | None:
    """Копия базы через sqlite backup — без риска поймать недописанный файл."""
    try:
        source = sqlite3.connect(DATABASE_PATH, timeout=30)
        try:
            target = sqlite3.connect(SNAPSHOT_PATH)
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
    except Exception as exc:
        logger.warning("Не удалось снять копию базы: %s", exc)
        return None
    return SNAPSHOT_PATH


def _valid_date(value: str) -> bool:
    if len(value) != 5 or value[2] != "-":
        return False
    try:
        datetime.strptime(f"2026-{value}", "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _holiday_text() -> str:
    items = holiday_list()
    lines = ["🎉 <b>Праздники</b>"]
    if not items:
        lines.append("пока пусто")
    for item in items:
        lines.append(
            f"<code>{item['id']}</code> {item['date']} "
            f"<b>{escape(item['name'])}</b> — +{item['clicks']} печ, "
            f"+{item['sosatel_clicks']} факс, +{item['superclicks']} супер"
        )
    lines += [
        "",
        "Добавить: <code>/holiday add 01-01 Новый год 100 20 10</code>",
        "Выдать сейчас: <code>/holiday give 1</code>",
        "Удалить: <code>/holiday del 1</code>",
    ]
    return "\n".join(lines)


def _profile_text(card: dict) -> str:
    """Тот же профиль, что показывает /profile."""
    return format_with_names(
        STR("profile_header"),
        user=escape(card["name"] or "друг"),
        normal=card["clicks"],
        fast=card["fast_clicks"],
        super=card["superclicks"],
        sosatel=card["sosatel_clicks"],
        exp=card["exp"],
    )


def _bonus_line(result: dict) -> str:
    parts = []
    if result["clicks"]:
        parts.append(f"+{result['clicks']} {NORMAL_NAME}")
    if result["sosatel_clicks"]:
        parts.append(f"+{result['sosatel_clicks']} {SOSATEL_NAME}")
    if result["superclicks"]:
        parts.append(f"+{result['superclicks']} {SUPER_NAME}")
    return ", ".join(parts) or "без очков"


async def notify_holiday(bot: Bot, result: dict) -> int:
    """Пишет начисленным, кроме игнора: за что бонус и профиль. Вернёт, кому дошло."""
    bonus = escape(_bonus_line(result))
    ignored = {row["user_id"] for row in list_blacklist()}
    sent = 0
    for user_id in result["user_ids"]:
        if user_id in ignored:
            logger.info("Бонус %s не отправлен: в игноре", user_id)
            continue
        card = get_user_card(user_id)
        if card is None:
            continue
        text = (
            f"🎉 <b>{escape(result['holiday'])}</b>\n\n"
            f"Тебе начислено: <b>{bonus}</b>\n\n"
            f"{_profile_text(card)}"
        )
        try:
            await bot.send_message(user_id, text)
            sent += 1
        except Exception as exc:  # человек не начинал чат с ботом или заблокировал
            logger.info("Бонус не отправлен %s: %s", user_id, exc)
        await asyncio.sleep(0.05)  # лимит Telegram — около 30 сообщений в секунду
    return sent


async def _finish_holiday(bot: Bot, result: dict, msg: Message | None) -> None:
    """Отправляет уведомления и сводку админам."""
    sent = await notify_holiday(bot, result)
    summary = (
        f"🎉 <b>{escape(result['holiday'])}</b> ({result['date']})\n"
        f"Начислено: {escape(_bonus_line(result))}\n"
        f"Получили бонус: {result['given']} чел.\n"
        f"Уведомление дошло: {sent} чел. "
        f"<i>(остальные в игноре или не начинали чат с ботом)</i>"
    )
    if msg is not None:
        await msg.reply(summary)
        return
    await _send_to_admins(bot, summary)


async def _send_to_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:
            logger.warning("Админу %s не отправлено: %s", admin_id, exc)


async def _send_db(bot: Bot) -> int:
    """Рассылает снимок базы всем админам. Возвращает число доставок."""
    snapshot = _snapshot()
    if snapshot is None:
        return 0
    name = f"clicker_{time.strftime('%Y-%m-%d')}.db"
    caption = f"🗄 {name}\n{time.strftime('%d.%m.%Y %H:%M')}"
    sent = 0
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_document(
                admin_id, FSInputFile(snapshot, filename=name), caption=caption
            )
            sent += 1
        except Exception as exc:
            logger.warning("База не ушла админу %s: %s", admin_id, exc)
    return sent


# ─── команды ────────────────────────────────────────────────────────────────

@router.message(Command("admin", "adm", "админ", "adminhelp"))
@admin_only
async def admin_help_cmd(msg: Message) -> None:
    await msg.reply(_help_text())


@router.message(Command("db", "dbnow", "база"))
@admin_only
async def db_cmd(msg: Message) -> None:
    snapshot = _snapshot()
    if snapshot is None:
        await msg.reply("⚠️ Не смог прочитать базу, смотри лог бота.")
        return
    name = f"clicker_{time.strftime('%Y-%m-%d')}.db"
    await msg.answer_document(
        FSInputFile(snapshot, filename=name),
        caption=f"🗄 {name}\n{time.strftime('%d.%m.%Y %H:%M')}",
    )


@router.message(Command("bal", "balance", "баланс"))
@admin_only
async def bal_cmd(msg: Message) -> None:
    target, _ = _split_id(msg, _args(msg))
    if target is None:
        await msg.reply(
            "Формат: <code>/bal id</code> или ответь этой командой на сообщение человека."
        )
        return
    card = get_user_card(target)
    if card is None:
        await msg.reply(
            f"❓ В базе нет <code>{target}</code>.\n"
            f"Начислить с нуля: <code>/give {target} 50</code>"
        )
        return
    await msg.reply(_card(card))


@router.message(Command("give", "addbal", "начислить"))
@admin_only
async def give_cmd(msg: Message) -> None:
    target, rest = _split_id(msg, _args(msg))
    numbers = _nums(rest)
    if target is None or not numbers or len(numbers) > 3:
        await msg.reply(
            "Формат: <code>/give id печати [факсы] [супер]</code>\n"
            "например <code>/give 123456789 50 10 5</code>"
        )
        return
    clicks = numbers[0]
    sosatel = numbers[1] if len(numbers) > 1 else 0
    superclicks = numbers[2] if len(numbers) > 2 else 0
    change_scores(
        target, clicks=clicks, superclicks=superclicks, sosatel=sosatel
    )
    await msg.reply(_card(get_user_card(target), header="➕ <b>Начислил</b>"))


@router.message(Command("setbal", "set", "поставить"))
@admin_only
async def setbal_cmd(msg: Message) -> None:
    target, rest = _split_id(msg, _args(msg))
    numbers = _nums(rest)
    if target is None or not numbers or len(numbers) > 3:
        await msg.reply(
            "Формат: <code>/setbal id печати [факсы] [супер]</code>\n"
            "например <code>/setbal 123456789 90 90 0</code>"
        )
        return
    clicks = numbers[0]
    sosatel = numbers[1] if len(numbers) > 1 else None
    superclicks = numbers[2] if len(numbers) > 2 else None
    set_scores(
        target, clicks=clicks, superclicks=superclicks, sosatel=sosatel
    )
    await msg.reply(_card(get_user_card(target), header="🎯 <b>Поставил</b>"))


@router.message(Command("transfer", "перенести"))
@admin_only
async def transfer_cmd(msg: Message) -> None:
    numbers = _nums(_args(msg))
    if not numbers or len(numbers) != 2:
        await msg.reply(
            "Формат: <code>/transfer старый_id новый_id</code>\n"
            "например <code>/transfer 111111111 222222222</code>"
        )
        return
    result = transfer_scores(numbers[0], numbers[1])
    if not result["ok"]:
        await msg.reply(f"⚠️ {escape(result['error'])}")
        return
    src, dst = result["src"], result["dst"]
    await msg.reply(
        f"🔁 Перенёс <code>{src['user_id']}</code> → <code>{dst['user_id']}</code>\n\n"
        f"печати: {src['clicks']} → {dst['clicks']}\n"
        f"факсы: {src['sosatel_clicks']} → {dst['sosatel_clicks']}\n"
        f"супер: {src['superclicks']} → {dst['superclicks']}\n\n"
        "<i>Старый id обнулён, чтобы перенос не повторили дважды. "
        "Запись осталась в таблице transfers.</i>"
    )


@router.message(Command("find", "найти"))
@admin_only
async def find_cmd(msg: Message) -> None:
    query = " ".join(_args(msg)).strip()
    if not query:
        await msg.reply("Формат: <code>/find часть имени</code>")
        return
    rows = find_users(query)
    if not rows:
        await msg.reply(f"🔍 По «{escape(query)}» никого не нашёл.")
        return
    lines = [f"🔍 <b>«{escape(query)}»</b> — найдено {len(rows)}"]
    for row in rows:
        lines.append(
            f"<code>{row['user_id']}</code> {escape(row['name']) or '—'} · "
            f"{row['clicks']} печ / {row['sosatel_clicks']} факс / "
            f"{row['superclicks']} супер"
        )
    await msg.reply("\n".join(lines))


@router.message(Command("holiday", "праздник"))
@admin_only
async def holiday_cmd(msg: Message) -> None:
    args = _args(msg)
    action = args[0].lower() if args else "list"
    rest = args[1:]

    if action in {"add", "добавить", "set"}:
        date = rest[0] if rest else ""
        if not _valid_date(date):
            await msg.reply(
                "Формат: <code>/holiday add 01-01 Новый год 100 20 10</code>\n"
                "дата ММ-ДД, числа: печати, факсы, супер."
            )
            return
        tail = rest[1:]
        numbers: list[int] = []
        while tail and len(numbers) < 3:
            try:
                numbers.insert(0, int(tail[-1]))
                tail.pop()
            except ValueError:
                break
        title = " ".join(tail).strip() or "Праздник"
        clicks = numbers[0] if len(numbers) > 0 else 0
        sosatel = numbers[1] if len(numbers) > 1 else 0
        superclicks = numbers[2] if len(numbers) > 2 else 0
        holiday_add(date, title, clicks, superclicks, sosatel)
        await msg.reply(
            f"🎉 Добавил: <b>{escape(title)}</b> — {date}\n"
            f"печати +{clicks}, факсы +{sosatel}, супер +{superclicks}\n\n"
            + _holiday_text()
        )
        return

    if action in {"del", "delete", "удалить"}:
        numbers = _nums(rest)
        if not numbers:
            await msg.reply("Формат: <code>/holiday del 1</code>")
            return
        removed = holiday_delete(numbers[0])
        await msg.reply(
            "🗑 Удалил." if removed else "Такого праздника нет."
        )
        return

    if action in {"give", "now", "выдать"}:
        numbers = _nums(rest)
        if not numbers:
            await msg.reply("Формат: <code>/holiday give 1</code>")
            return
        result = apply_holiday(numbers[0])
        if not result["ok"]:
            await msg.reply(f"⚠️ {escape(result['error'])}")
            return
        if result["given"] == 0:
            await msg.reply("Все уже получили этот бонус, второй раз не даю.")
            return
        await _finish_holiday(msg.bot, result, msg)
        return

    await msg.reply(_holiday_text())


# ─── фоновые задачи ─────────────────────────────────────────────────────────

async def db_backup_task(bot: Bot) -> None:
    """Раз в DB_BACKUP_INTERVAL_DAYS дней присылает clicker.db админам."""
    interval = DB_BACKUP_INTERVAL_DAYS * 24 * 3600
    while True:
        try:
            last = 0.0
            if BACKUP_MARKER.is_file():
                try:
                    last = float(BACKUP_MARKER.read_text(encoding="utf-8").strip())
                except ValueError:
                    last = 0.0
            now = time.time()
            if now - last >= interval:
                sent = await _send_db(bot)
                if sent:
                    BACKUP_MARKER.write_text(str(int(now)), encoding="utf-8")
                    logger.info("Копия базы отправлена админам: %s", sent)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Бэкап базы не ушёл: %s", exc)
        await asyncio.sleep(1800)


async def holiday_task(bot: Bot) -> None:
    """Проверяет, не наступил ли праздник, и начисляет бонус всем."""
    while True:
        try:
            today = time.strftime("%m-%d")
            for item in holidays_for_date(today):
                result = apply_holiday(item["id"])
                if result["ok"] and result["given"]:
                    await _finish_holiday(bot, result, None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Праздничный бонус не сработал: %s", exc)
        await asyncio.sleep(HOLIDAY_CHECK_INTERVAL)


# ─── рассылка всем ──────────────────────────────────────────────────────────

async def broadcast(
    bot: Bot, text: str | None, source: Message | None
) -> tuple[int, int, int]:
    """Шлёт всем из базы, кроме игнора: (дошло, всего, сколько в игноре)."""
    all_ids = get_all_user_ids()
    ignored = {row["user_id"] for row in list_blacklist()}
    user_ids = [uid for uid in all_ids if uid not in ignored]
    sent = 0
    for user_id in user_ids:
        try:
            if source is not None:
                await bot.copy_message(user_id, source.chat.id, source.message_id)
            else:
                await bot.send_message(user_id, text)
            sent += 1
        except Exception as exc:  # не начинал чат с ботом или заблокировал
            logger.info("Рассылка не дошла %s: %s", user_id, exc)
        await asyncio.sleep(0.05)  # лимит Telegram — около 30 сообщений в секунду
    return sent, len(user_ids), len(all_ids) - len(user_ids)


@router.message(Command("sendall", "broadcast", "рассылка"))
@admin_only
async def sendall_cmd(msg: Message) -> None:
    source = getattr(msg, "reply_to_message", None)
    parts = (msg.text or "").split(maxsplit=1)
    text = parts[1].strip() if len(parts) > 1 else ""
    if source is None and not text:
        await msg.reply(
            "Формат: <code>/sendall текст</code>\n"
            "или ответь /sendall на сообщение — разошлю его копию."
        )
        return
    await msg.reply("📨 Рассылаю, подожди...")
    sent, total, skipped = await broadcast(msg.bot, text or None, source)
    ignored_line = f"\n🚫 В игноре, не писали: {skipped}." if skipped else ""
    await msg.reply(
        f"📨 Готово: дошло {sent} из {total}.{ignored_line}\n"
        "<i>Остальные не начинали чат с ботом или заблокировали его.</i>"
    )
