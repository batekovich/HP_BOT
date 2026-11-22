import asyncio
import hashlib
import json
import logging
import os
import time

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

# Токен держим в переменной окружения, а не в коде
TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_PATH = os.path.join(BASE_DIR, "assets", "hp.mp4")
COOLDOWN_FILE = os.path.join(BASE_DIR, "cooldowns.json")
COOLDOWN_SECONDS = 960

# Удаление своих сообщений через 12 часов
DELETE_AFTER_SECONDS = 12 * 60 * 60  # 43200

# Метка версии: по ней сразу видно, что запущен именно этот файл
VERSION = "v6-cd960-autodel-fixed916"

# Текст при повторной команде. {minutes} и {seconds} подставятся сами
COOLDOWN_MESSAGE = "ПИДАР! ПАДАЖИ И НАПИШИ ХП ЧЕРЕЗ {minutes} МИН. {seconds} СЕК."

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

STARTED_AT = int(time.time())

# Кулдауны в памяти + на диске
_cooldowns_cache = {}


def read_cooldowns_file() -> dict:
    try:
        with open(COOLDOWN_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): int(v) for k, v in data.items()}
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, ValueError, TypeError, OSError) as e:
        log.warning("Кулдауны не прочитаны (%s): %s", COOLDOWN_FILE, e)
        return {}


def load_cooldowns() -> dict:
    # Всегда читаем с диска и обновляем кэш — так кулдаун не теряется
    disk = read_cooldowns_file()
    if disk:
        _cooldowns_cache.clear()
        _cooldowns_cache.update(disk)
        return dict(disk)
    return dict(_cooldowns_cache)


def save_cooldowns(data: dict) -> None:
    _cooldowns_cache.clear()
    _cooldowns_cache.update(data)
    tmp = COOLDOWN_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, COOLDOWN_FILE)
        log.info("Кулдауны сохранены: %s", data)
    except OSError as e:
        log.error("Не удалось записать %s: %s", COOLDOWN_FILE, e)


def source_md5() -> str:
    try:
        with open(file, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except OSError as e:
        return f"не прочитать ({e})"


def human_time(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


async def delete_later(chat_id: int, message_id: int) -> None:
    """Удаляет сообщение бота через 12 часов. Только свои сообщения."""
    try:
        await asyncio.sleep(DELETE_AFTER_SECONDS)
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        log.info("Удалено своё сообщение %s в чате %s", message_id, chat_id)
    except Exception as e:
        # Сообщение уже удалено, чат недоступен и т.п. — просто логируем
        log.warning("Не удалось удалить сообщение %s в чате %s: %s", message_id, chat_id, e)


def schedule_delete(msg: types.Message) -> None:
    """Планирует удаление только своего сообщения через 12 часов."""
    if msg is None:
        return
    asyncio.create_task(delete_later(msg.chat.id, msg.message_id))


@dp.message(Command("hp"))
async def send_video_handler(message: types.Message):
    if not message.from_user:
        return

    user_id = str(message.from_user.id)
    now = int(time.time())

    cooldowns = load_cooldowns()
    last_time = cooldowns.get(user_id)

    # 1. Проверяем кулдаун
    if last_time is not None:
        time_passed = now - last_time
        if time_passed < COOLDOWN_SECONDS:
            time_left = COOLDOWN_SECONDS - time_passed
            minutes_left, seconds_left = divmod(time_left, 60)
            sent = await message.answer(
                COOLDOWN_MESSAGE.format(minutes=minutes_left, seconds=seconds_left)
            )
            schedule_delete(sent)
            log.info("/hp в кулдауне у %s, осталось %s сек.", user_id, time_left)
            return

    # 2. Если файл видео отсутствует, пишем лог и выходим
    if not os.path.exists(VIDEO_PATH):
        log.error("Файл видео не найден по пути: %s", VIDEO_PATH)
        return

    # 3. Отправляем видео с принудительными размерами 9:16 (720x1280)
    try:
        video_file = FSInputFile(VIDEO_PATH)
        sent_video = await message.answer_video(
            video=video_file,
            width=720,
            height=1280
        )
        # Планируем автоудаление видео через 12 часов
        schedule_delete(sent_video)
        
        # Обновляем и сохраняем кулдаун
        cooldowns[user_id] = now
        save_cooldowns(cooldowns)
        log.info("Видео успешно отправлено пользователю %s, кулдаун обновлен.", user_id)
    except Exception as e:
        log.error("Ошибка при отправке видео: %s", e)

# Ниже должен идти запуск бота (например, dp.start_polling(bot)), 
# оставьте его таким, каким он был в вашем оригинальном файле.
