"""
Start bot polling as background asyncio task.
"""
import logging
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeChat

from .bot import bot, dp

logger = logging.getLogger(__name__)


async def set_bot_commands():
    """Установить команды бота для групповых чатов и админа."""
    import os

    commands = [
        BotCommand(command="start", description="Создать базу (только админ)"),
        BotCommand(command="join", description="Вступить на базу"),
        BotCommand(command="leave", description="Покинуть базу"),
        BotCommand(command="base", description="Информация о базе"),
        BotCommand(command="play", description="Открыть игру"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeAllGroupChats())

    # Register private commands for admin
    admin_id = int(os.getenv("ADMIN_TELEGRAM_ID") or 0)
    if admin_id:
        try:
            admin_commands = [
                BotCommand(command="stars", description="Топ-3 и балансы звёзд"),
            ]
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            logger.warning(f"[Bot] Could not set admin commands: {e}")


async def start_polling():
    """Запустить long polling бота."""
    logger.info("[Bot] Starting polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    await set_bot_commands()
    logger.info("[Bot] Commands registered, polling started")
    await dp.start_polling(bot)


async def stop_polling():
    """Остановить polling."""
    logger.info("[Bot] Stopping polling...")
    await dp.stop_polling()
    await bot.session.close()
