"""
Clan REST API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ...database import get_db
from ...models import Clan, ClanMember, Player, PlayerInventory
from ...auth import validate_telegram_data

router = APIRouter(prefix="/api/clan", tags=["clan"])


def _get_user(init_data: str) -> dict:
    user = validate_telegram_data(init_data)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid auth")
    return user


@router.get("")
async def get_my_clan(
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get player's clan info"""
    user = _get_user(init_data)
    telegram_id = user["id"]

    result = await db.execute(
        select(ClanMember)
        .options(selectinload(ClanMember.clan))
        .where(ClanMember.player_id == telegram_id)
    )
    membership = result.scalar_one_or_none()

    if not membership:
        return {"clan": None}

    clan = membership.clan

    # Get members
    result = await db.execute(
        select(ClanMember)
        .options(selectinload(ClanMember.player))
        .where(ClanMember.clan_id == clan.id)
    )
    members = []
    for m in result.scalars().all():
        members.append({
            "player_id": m.player_id,
            "username": m.player.username if m.player else None,
            "role": m.role,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
        })

    return {
        "clan": {
            "id": clan.id,
            "name": clan.name,
            "telegram_chat_id": clan.telegram_chat_id,
            "resources": {
                "metal": clan.metal,
                "wood": clan.wood,
                "food": clan.food,
                "ammo": clan.ammo,
                "meds": clan.meds,
            },
            "base_x": clan.base_x,
            "base_y": clan.base_y,
            "members": members,
        },
        "my_role": membership.role,
    }


@router.post("/create")
async def create_clan(
    name: str,
    telegram_chat_id: int,
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Create a new clan linked to a Telegram group"""
    user = _get_user(init_data)
    telegram_id = user["id"]

    # Check not already in a clan
    result = await db.execute(
        select(ClanMember).where(ClanMember.player_id == telegram_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already in a clan")

    # Check chat ID not taken
    result = await db.execute(
        select(Clan).where(Clan.telegram_chat_id == telegram_chat_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Chat already linked to a clan")

    # Find base location
    from .map_generator import map_generator
    base_cx, base_cy = map_generator.find_base_location()
    from .map_generator import CHUNK_SIZE
    base_x = base_cx * CHUNK_SIZE + CHUNK_SIZE // 2
    base_y = base_cy * CHUNK_SIZE + CHUNK_SIZE // 2

    clan = Clan(
        name=name,
        telegram_chat_id=telegram_chat_id,
        base_x=base_x,
        base_y=base_y,
    )
    db.add(clan)
    await db.flush()

    # Add creator as leader
    member = ClanMember(
        clan_id=clan.id,
        player_id=telegram_id,
        role="leader",
    )
    db.add(member)
    await db.commit()

    return {"success": True, "clan_id": clan.id, "name": clan.name}


@router.post("/join")
async def join_clan(
    clan_id: int,
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Join an existing clan"""
    user = _get_user(init_data)
    telegram_id = user["id"]

    # Check not already in a clan
    result = await db.execute(
        select(ClanMember).where(ClanMember.player_id == telegram_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already in a clan")

    # Check clan exists
    result = await db.execute(select(Clan).where(Clan.id == clan_id))
    clan = result.scalar_one_or_none()
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")

    member = ClanMember(
        clan_id=clan_id,
        player_id=telegram_id,
        role="member",
    )
    db.add(member)
    await db.commit()

    return {"success": True, "clan_name": clan.name}


@router.delete("/leave")
async def leave_clan(
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Leave current clan"""
    user = _get_user(init_data)
    telegram_id = user["id"]

    result = await db.execute(
        select(ClanMember).where(ClanMember.player_id == telegram_id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=400, detail="Not in a clan")

    if membership.role == "leader":
        # Check if there are other members
        result = await db.execute(
            select(ClanMember).where(
                ClanMember.clan_id == membership.clan_id,
                ClanMember.player_id != telegram_id
            )
        )
        others = result.scalars().all()
        if others:
            # Promote first officer or member to leader
            new_leader = next((m for m in others if m.role == "officer"), others[0])
            new_leader.role = "leader"

    await db.delete(membership)
    await db.commit()

    return {"success": True}


@router.get("/{clan_id}")
async def get_clan_details(
    clan_id: int,
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific clan"""
    _get_user(init_data)

    result = await db.execute(select(Clan).where(Clan.id == clan_id))
    clan = result.scalar_one_or_none()
    if not clan:
        raise HTTPException(status_code=404, detail="Clan not found")

    result = await db.execute(
        select(ClanMember)
        .options(selectinload(ClanMember.player))
        .where(ClanMember.clan_id == clan_id)
    )
    members = []
    for m in result.scalars().all():
        members.append({
            "player_id": m.player_id,
            "username": m.player.username if m.player else None,
            "role": m.role,
        })

    return {
        "id": clan.id,
        "name": clan.name,
        "resources": {
            "metal": clan.metal,
            "wood": clan.wood,
            "food": clan.food,
            "ammo": clan.ammo,
            "meds": clan.meds,
        },
        "members": members,
        "member_count": len(members),
    }


@router.post("/deposit")
async def deposit_resources(
    metal: int = 0,
    wood: int = 0,
    food: int = 0,
    ammo: int = 0,
    meds: int = 0,
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Deposit resources from player inventory to clan"""
    user = _get_user(init_data)
    telegram_id = user["id"]

    # Get membership
    result = await db.execute(
        select(ClanMember).where(ClanMember.player_id == telegram_id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=400, detail="Not in a clan")

    # Get player inventory
    result = await db.execute(
        select(PlayerInventory).where(PlayerInventory.player_id == telegram_id)
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=400, detail="No inventory")

    # Validate amounts
    if metal > inv.metal or wood > inv.wood or food > inv.food or ammo > inv.ammo or meds > inv.meds:
        raise HTTPException(status_code=400, detail="Not enough resources")

    if metal < 0 or wood < 0 or food < 0 or ammo < 0 or meds < 0:
        raise HTTPException(status_code=400, detail="Invalid amounts")

    # Transfer
    result = await db.execute(select(Clan).where(Clan.id == membership.clan_id))
    clan = result.scalar_one_or_none()

    inv.metal -= metal
    inv.wood -= wood
    inv.food -= food
    inv.ammo -= ammo
    inv.meds -= meds

    clan.metal += metal
    clan.wood += wood
    clan.food += food
    clan.ammo += ammo
    clan.meds += meds

    await db.commit()

    return {"success": True}


@router.post("/kick")
async def kick_member(
    player_id: int,
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Kick a member (leader or officer only)"""
    user = _get_user(init_data)
    telegram_id = user["id"]

    # Get kicker's membership
    result = await db.execute(
        select(ClanMember).where(ClanMember.player_id == telegram_id)
    )
    kicker = result.scalar_one_or_none()
    if not kicker or kicker.role not in ("leader", "officer"):
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get target
    result = await db.execute(
        select(ClanMember).where(
            ClanMember.player_id == player_id,
            ClanMember.clan_id == kicker.clan_id
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")

    if target.role == "leader":
        raise HTTPException(status_code=403, detail="Cannot kick the leader")

    if target.role == "officer" and kicker.role != "leader":
        raise HTTPException(status_code=403, detail="Only leader can kick officers")

    await db.delete(target)
    await db.commit()

    return {"success": True}


@router.post("/promote")
async def promote_member(
    player_id: int,
    role: str = "officer",
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Promote a member (leader only)"""
    user = _get_user(init_data)
    telegram_id = user["id"]

    if role not in ("officer", "member"):
        raise HTTPException(status_code=400, detail="Invalid role")

    # Get promoter's membership
    result = await db.execute(
        select(ClanMember).where(ClanMember.player_id == telegram_id)
    )
    promoter = result.scalar_one_or_none()
    if not promoter or promoter.role != "leader":
        raise HTTPException(status_code=403, detail="Only leader can promote")

    # Get target
    result = await db.execute(
        select(ClanMember).where(
            ClanMember.player_id == player_id,
            ClanMember.clan_id == promoter.clan_id
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")

    target.role = role
    await db.commit()

    return {"success": True, "new_role": role}
