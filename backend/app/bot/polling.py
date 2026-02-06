"""
Start bot polling as background asyncio task.
"""
import logging
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats

from .bot import bot, dp

logger = logging.getLogger(__name__)


async def set_bot_commands():
    """Установить команды бота для групповых чатов."""
    commands = [
        BotCommand(command="start", description="Создать базу (только админ)"),
        BotCommand(command="join", description="Вступить на базу"),
        BotCommand(command="leave", description="Покинуть базу"),
        BotCommand(command="base", description="Информация о базе"),
        BotCommand(command="play", description="Открыть игру"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeAllGroupChats())


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
