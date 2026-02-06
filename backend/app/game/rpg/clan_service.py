"""
Clan business logic — shared between REST API and Telegram bot.
"""
from typing import Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ...database import async_session
from ...models import Clan, ClanMember, Player, PlayerInventory, Building, JoinRequest
from .map_generator import map_generator, CHUNK_SIZE


async def get_clan_by_chat_id(chat_id: int) -> Optional[dict]:
    """Получить клан по Telegram chat_id."""
    async with async_session() as db:
        result = await db.execute(
            select(Clan).where(Clan.telegram_chat_id == chat_id)
        )
        clan = result.scalar_one_or_none()
        if not clan:
            return None
        return {
            "id": clan.id,
            "name": clan.name,
            "telegram_chat_id": clan.telegram_chat_id,
            "metal": clan.metal, "wood": clan.wood,
            "food": clan.food, "ammo": clan.ammo, "meds": clan.meds,
            "base_x": clan.base_x, "base_y": clan.base_y,
        }


async def create_clan_from_group(
    chat_id: int,
    group_name: str,
    leader_telegram_id: int,
    leader_username: Optional[str] = None
) -> Tuple[bool, str, Optional[int]]:
    """
    Создать клан из Telegram-группы.
    Returns (success, message, clan_id).
    """
    async with async_session() as db:
        # Проверить, не привязана ли группа уже
        result = await db.execute(
            select(Clan).where(Clan.telegram_chat_id == chat_id)
        )
        if result.scalar_one_or_none():
            return False, "База уже создана в этой группе!", None

        # Убедиться что игрок существует
        result = await db.execute(
            select(Player).where(Player.telegram_id == leader_telegram_id)
        )
        player = result.scalar_one_or_none()
        if not player:
            player = Player(telegram_id=leader_telegram_id, username=leader_username)
            db.add(player)
            await db.flush()

        # Проверить, не состоит ли лидер уже в клане
        result = await db.execute(
            select(ClanMember).where(ClanMember.player_id == leader_telegram_id)
        )
        if result.scalar_one_or_none():
            return False, "Ты уже состоишь в другом клане!", None

        # Найти место для базы
        base_cx, base_cy = map_generator.find_base_location()
        base_x = base_cx * CHUNK_SIZE + CHUNK_SIZE // 2
        base_y = base_cy * CHUNK_SIZE + CHUNK_SIZE // 2

        clan = Clan(
            name=group_name,
            telegram_chat_id=chat_id,
            base_x=base_x, base_y=base_y,
        )
        db.add(clan)
        await db.flush()

        member = ClanMember(
            clan_id=clan.id,
            player_id=leader_telegram_id,
            role="leader",
        )
        db.add(member)
        await db.commit()

        return True, f"База «{group_name}» создана!", clan.id


async def add_member_directly(
    chat_id: int,
    player_telegram_id: int,
    player_username: Optional[str] = None,
    role: str = "member"
) -> Tuple[bool, str]:
    """Добавить участника напрямую (для админов)."""
    async with async_session() as db:
        result = await db.execute(
            select(Clan).where(Clan.telegram_chat_id == chat_id)
        )
        clan = result.scalar_one_or_none()
        if not clan:
            return False, "В этой группе нет базы!"

        # Убедиться что игрок существует
        result = await db.execute(
            select(Player).where(Player.telegram_id == player_telegram_id)
        )
        player = result.scalar_one_or_none()
        if not player:
            player = Player(telegram_id=player_telegram_id, username=player_username)
            db.add(player)
            await db.flush()

        # Проверить, не в клане ли уже
        result = await db.execute(
            select(ClanMember).where(ClanMember.player_id == player_telegram_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            if existing.clan_id == clan.id:
                return False, "Ты уже на этой базе!"
            return False, "Ты уже состоишь в другом клане!"

        member = ClanMember(
            clan_id=clan.id,
            player_id=player_telegram_id,
            role=role,
        )
        db.add(member)
        await db.commit()
        return True, "Добро пожаловать на базу!"


async def create_join_request(
    chat_id: int,
    player_telegram_id: int,
    player_username: Optional[str] = None
) -> Tuple[bool, str, Optional[int]]:
    """
    Создать заявку на вступление.
    Returns (success, message, join_request_id).
    """
    async with async_session() as db:
        result = await db.execute(
            select(Clan).where(Clan.telegram_chat_id == chat_id)
        )
        clan = result.scalar_one_or_none()
        if not clan:
            return False, "В этой группе нет базы! Админ должен написать /start", None

        # Убедиться что игрок существует
        result = await db.execute(
            select(Player).where(Player.telegram_id == player_telegram_id)
        )
        player = result.scalar_one_or_none()
        if not player:
            player = Player(telegram_id=player_telegram_id, username=player_username)
            db.add(player)
            await db.flush()

        # Проверить, не состоит ли уже в этом клане
        result = await db.execute(
            select(ClanMember).where(
                ClanMember.player_id == player_telegram_id,
                ClanMember.clan_id == clan.id
            )
        )
        if result.scalar_one_or_none():
            return False, "Ты уже на этой базе!", None

        # Проверить, не состоит ли в другом клане
        result = await db.execute(
            select(ClanMember).where(ClanMember.player_id == player_telegram_id)
        )
        if result.scalar_one_or_none():
            return False, "Ты уже состоишь в другом клане! Сначала покинь его.", None

        # Проверить pending заявку
        result = await db.execute(
            select(JoinRequest).where(
                JoinRequest.clan_id == clan.id,
                JoinRequest.player_id == player_telegram_id,
                JoinRequest.status == "pending"
            )
        )
        if result.scalar_one_or_none():
            return False, "Твоя заявка уже на рассмотрении!", None

        jr = JoinRequest(
            clan_id=clan.id,
            player_id=player_telegram_id,
            chat_id=chat_id,
            status="pending",
        )
        db.add(jr)
        await db.commit()
        await db.refresh(jr)

        return True, "ok", jr.id


async def update_join_request_message(request_id: int, message_id: int):
    """Сохранить message_id для заявки."""
    async with async_session() as db:
        result = await db.execute(
            select(JoinRequest).where(JoinRequest.id == request_id)
        )
        jr = result.scalar_one_or_none()
        if jr:
            jr.message_id = message_id
            await db.commit()


async def resolve_join_request(
    request_id: int,
    approved: bool,
    admin_telegram_id: int
) -> Tuple[bool, str]:
    """
    Одобрить или отклонить заявку.
    Returns (success, message).
    """
    async with async_session() as db:
        result = await db.execute(
            select(JoinRequest).where(JoinRequest.id == request_id)
        )
        jr = result.scalar_one_or_none()
        if not jr or jr.status != "pending":
            return False, "Заявка не найдена или уже обработана"

        jr.resolved_by = admin_telegram_id
        jr.resolved_at = datetime.now(timezone.utc)

        if approved:
            jr.status = "approved"
            member = ClanMember(
                clan_id=jr.clan_id,
                player_id=jr.player_id,
                role="member",
            )
            db.add(member)
            await db.commit()
            return True, "approved"
        else:
            jr.status = "rejected"
            await db.commit()
            return True, "rejected"


async def leave_clan(player_telegram_id: int) -> Tuple[bool, str]:
    """Покинуть клан."""
    async with async_session() as db:
        result = await db.execute(
            select(ClanMember).where(ClanMember.player_id == player_telegram_id)
        )
        membership = result.scalar_one_or_none()
        if not membership:
            return False, "Ты не состоишь ни в одном клане!"

        if membership.role == "leader":
            result = await db.execute(
                select(ClanMember).where(
                    ClanMember.clan_id == membership.clan_id,
                    ClanMember.player_id != player_telegram_id
                )
            )
            others = result.scalars().all()
            if others:
                new_leader = next((m for m in others if m.role == "officer"), others[0])
                new_leader.role = "leader"

        await db.delete(membership)
        await db.commit()
        return True, "Ты покинул базу!"


async def get_clan_info_for_group(chat_id: int) -> Optional[dict]:
    """Получить полную информацию о базе для отображения в группе."""
    async with async_session() as db:
        result = await db.execute(
            select(Clan).where(Clan.telegram_chat_id == chat_id)
        )
        clan = result.scalar_one_or_none()
        if not clan:
            return None

        result = await db.execute(
            select(ClanMember)
            .options(selectinload(ClanMember.player))
            .where(ClanMember.clan_id == clan.id)
        )
        members = []
        for m in result.scalars().all():
            members.append({
                "player_id": m.player_id,
                "username": m.player.username if m.player else "???",
                "role": m.role,
            })

        result = await db.execute(
            select(Building).where(Building.clan_id == clan.id)
        )
        building_count = len(result.scalars().all())

        return {
            "name": clan.name,
            "members": members,
            "member_count": len(members),
            "building_count": building_count,
            "resources": {
                "metal": clan.metal, "wood": clan.wood,
                "food": clan.food, "ammo": clan.ammo, "meds": clan.meds,
            },
        }
