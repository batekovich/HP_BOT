#!/usr/bin/env python3
import asyncio
import logging
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import FSInputFile

# ─── Пути ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
CLICKER_DIR = ROOT / "clickerBot-hp"
HPGOVNO_DIR = ROOT / "HPGOVNO"

sys.path.insert(0, str(CLICKER_DIR))
sys.path.insert(0, str(HPGOVNO_DIR))

# ─── Импорты кликера ─────────────────────────────────────────────────────────
from config import BOT_TOKEN  # noqa: E402
from database import init_db  # noqa: E402
from handlers import autosave, click, invest, invite, profile, top  # noqa: E402
from handlers.invest import investments_watcher  # noqa: E402
from maintenance import MaintenanceMiddleware  # noqa: E402

# ─── Логирование ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run")


# ─── Хендлер из HPGOVNO (/hp) ────────────────────────────────────────────────
VIDEO_PATH = HPGOVNO_DIR / "assets" / "hp.mp4"


async def send_hp_video(message: types.Message) -> None:
    """Отправляет видео hp.mp4 по команде /hp."""
    if VIDEO_PATH.is_file():
        video = FSInputFile(VIDEO_PATH)
        await message.answer_video(video=video)
    else:
        await message.reply("Видео hp.mp4 не найдено в HPGOVNO/assets/")


# ─── Главная функция ─────────────────────────────────────────────────────────
async def main() -> None:
    token = BOT_TOKEN
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не задан: скопируй clickerBot-hp/.env.example в "
            "clickerBot-hp/.env и впиши токен от @BotFather"
        )

    logger.info("Инициализация базы данных кликера...")
    init_db()

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    # Техработы: пока режим включён, дальше роутеров проходят только админы
    dp.message.middleware(MaintenanceMiddleware())

    # Регистрируем все роутеры кликера
    dp.include_routers(
        click.router,
        top.router,
        profile.router,
        invest.router,
        invite.router,
        autosave.router,
    )

    # Добавляем хендлер /hp из HPGOVNO
    dp.message.register(send_hp_video, Command("hp"))

    logger.info("Запуск фоновых задач (invite + investments)...")
    invite_task = asyncio.create_task(invite.invite_task(bot))
    investment_task = asyncio.create_task(investments_watcher(bot))

    logger.info("Бот онлайн. Слушаю сообщения (кликер + /hp)...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        for task in (invite_task, investment_task):
            task.cancel()
        await asyncio.gather(invite_task, investment_task, return_exceptions=True)
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")
    except Exception as e:
        logger.exception("Критическая ошибка: %s", e)