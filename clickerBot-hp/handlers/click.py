import random
import time
from html import escape
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from basic_utils import STR, format_with_names, human_time_left
from config import (
    ADMIN_IDS,
    ADMIN_USERNAMES,
    CLICK_COOLDOWN,
    SOSATEL_COOLDOWN,
    SUPERCLICK_CHANCE,
    SUPERCLICK_COOLDOWN,
)
from database import (
    add_chat,
    get_chat_top,
    get_counts,
    get_remaining_cd,
    inc_chat_score,
    inc_click,
    inc_exp,
    inc_sosatel,
    inc_superclick,
    get_bot_stats,
    register_chat_start,
    touch_chat_user,
    touch_user,
    try_use_cooldown,
)
from maintenance import (
    is_admin,
    is_maintenance,
    maintenance_since,
    set_maintenance,
)
from utils.media import ASSETS_DIR, send_click_image


router = Router(name="clicker")

GROUP_TYPES = {"group", "supergroup"}

# Счёт внутри чата ведётся отдельно для каждого чата.
LEADER_MODES = {
    "normal": ("clicks", "{normal_name}"),
    "click": ("clicks", "{normal_name}"),
    "bistro": ("superclicks", "{super_name}"),
    "super": ("superclicks", "{super_name}"),
    "superclick": ("superclicks", "{super_name}"),
    "sosatel": ("sosatel_clicks", "{sosatel_name}"),
    "fax": ("sosatel_clicks", "{sosatel_name}"),
}

START_INFO = """ИНФОРМАЦИЯ БОТА🤖

<b>СТАТИСТИКА БОТА:</b>
<blockquote>{stats}</blockquote>

КАНАЛ = @huinky14
ВЛАДЕЛЕЦ = @u4likhan
ХОСТИНГ БОТА = apexnodes.xyz
ПОДДЕРЖАТЬ ПРОЕКТ = <a href="http://t.me/u4likhan">лс влд</a>, <a href="http://t.me/send?start=IVbgfuK77rzI">криптокошелек</a>
АССИСТЕНТЫ = @fr3aksnet
<a href="http://t.me/huinky14?direct">ПРЕДЛОЖКА ЩЕЩЕ АМЫ</a>

<b>1. ЧТО УМЕЕТ ЭТОТ БОТ?:</b>
УМЕЕТ ПЕЧАТАТЬ ✅🖨
2. УМЕЕТ ПЕЧАТАТЬ БЫСТРО ✅🖨🏃‍♀➡️
3. ОТПРАВЛЯТЬ ФАКС ✅📠📞
4. СМОТРЕТЬ ВИДЕО HP!!! 📹🎞📼📀

<b>КОМАНДЫ БОТА:</b>
<blockquote>/hp — КИДАЕТ ВИДЕО ХП
/pechatat "текст" — печатать документы
/pechatathuibistro — печатает члены быстро
/sendfax — отправляет факс
/profile — показывает профиль и опыт
/liders — показывает опытных игроков (работает только в чатах)
/start — начало использования бота
/info — эта справка</blockquote>

БОТ ПРЕДСТАВЛЯЕТСЯ КАК КЛИКЕР БОТ, ГДЕ МОЖНО КЛИКАТЬ КОМАНДЫ И ЮЗАТЬ ИХ, ОСНОВНАЯ МЫСЛЬ БОТА ЗАКЛЮЧАЕТСЯ В ТОМ ЧТО МОЖНО ПЕЧАТАТЬ И ОТПРАВЛЯТЬ ФАКС 📠 А ТАКЖЕ МОЖНО СОБИРАТЬ ОПЫТ И КОЛИЧЕСТВО ПЕЧАТИ ДОКУМЕНТОВ ✅

❤️‍🔥БЛАГОДАРНОСТЬ ЗА ИСПОЛЬЗОВАНИЕ БОТА ❤️‍🔥:
@cloudflarelarp @z1oty @Tea37_letov

<b>ВАЖНАЯ ИНФОРМАЦИЯ:</b>
<blockquote>БОТ НЕ ПРЕДСТАВЛЯЕТСЯ КОМПАНИЕЙ HP Inc, БОТ СОЗДАН В РАЗВЛЕКАТЕЛЬНЫХ ЦЕЛЯХ, И ИСПОЛЬЗУЕТ ТОЛЬКО ТЕХНИКУ HP Inc И НИКАК НЕ ОСКОРБЛЯЕТ КОМПАНИЮ И ИХ СОТРУДНИКОВ</blockquote>

СОТРУДНИЧАЕМ С @BVK_PUBLIC✅✅✅

<b>ИСХОДНИК И ЛИЦЕНЗИЯ:</b>
<blockquote>ОСНОВА = бот @ebu_momera_bot — у него раньше была ссылка на исходный репозиторий
НАША ВЕРСИЯ = <a href="https://github.com/batekovich/HP_BOT">github.com/batekovich/HP_BOT</a>
ЛИЦЕНЗИЯ = MIT, Copyright (c) 2026 batekovich — только на мои правки (кликер, топы по чатам, /info). Код-основа принадлежит авторам @ebu_momera_bot, их лицензия мне не известна</blockquote>"""


def _num(value: int) -> str:
    """12345 -> 12 345"""
    return f"{value:,}".replace(",", " ")


def _active_line(st: dict) -> str:
    """Строка про активных; если за неделю никого — показываем дату последнего клика."""
    head = f"🔥 АКТИВНЫХ ЗА {st['active_days']} ДНЕЙ — "
    if st["active"]:
        return head + _num(st["active"])
    if st.get("last_activity"):
        last = time.strftime("%d.%m.%Y", time.localtime(st["last_activity"]))
        return head + f"нет, последний клик {last}"
    return head + "0"

def build_info() -> str:
    """Текст /info со свежими цифрами из базы."""
    try:
        st = get_bot_stats()
        stats = (
            f"👥 ПОЛЬЗОВАТЕЛЕЙ — {_num(st['users'])}\n"
            f"💬 ЧАТОВ — {_num(st['chats'])}\n"
            f"🖨 ВСЕГО КЛИКОВ — {_num(st['clicks'] + st['superclicks'] + st['sosatel'])}\n"
            + _active_line(st)
        )
    except Exception:
        stats = "👥 СТАТИСТИКА ВРЕМЕННО НЕДОСТУПНА"
    return START_INFO.replace("{stats}", stats)


def _fmt_date(timestamp: float) -> str:
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(timestamp))


async def _prepare_user(msg: Message) -> tuple[int, str]:
    if msg.chat.type in GROUP_TYPES:
        add_chat(msg.chat.id)
    user = msg.from_user
    touch_user(user.id, user.full_name, msg.chat.id)
    if msg.chat.type in GROUP_TYPES:
        touch_chat_user(msg.chat.id, user.id, user.full_name)
    return user.id, user.full_name


def _add_to_chat(msg: Message, user_id: int, column: str) -> None:
    """Keep the per-chat score in sync with the global one."""
    if msg.chat.type in GROUP_TYPES:
        inc_chat_score(msg.chat.id, user_id, column)


async def _cooldown_message(
    msg: Message,
    user_id: int,
    field: str,
    cooldown: int,
    key: str,
) -> None:
    left = get_remaining_cd(user_id, field, cooldown)
    await msg.reply(format_with_names(STR(key), time=human_time_left(left)))


@router.message(Command("start"))
async def start_cmd(msg: Message) -> None:
    user = msg.from_user
    if user is None:
        return
    if msg.chat.type in GROUP_TYPES:
        add_chat(msg.chat.id)
    touch_user(user.id, user.full_name, msg.chat.id)
    if msg.chat.type in GROUP_TYPES:
        touch_chat_user(msg.chat.id, user.id, user.full_name)

    info = register_chat_start(msg.chat.id, user.id, user.full_name)
    if info["is_new"]:
        head = "🆕 <b>Вы начали чат!</b>"
    else:
        head = (
            "ℹ️ <b>Чат уже начинался.</b>\n"
            f"Первый старт: {_fmt_date(info['first_start'])}\n"
            f"Всего запусков: {info['starts_count']}"
        )
    # Инфу о боте на старте не показываем — человек открывает её сам командой /info.
    await msg.reply(head)
    await msg.answer("<i>Подробнее о боте и командах — /info</i>")


BOT_DIR = Path(__file__).resolve().parent.parent

# Видео лежит в отдельной папке HPGOVNO рядом с ботом.
HP_CANDIDATES = (
    BOT_DIR.parent / "HPGOVNO" / "assets" / "hp.mp4",
    BOT_DIR / "HPGOVNO" / "assets" / "hp.mp4",
    ASSETS_DIR / "hp.mp4",
)


def find_hp_video() -> Path | None:
    for path in HP_CANDIDATES:
        if path.is_file():
            return path
    return None


@router.message(Command("hp"))
async def hp_cmd(msg: Message) -> None:
    """Кидает видео HP из папки HPGOVNO/assets/hp.mp4."""
    path = find_hp_video()
    if path is None:
        await msg.reply("❌ Видео не найдено. Ожидал hp.mp4 в HPGOVNO/assets/")
        return
    await msg.answer_video(FSInputFile(path), caption="📹 ВИДЕО HP!!!")


@router.message(Command("info", "help"))
async def info_cmd(msg: Message) -> None:
    await msg.reply(build_info())


async def _is_chat_member(msg: Message, user_id: int) -> bool:
    """True only for users who are still in this chat."""
    try:
        member = await msg.bot.get_chat_member(msg.chat.id, user_id)
    except Exception:
        return False
    if member.status in {"creator", "administrator", "member"}:
        return True
    return bool(getattr(member, "is_member", False))


@router.message(Command("leaders", "liders", "лидеры", "topchat"))
async def leaders_cmd(msg: Message) -> None:
    if msg.chat.type not in GROUP_TYPES:
        await msg.reply(
            "🏆 Лидеры считаются в групповых чатах. "
            "Добавь меня в группу — и топ появится там."
        )
        return

    add_chat(msg.chat.id)
    args = (msg.text or "").split()
    mode = args[1].lower() if len(args) > 1 else "normal"
    column, name_key = LEADER_MODES.get(mode, ("clicks", "{normal_name}"))
    score_name = format_with_names(name_key)

    rows = get_chat_top(msg.chat.id, column, limit=40)
    if not rows:
        await msg.reply(STR("top_empty"))
        return

    lines = [f"🏆 <b>Лидеры этого чата</b> — {escape(score_name)}"]
    place = 0
    for user_id, name, count in rows:
        if not await _is_chat_member(msg, user_id):
            continue
        place += 1
        lines.append(f"{place}. {escape(name or 'Неизвестный игрок')} — {count}")
        if place >= 10:
            break

    if place == 0:
        await msg.reply(
            "Пока никто из участников этого чата не набирал очки.\n"
            "Начни первым: /pechatat"
        )
        return

    lines.append("")
    lines.append("<i>Очки — общие, как в /profile.</i>")
    await msg.reply("\n".join(lines))


@router.message(Command("pechatat"))
async def click_cmd(msg: Message) -> None:
    user_id, _ = await _prepare_user(msg)
    if not try_use_cooldown(user_id, "last_click", CLICK_COOLDOWN):
        await _cooldown_message(
            msg,
            user_id,
            "last_click",
            CLICK_COOLDOWN,
            "timeleft_click",
        )
        return

    # Текст после команды: /pechatat мой текст → «Юзер НАПЕЧАТАЛ: текст»
    parts = (msg.text or "").split(maxsplit=1)
    custom_text = parts[1].strip() if len(parts) > 1 else ""

    inc_click(user_id)
    inc_exp(user_id)
    _add_to_chat(msg, user_id, "clicks")
    _add_to_chat(msg, user_id, "exp")
    clicks, _, _, _, _ = get_counts(user_id)

    if custom_text:
        caption = f"НАПЕЧАТАЛ🖨️🖨: {custom_text}"
    else:
        caption = f"НАПЕЧАТАЛ ДОКУМЕНТОВ!🖨🤪 Всего: {clicks}"

    await send_click_image(
        msg,
        caption=caption,
        image_name="clicked.jpg",
    )


@router.message(Command("pechatathuibistro"))
async def superclick_cmd(msg: Message) -> None:
    user_id, _ = await _prepare_user(msg)
    if not try_use_cooldown(user_id, "last_superclick", SUPERCLICK_COOLDOWN):
        await msg.reply(STR("superclick_cooldown"))
        return

    inc_exp(user_id)
    _add_to_chat(msg, user_id, "exp")
    if random.random() <= SUPERCLICK_CHANCE:
        inc_superclick(user_id)
        _add_to_chat(msg, user_id, "superclicks")
        _, _, superclicks, _, _ = get_counts(user_id)
        await send_click_image(
            msg,
            caption=(
                "БЫСТРО НАПЕЧАТАЛ ЧЛЕНОВ!🖨🔞 "
                f"Всего: {superclicks}"
            ),
            image_name="superclick.jpg",
        )
    else:
        await msg.reply(STR("superclick_fail"))


@router.message(Command("sendfax"))
async def sosatel_cmd(msg: Message) -> None:
    """Register the new score type using the basic click response for now."""
    user_id, _ = await _prepare_user(msg)
    if not try_use_cooldown(user_id, "last_sosatel", SOSATEL_COOLDOWN):
        await _cooldown_message(
            msg,
            user_id,
            "last_sosatel",
            SOSATEL_COOLDOWN,
            "timeleft_sosatel",
        )
        return

    inc_sosatel(user_id)
    inc_exp(user_id)
    _add_to_chat(msg, user_id, "sosatel_clicks")
    _add_to_chat(msg, user_id, "exp")
    sosatel_clicks = get_counts(user_id)[3]
    await send_click_image(
        msg,
        caption=f"ОТПРАВИЛ ФАКС!🤪📠 Всего: {sosatel_clicks}",
        image_name="otsos.jpg",
    )


@router.message(Command("timeleft"))
async def timeleft_cmd(msg: Message) -> None:
    user_id = msg.from_user.id
    lines = [
        format_with_names(
            STR("timeleft_click"),
            time=human_time_left(
                get_remaining_cd(user_id, "last_click", CLICK_COOLDOWN)
            ),
        ),
        format_with_names(
            STR("timeleft_super"),
            time=human_time_left(
                get_remaining_cd(user_id, "last_superclick", SUPERCLICK_COOLDOWN)
            ),
        ),
        format_with_names(
            STR("timeleft_sosatel"),
            time=human_time_left(
                get_remaining_cd(user_id, "last_sosatel", SOSATEL_COOLDOWN)
            ),
        ),
    ]
    await msg.reply("\n".join(lines))


# ─── Техобслуживание: /test (только владелец и ассистенты) ───────────────────

TEST_ON = {"on", "вкл", "включить", "start", "1"}
TEST_OFF = {"off", "выкл", "выключить", "stop", "0"}


def _admins_line() -> str:
    """Кто не попадёт под техработы."""
    parts = [f"@{name}" for name in sorted(ADMIN_USERNAMES)]
    parts += [str(user_id) for user_id in sorted(ADMIN_IDS)]
    return ", ".join(parts) if parts else "никто не настроен"


def _since_line() -> str:
    since = maintenance_since()
    if since is None:
        return "выключены"
    return f"включены с {time.strftime('%d.%m.%Y %H:%M', time.localtime(since))}"


@router.message(Command("test"))
async def test_cmd(msg: Message) -> None:
    """Режим техобслуживания: /test — статус, /test on, /test off."""
    user = msg.from_user
    if not is_admin(user):
        await msg.reply("⛔ Команда только для владельца бота и ассистентов.")
        return

    args = (msg.text or "").split(maxsplit=1)
    action = args[1].strip().lower().lstrip("-") if len(args) > 1 else ""

    if action in TEST_ON:
        changed = set_maintenance(True)
        head = (
            "🛠 <b>Технические работы включены</b>"
            if changed
            else "🛠 <b>Технические работы уже включены</b>"
        )
        await msg.reply(
            f"{head}\n"
            "Остальные получат «технические работы» вместо ответа.\n"
            f"Доступ оставлен: {_admins_line()}\n"
            "Выключить: /test off"
        )
        return

    if action in TEST_OFF:
        changed = set_maintenance(False)
        head = (
            "✅ <b>Технические работы выключены</b>"
            if changed
            else "✅ <b>Технических работ нет</b>"
        )
        await msg.reply(f"{head}\nБот снова отвечает всем.")
        return

    lines = [
        "🧪 <b>Режим тестирования</b>",
        "",
        f"ТЕХРАБОТЫ = {_since_line()}",
        f"ДОСТУП = {_admins_line()}",
        f"ТВОЙ ID = <code>{user.id}</code>",
        "",
        "<i>/test on — включить техработы</i>",
        "<i>/test off — выключить</i>",
    ]
    if action:
        lines.insert(5, f"<i>Не понял «{escape(action)}» — показываю статус.</i>")
    await msg.reply("\n".join(lines))
