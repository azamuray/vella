"""
Bot command handlers for Telegram group integration.
"""
import os
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ChatMemberAdministrator, ChatMemberOwner,
)
from aiogram.filters import Command
from aiogram.enums import ChatType

from ..game.rpg.clan_service import (
    create_clan_from_group,
    create_join_request,
    update_join_request_message,
    resolve_join_request,
    leave_clan,
    get_clan_info_for_group,
    get_clan_by_chat_id,
    add_member_directly,
)

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://vella.lovza.ru")

group_router = Router()
callback_router = Router()


# ========== Helpers ==========

async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Проверить что user_id является админом чата."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except Exception:
        return False


# ========== /start — Создание базы ==========

@group_router.message(Command("start"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_start(message: Message, bot: Bot):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_chat_admin(bot, chat_id, user_id):
        await message.reply(
            "Только админ группы может создать базу!\n"
            "Попроси админа написать /start"
        )
        return

    existing = await get_clan_by_chat_id(chat_id)
    if existing:
        await message.reply(
            f"База <b>{existing['name']}</b> уже создана!\n\n"
            f"Участники могут написать /join чтобы вступить.\n"
            f"Напиши /base чтобы увидеть информацию о базе."
        )
        return

    group_name = message.chat.title or f"Base #{abs(chat_id) % 10000}"
    success, msg, clan_id = await create_clan_from_group(
        chat_id=chat_id,
        group_name=group_name,
        leader_telegram_id=user_id,
        leader_username=message.from_user.username,
    )

    if success:
        await message.reply(
            f"<b>{msg}</b>\n\n"
            f"Ты — лидер базы.\n\n"
            f"Участники группы могут написать /join чтобы вступить.\n"
            f"Напиши /play чтобы открыть игру."
        )
    else:
        await message.reply(f"Ошибка: {msg}")


# ========== /join — Заявка на вступление ==========

@group_router.message(Command("join"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_join(message: Message, bot: Bot):
    user_id = message.from_user.id
    chat_id = message.chat.id
    username = message.from_user.username or message.from_user.first_name

    # Админ — добавить как офицера напрямую
    if await is_chat_admin(bot, chat_id, user_id):
        success, msg = await add_member_directly(
            chat_id=chat_id,
            player_telegram_id=user_id,
            player_username=username,
            role="officer",
        )
        if success:
            await message.reply(f"Добро пожаловать на базу, офицер! Напиши /play чтобы играть.")
        else:
            await message.reply(msg)
        return

    # Обычный юзер — заявка с кнопками
    success, msg, request_id = await create_join_request(
        chat_id=chat_id,
        player_telegram_id=user_id,
        player_username=username,
    )

    if not success:
        await message.reply(msg)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Принять",
                callback_data=f"join_approve:{request_id}:{user_id}"
            ),
            InlineKeyboardButton(
                text="Отклонить",
                callback_data=f"join_reject:{request_id}:{user_id}"
            ),
        ]
    ])

    sent = await message.reply(
        f"<b>{username}</b> хочет вступить на базу!\n\n"
        f"Админ, прими решение:",
        reply_markup=keyboard,
    )

    await update_join_request_message(request_id, sent.message_id)


# ========== Callbacks: Принять/Отклонить ==========

@callback_router.callback_query(F.data.startswith("join_approve:"))
async def cb_approve(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    request_id = int(parts[1])

    if not await is_chat_admin(bot, callback.message.chat.id, callback.from_user.id):
        await callback.answer("Только админ может принимать заявки!", show_alert=True)
        return

    success, result = await resolve_join_request(
        request_id=request_id,
        approved=True,
        admin_telegram_id=callback.from_user.id,
    )

    if not success:
        await callback.answer(result, show_alert=True)
        return

    await callback.message.edit_text(
        "Заявка принята! Добро пожаловать на базу!\n"
        "Напиши /play чтобы открыть игру."
    )
    await callback.answer("Принято!")


@callback_router.callback_query(F.data.startswith("join_reject:"))
async def cb_reject(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    request_id = int(parts[1])

    if not await is_chat_admin(bot, callback.message.chat.id, callback.from_user.id):
        await callback.answer("Только админ может отклонять заявки!", show_alert=True)
        return

    success, result = await resolve_join_request(
        request_id=request_id,
        approved=False,
        admin_telegram_id=callback.from_user.id,
    )

    if not success:
        await callback.answer(result, show_alert=True)
        return

    await callback.message.edit_text("Заявка отклонена.")
    await callback.answer("Отклонено")


# ========== /leave — Покинуть базу ==========

@group_router.message(Command("leave"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_leave(message: Message):
    success, msg = await leave_clan(message.from_user.id)
    await message.reply(msg)


# ========== /base — Информация о базе ==========

@group_router.message(Command("base"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_base(message: Message):
    info = await get_clan_info_for_group(message.chat.id)

    if not info:
        await message.reply(
            "В этой группе нет базы!\n"
            "Админ может создать её командой /start"
        )
        return

    role_emoji = {"leader": "👑", "officer": "⭐", "member": "🔫"}
    members_text = "\n".join(
        f"  {role_emoji.get(m['role'], '•')} @{m['username']} ({m['role']})"
        for m in info["members"]
    )

    res = info["resources"]

    await message.reply(
        f"<b>🏚 База: {info['name']}</b>\n\n"
        f"<b>Ресурсы:</b>\n"
        f"  🔩 Металл: {res['metal']}\n"
        f"  🪵 Дерево: {res['wood']}\n"
        f"  🍖 Еда: {res['food']}\n"
        f"  🔫 Патроны: {res['ammo']}\n"
        f"  💊 Медикаменты: {res['meds']}\n\n"
        f"<b>Участники ({info['member_count']}):</b>\n"
        f"{members_text}\n\n"
        f"<b>Зданий построено:</b> {info['building_count']}\n\n"
        f"Напиши /play чтобы открыть игру!"
    )


# ========== /play — Открыть WebApp ==========

@group_router.message(Command("play"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_play(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎮 Играть в VELLA",
                url=WEBAPP_URL,
            )
        ]
    ])

    await message.reply(
        "Нажми кнопку чтобы открыть игру!",
        reply_markup=keyboard,
    )
