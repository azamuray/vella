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
from sqlalchemy import select, desc

from ..database import async_session
from ..models import Player, StarRewardLog
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
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

group_router = Router()
callback_router = Router()
private_router = Router()


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


# ========== /stars — Топ-3 и балансы (только админ, в ЛС) ==========

@private_router.message(Command("stars"), F.chat.type == ChatType.PRIVATE)
async def cmd_stars(message: Message):
    if not ADMIN_TELEGRAM_ID or message.from_user.id != ADMIN_TELEGRAM_ID:
        return

    async with async_session() as db:
        result = await db.execute(
            select(Player)
            .where(Player.highest_wave > 0)
            .order_by(desc(Player.highest_wave), desc(Player.total_kills))
            .limit(3)
        )
        top_players = result.scalars().all()

    if not top_players:
        await message.reply("Пока нет игроков в лидерборде.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, p in enumerate(top_players):
        name = f"@{p.username}" if p.username else f"id:{p.telegram_id}"
        link = f'<a href="tg://user?id={p.telegram_id}">{name}</a>'
        balance = round(p.star_balance or 0, 2)
        earned = p.total_stars_earned or 0
        lines.append(
            f"{medals[i]} {link}\n"
            f"   Волна: <b>{p.highest_wave}</b> | Kills: <b>{p.total_kills}</b>\n"
            f"   Баланс: <b>{balance}</b> ⭐ | Всего отправлено: <b>{earned}</b> ⭐"
        )

    await message.reply(
        "⭐ <b>Топ-3 игроков (награды за звёзды)</b>\n\n"
        + "\n\n".join(lines)
    )


# ========== Callback: Подтверждение отправки звёзд ==========

@callback_router.callback_query(F.data.startswith("stars_confirm:"))
async def cb_stars_confirm(callback: CallbackQuery):
    if not ADMIN_TELEGRAM_ID or callback.from_user.id != ADMIN_TELEGRAM_ID:
        await callback.answer("Только админ может подтверждать!", show_alert=True)
        return

    parts = callback.data.split(":")
    log_id = int(parts[1])
    player_id = int(parts[2])
    amount = int(parts[3])

    async with async_session() as db:
        # Update log status
        result = await db.execute(
            select(StarRewardLog).where(StarRewardLog.id == log_id)
        )
        log = result.scalar_one_or_none()

        if not log:
            await callback.answer("Запись не найдена!", show_alert=True)
            return

        if log.status == "sent":
            await callback.answer("Уже подтверждено!", show_alert=True)
            return

        log.status = "sent"

        # Update player balance
        result = await db.execute(
            select(Player).where(Player.telegram_id == player_id)
        )
        player = result.scalar_one_or_none()

        if player:
            player.star_balance = max(0, (player.star_balance or 0) - amount)
            player.total_stars_earned = (player.total_stars_earned or 0) + amount

        await db.commit()

    # Update the button text in the message
    name = f"@{player.username}" if player and player.username else f"id:{player_id}"

    # Rebuild keyboard: mark this button as confirmed
    if callback.message and callback.message.reply_markup:
        new_buttons = []
        for row in callback.message.reply_markup.inline_keyboard:
            new_row = []
            for btn in row:
                if btn.callback_data == callback.data:
                    new_row.append(InlineKeyboardButton(
                        text=f"✅ {name} — {amount}⭐ (отправлено)",
                        callback_data=f"stars_done:{log_id}",
                    ))
                else:
                    new_row.append(btn)
            new_buttons.append(new_row)

        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=new_buttons)
        )

    await callback.answer(f"Отправка {amount}⭐ для {name} подтверждена!")
