"""
Database operations for open world — load/save player state, chunks, zombies.
"""
from typing import Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...models import WorldState, PlayerInventory, MapChunk, WorldZombie, Clan, ClanMember, Building, BuildingType
from ...database import async_session
from .map_generator import map_generator, CHUNK_SIZE, TILE_SIZE


async def get_or_create_world_state(player_id: int) -> dict:
    """Load or create world state for a player. Returns dict with position, hp, inventory."""
    async with async_session() as db:
        # World state
        result = await db.execute(
            select(WorldState).where(WorldState.player_id == player_id)
        )
        ws = result.scalar_one_or_none()

        if not ws:
            # Find safe spawn position in chunk (0, 0)
            spawn_x, spawn_y = map_generator.get_safe_spawn_position(0, 0)
            ws = WorldState(
                player_id=player_id,
                x=spawn_x, y=spawn_y,
                hp=100, max_hp=100, is_alive=True
            )
            db.add(ws)
            await db.commit()
            await db.refresh(ws)

        # Inventory
        result = await db.execute(
            select(PlayerInventory).where(PlayerInventory.player_id == player_id)
        )
        inv = result.scalar_one_or_none()

        if not inv:
            inv = PlayerInventory(player_id=player_id)
            db.add(inv)
            await db.commit()
            await db.refresh(inv)

        return {
            "x": ws.x,
            "y": ws.y,
            "hp": ws.hp,
            "max_hp": ws.max_hp,
            "is_alive": ws.is_alive,
            "inventory": {
                "metal": inv.metal,
                "wood": inv.wood,
                "food": inv.food,
                "ammo": inv.ammo,
                "meds": inv.meds,
            },
            "equipped_weapon": inv.equipped_weapon,
            "equipped_clothing": inv.equipped_clothing,
        }


async def save_world_state(player_id: int, x: float, y: float, hp: int,
                            is_alive: bool, inventory: dict, weapon_code: str,
                            clothing: dict = None):
    """Save player's world state to DB"""
    async with async_session() as db:
        result = await db.execute(
            select(WorldState).where(WorldState.player_id == player_id)
        )
        ws = result.scalar_one_or_none()
        if ws:
            ws.x = x
            ws.y = y
            ws.hp = hp
            ws.is_alive = is_alive

        result = await db.execute(
            select(PlayerInventory).where(PlayerInventory.player_id == player_id)
        )
        inv = result.scalar_one_or_none()
        if inv:
            inv.metal = inventory.get("metal", 0)
            inv.wood = inventory.get("wood", 0)
            inv.food = inventory.get("food", 0)
            inv.ammo = inventory.get("ammo", 0)
            inv.meds = inventory.get("meds", 0)
            inv.equipped_weapon = weapon_code
            if clothing is not None:
                inv.equipped_clothing = clothing

        await db.commit()


async def load_chunk_from_db(chunk_x: int, chunk_y: int) -> Optional[dict]:
    """Load a chunk from DB. Returns None if not generated yet."""
    async with async_session() as db:
        result = await db.execute(
            select(MapChunk).where(
                MapChunk.chunk_x == chunk_x,
                MapChunk.chunk_y == chunk_y
            )
        )
        chunk = result.scalar_one_or_none()
        if not chunk:
            return None

        return {
            "terrain": chunk.terrain,
            "resources": chunk.resources or [],
            "spawn_points": chunk.spawn_points or [],
            "seed": chunk.seed,
        }


async def save_chunk_to_db(chunk_x: int, chunk_y: int, terrain: list,
                            resources: list, spawn_points: list, seed: int):
    """Save generated chunk to DB"""
    async with async_session() as db:
        result = await db.execute(
            select(MapChunk).where(
                MapChunk.chunk_x == chunk_x,
                MapChunk.chunk_y == chunk_y
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return  # Already saved

        chunk = MapChunk(
            chunk_x=chunk_x,
            chunk_y=chunk_y,
            terrain=terrain,
            resources=resources,
            spawn_points=spawn_points,
            seed=seed,
        )
        db.add(chunk)
        await db.commit()


async def load_chunk_zombies(chunk_x: int, chunk_y: int) -> list:
    """Load alive zombies for a chunk from DB"""
    async with async_session() as db:
        result = await db.execute(
            select(WorldZombie).where(
                WorldZombie.chunk_x == chunk_x,
                WorldZombie.chunk_y == chunk_y,
                WorldZombie.is_alive == True
            )
        )
        zombies = []
        for wz in result.scalars().all():
            zombies.append({
                "db_id": wz.id,
                "x": wz.x,
                "y": wz.y,
                "type": wz.zombie_type,
                "hp": wz.hp,
            })
        return zombies


def _find_clans_in_chunk(chunk_x: int, chunk_y: int):
    """Build a query filter for clans whose base is within this chunk.
    Clan.base_x/base_y store world coordinates, so we check the range."""
    world_min_x = chunk_x * CHUNK_SIZE
    world_max_x = (chunk_x + 1) * CHUNK_SIZE
    world_min_y = chunk_y * CHUNK_SIZE
    world_max_y = (chunk_y + 1) * CHUNK_SIZE
    return and_(
        Clan.base_x >= world_min_x, Clan.base_x < world_max_x,
        Clan.base_y >= world_min_y, Clan.base_y < world_max_y,
    )


async def load_clan_bases_for_chunk(chunk_x: int, chunk_y: int) -> list:
    """Load clan base positions for clans whose base is in this chunk."""
    async with async_session() as db:
        result = await db.execute(
            select(Clan).where(_find_clans_in_chunk(chunk_x, chunk_y))
        )
        clans = result.scalars().all()
        return [{"x": c.base_x, "y": c.base_y} for c in clans]


async def load_turrets_for_chunk(chunk_x: int, chunk_y: int) -> list:
    """Load built turrets for clans whose base is at this chunk."""
    async with async_session() as db:
        result = await db.execute(
            select(Clan).where(_find_clans_in_chunk(chunk_x, chunk_y))
        )
        clans = result.scalars().all()
        if not clans:
            return []

        turrets = []
        now = datetime.now(timezone.utc)
        for clan in clans:
            result = await db.execute(
                select(Building).where(
                    Building.clan_id == clan.id,
                    Building.is_active == True
                ).options(selectinload(Building.building_type))
            )
            for building in result.scalars().all():
                bt = building.building_type
                if not bt or bt.category != "defense" or bt.damage <= 0:
                    continue
                if building.build_complete is None:
                    continue
                if building.build_complete.replace(tzinfo=timezone.utc) > now:
                    continue

                # Grid is 16x16 centered on clan base position
                world_x = clan.base_x - 8 * TILE_SIZE + building.grid_x * TILE_SIZE + (bt.width * TILE_SIZE) / 2
                world_y = clan.base_y - 8 * TILE_SIZE + building.grid_y * TILE_SIZE + (bt.height * TILE_SIZE) / 2

                turrets.append({
                    "id": building.id,
                    "x": world_x,
                    "y": world_y,
                    "damage": bt.damage,
                    "fire_rate": bt.fire_rate,
                    "attack_range": bt.attack_range,
                    "type_code": bt.code,
                })

        return turrets


async def get_player_clan_base(player_id: int, online_player_ids: set = None) -> Optional[dict]:
    """Get the clan base info for a player (if they are in a clan).
    Includes list of clan members with online status."""
    if online_player_ids is None:
        online_player_ids = set()

    async with async_session() as db:
        result = await db.execute(
            select(ClanMember)
            .options(
                selectinload(ClanMember.clan).selectinload(Clan.members).selectinload(ClanMember.player)
            )
            .where(ClanMember.player_id == player_id)
        )
        membership = result.scalar_one_or_none()
        if not membership or not membership.clan:
            return None
        clan = membership.clan

        members = []
        for m in clan.members:
            if not m.player:
                continue
            members.append({
                "player_id": m.player_id,
                "username": m.player.username or f"player_{m.player_id}",
                "role": m.role,
                "is_online": m.player_id in online_player_ids,
            })

        return {
            "clan_id": clan.id,
            "name": clan.name,
            "base_x": clan.base_x,
            "base_y": clan.base_y,
            "members": members,
        }


async def deposit_player_resources(player_id: int, world_player, safe_zone_radius: float) -> Optional[dict]:
    """Deposit all player resources to their clan base if they are near it."""
    import math
    async with async_session() as db:
        # Get player's clan
        result = await db.execute(
            select(ClanMember)
            .options(selectinload(ClanMember.clan))
            .where(ClanMember.player_id == player_id)
        )
        membership = result.scalar_one_or_none()
        if not membership or not membership.clan:
            return None

        clan = membership.clan

        # Check proximity
        dx = clan.base_x - world_player.x
        dy = clan.base_y - world_player.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > safe_zone_radius:
            return None

        # Collect amounts to deposit
        deposited = {
            "metal": world_player.metal,
            "wood": world_player.wood,
            "food": world_player.food,
            "ammo": world_player.ammo_inv,
            "meds": world_player.meds,
        }

        # Transfer to clan
        clan.metal += world_player.metal
        clan.wood += world_player.wood
        clan.food += world_player.food
        clan.ammo += world_player.ammo_inv
        clan.meds += world_player.meds

        # Clear player inventory
        world_player.metal = 0
        world_player.wood = 0
        world_player.food = 0
        world_player.ammo_inv = 0
        world_player.meds = 0

        await db.commit()
        return deposited


async def load_buildings_for_chunk(chunk_x: int, chunk_y: int) -> list:
    """Load all buildings for clans whose base is in this chunk."""
    async with async_session() as db:
        result = await db.execute(
            select(Clan).where(_find_clans_in_chunk(chunk_x, chunk_y))
        )
        clans = result.scalars().all()
        if not clans:
            return []

        buildings = []
        now = datetime.now(timezone.utc)
        for clan in clans:
            result = await db.execute(
                select(Building).where(
                    Building.clan_id == clan.id,
                    Building.is_active == True
                ).options(selectinload(Building.building_type))
            )
            for building in result.scalars().all():
                bt = building.building_type
                if not bt:
                    continue

                is_built = True
                if building.build_complete:
                    is_built = building.build_complete.replace(tzinfo=timezone.utc) <= now

                # Grid is 16x16 centered on clan base position
                world_x = clan.base_x - 8 * TILE_SIZE + building.grid_x * TILE_SIZE
                world_y = clan.base_y - 8 * TILE_SIZE + building.grid_y * TILE_SIZE

                # last_collected timestamp for client-side production calc
                lc_ts = None
                if building.last_collected:
                    lc = building.last_collected
                    if lc.tzinfo is None:
                        lc_ts = lc.replace(tzinfo=timezone.utc).timestamp()
                    else:
                        lc_ts = lc.timestamp()

                buildings.append({
                    "id": building.id,
                    "clan_id": clan.id,
                    "type_code": bt.code,
                    "type_name": bt.name,
                    "category": bt.category,
                    "x": world_x,
                    "y": world_y,
                    "width": bt.width * TILE_SIZE,
                    "height": bt.height * TILE_SIZE,
                    "hp": building.hp,
                    "max_hp": bt.max_hp,
                    "is_built": is_built,
                    "clan_name": clan.name,
                    "produces_resource": bt.produces_resource,
                    "production_rate": bt.production_rate,
                    "storage_capacity": getattr(bt, 'storage_capacity', 0),
                    "last_collected_ts": lc_ts,
                })

        return buildings


async def save_chunk_zombies(chunk_x: int, chunk_y: int, zombies: list):
    """Save zombies in a chunk to DB (for persistence when chunk unloads)"""
    async with async_session() as db:
        # Delete existing zombies in this chunk
        result = await db.execute(
            select(WorldZombie).where(
                WorldZombie.chunk_x == chunk_x,
                WorldZombie.chunk_y == chunk_y
            )
        )
        for wz in result.scalars().all():
            await db.delete(wz)

        # Save current zombies
        for z in zombies:
            wz = WorldZombie(
                x=z["x"],
                y=z["y"],
                chunk_x=chunk_x,
                chunk_y=chunk_y,
                zombie_type=z["type"],
                hp=z["hp"],
                max_hp=z["max_hp"],
                is_alive=True,
            )
            db.add(wz)

        await db.commit()
