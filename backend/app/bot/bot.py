"""
VELLA Telegram Bot — group integration.
"""
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Register routers
from .handlers import group_router, callback_router
dp.include_router(group_router)
dp.include_router(callback_router)
