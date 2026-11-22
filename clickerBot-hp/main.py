import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database import init_db
from handlers import autosave, click, invest, invite, profile, top
from handlers.invest import investments_watcher
from maintenance import MaintenanceMiddleware  # noqa: E402


logging.basicConfig(level=logging.INFO)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not configured: copy .env.example to .env "
            "and put the token from @BotFather there"
        )

    logging.info("Bot is starting")
    init_db()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dispatcher = Dispatcher()
    # Техработы: пока режим включён, дальше роутеров проходят только админы
    dispatcher.message.middleware(MaintenanceMiddleware())
    dispatcher.include_routers(
        click.router,
        top.router,
        profile.router,
        invest.router,
        invite.router,
        autosave.router,
    )

    invite_task = asyncio.create_task(invite.invite_task(bot))
    investment_task = asyncio.create_task(investments_watcher(bot))
    try:
        await dispatcher.start_polling(bot)
    finally:
        for task in (invite_task, investment_task):
            task.cancel()
        await asyncio.gather(invite_task, investment_task, return_exceptions=True)
        await bot.session.close()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
