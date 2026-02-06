"""
Building REST API routes for clan bases.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ...database import get_db
from ...models import Clan, ClanMember, Building, BuildingType
from ...auth import validate_telegram_data
from .base_grid import can_place_building, build_grid_from_buildings

router = APIRouter(prefix="/api/buildings", tags=["buildings"])


def _get_user(init_data: str) -> dict:
    user = validate_telegram_data(init_data)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid auth")
    return user


async def _get_clan_membership(telegram_id: int, db: AsyncSession):
    """Get player's clan membership or raise 400."""
    result = await db.execute(
        select(ClanMember).where(ClanMember.player_id == telegram_id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=400, detail="Not in a clan")
    return membership


@router.get("/types")
async def get_building_types(
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get all building types"""
    _get_user(init_data)

    result = await db.execute(select(BuildingType))
    types = []
    for bt in result.scalars().all():
        types.append({
            "id": bt.id,
            "code": bt.code,
            "name": bt.name,
            "category": bt.category,
            "width": bt.width,
            "height": bt.height,
            "max_hp": bt.max_hp,
            "produces_resource": bt.produces_resource,
            "production_rate": bt.production_rate,
            "damage": bt.damage,
            "fire_rate": bt.fire_rate,
            "attack_range": bt.attack_range,
            "cost_metal": bt.cost_metal,
            "cost_wood": bt.cost_wood,
            "cost_food": bt.cost_food,
            "build_time": bt.build_time,
        })

    return types


@router.get("")
async def get_clan_buildings(
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get buildings for player's clan"""
    user = _get_user(init_data)
    membership = await _get_clan_membership(user["id"], db)

    result = await db.execute(
        select(Building)
        .options(selectinload(Building.building_type))
        .where(Building.clan_id == membership.clan_id)
    )

    buildings = []
    for b in result.scalars().all():
        bt = b.building_type
        is_built = b.build_complete and b.build_complete <= datetime.utcnow()

        # Calculate produced resources
        produced = 0
        if bt.produces_resource and bt.production_rate > 0 and is_built:
            hours_since = (datetime.utcnow() - b.last_collected).total_seconds() / 3600
            produced = int(hours_since * bt.production_rate)

        buildings.append({
            "id": b.id,
            "type_code": bt.code,
            "type_name": bt.name,
            "category": bt.category,
            "grid_x": b.grid_x,
            "grid_y": b.grid_y,
            "width": bt.width,
            "height": bt.height,
            "hp": b.hp,
            "max_hp": bt.max_hp,
            "level": b.level,
            "is_active": b.is_active,
            "is_built": is_built,
            "build_progress": _build_progress(b),
            "produces_resource": bt.produces_resource,
            "produced_amount": produced,
        })

    return buildings


def _build_progress(building: Building) -> float:
    """Calculate build progress 0.0 - 1.0"""
    if not building.build_started or not building.build_complete:
        return 1.0
    now = datetime.utcnow()
    if now >= building.build_complete:
        return 1.0
    total = (building.build_complete - building.build_started).total_seconds()
    elapsed = (now - building.build_started).total_seconds()
    return min(1.0, elapsed / total) if total > 0 else 1.0


@router.post("/place")
async def place_building(
    building_type_code: str,
    grid_x: int,
    grid_y: int,
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Place a building on the clan base grid"""
    user = _get_user(init_data)
    membership = await _get_clan_membership(user["id"], db)

    if membership.role not in ("leader", "officer"):
        raise HTTPException(status_code=403, detail="Only leader/officer can build")

    # Get building type
    result = await db.execute(
        select(BuildingType).where(BuildingType.code == building_type_code)
    )
    bt = result.scalar_one_or_none()
    if not bt:
        raise HTTPException(status_code=404, detail="Building type not found")

    # Get clan
    result = await db.execute(select(Clan).where(Clan.id == membership.clan_id))
    clan = result.scalar_one_or_none()

    # Check resources
    if clan.metal < bt.cost_metal or clan.wood < bt.cost_wood or clan.food < bt.cost_food:
        raise HTTPException(status_code=400, detail="Not enough resources")

    # Get existing buildings for grid check
    result = await db.execute(
        select(Building)
        .options(selectinload(Building.building_type))
        .where(Building.clan_id == clan.id)
    )
    existing = []
    for b in result.scalars().all():
        existing.append({
            "id": b.id,
            "grid_x": b.grid_x,
            "grid_y": b.grid_y,
            "width": b.building_type.width,
            "height": b.building_type.height,
        })

    grid = build_grid_from_buildings(existing)

    if not can_place_building(grid, grid_x, grid_y, bt.width, bt.height):
        raise HTTPException(status_code=400, detail="Cannot place here — overlaps or out of bounds")

    # Deduct resources
    clan.metal -= bt.cost_metal
    clan.wood -= bt.cost_wood
    clan.food -= bt.cost_food

    # Create building
    now = datetime.utcnow()
    building = Building(
        clan_id=clan.id,
        building_type_id=bt.id,
        grid_x=grid_x,
        grid_y=grid_y,
        hp=bt.max_hp,
        build_started=now,
        build_complete=now + timedelta(seconds=bt.build_time),
    )
    db.add(building)
    await db.commit()

    return {"success": True, "building_id": building.id}


@router.post("/collect")
async def collect_production(
    building_id: int,
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Collect resources from a production building"""
    user = _get_user(init_data)
    membership = await _get_clan_membership(user["id"], db)

    result = await db.execute(
        select(Building)
        .options(selectinload(Building.building_type))
        .where(Building.id == building_id, Building.clan_id == membership.clan_id)
    )
    building = result.scalar_one_or_none()
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    bt = building.building_type
    if not bt.produces_resource or bt.production_rate <= 0:
        raise HTTPException(status_code=400, detail="Not a production building")

    # Check if built
    if building.build_complete and building.build_complete > datetime.utcnow():
        raise HTTPException(status_code=400, detail="Still under construction")

    # Calculate produced
    hours_since = (datetime.utcnow() - building.last_collected).total_seconds() / 3600
    produced = int(hours_since * bt.production_rate)

    if produced <= 0:
        raise HTTPException(status_code=400, detail="Nothing to collect yet")

    # Add to clan
    result = await db.execute(select(Clan).where(Clan.id == membership.clan_id))
    clan = result.scalar_one_or_none()

    resource = bt.produces_resource
    current = getattr(clan, resource, 0)
    setattr(clan, resource, current + produced)

    building.last_collected = datetime.utcnow()
    await db.commit()

    return {
        "success": True,
        "resource": resource,
        "amount": produced,
        "clan_total": getattr(clan, resource),
    }


@router.delete("/{building_id}")
async def demolish_building(
    building_id: int,
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Demolish a building (leader/officer only)"""
    user = _get_user(init_data)
    membership = await _get_clan_membership(user["id"], db)

    if membership.role not in ("leader", "officer"):
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(
        select(Building).where(
            Building.id == building_id,
            Building.clan_id == membership.clan_id
        )
    )
    building = result.scalar_one_or_none()
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    await db.delete(building)
    await db.commit()

    return {"success": True}
