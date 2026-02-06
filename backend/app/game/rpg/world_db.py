"""
Database operations for open world — load/save player state, chunks, zombies.
"""
from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import WorldState, PlayerInventory, MapChunk, WorldZombie
from ...database import async_session
from .map_generator import map_generator


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
        }


async def save_world_state(player_id: int, x: float, y: float, hp: int,
                            is_alive: bool, inventory: dict, weapon_code: str):
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


async def load_turrets_for_chunk(chunk_x: int, chunk_y: int) -> list:
    """Load built turrets for clans whose base is at this chunk."""
    from ...models import Clan, Building, BuildingType
    from sqlalchemy.orm import selectinload

    async with async_session() as db:
        # Find clans with base at this chunk
        result = await db.execute(
            select(Clan).where(
                Clan.base_x == chunk_x,
                Clan.base_y == chunk_y
            )
        )
        clans = result.scalars().all()
        if not clans:
            return []

        turrets = []
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
                # Check if fully built
                if building.build_complete is None:
                    continue
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                if building.build_complete.replace(tzinfo=timezone.utc) > now:
                    continue

                # Convert grid position to world coordinates
                # Base occupies the chunk, buildings are on 16x16 grid within it
                from .map_generator import CHUNK_SIZE, TILE_SIZE
                world_x = chunk_x * CHUNK_SIZE + building.grid_x * TILE_SIZE + (bt.width * TILE_SIZE) / 2
                world_y = chunk_y * CHUNK_SIZE + building.grid_y * TILE_SIZE + (bt.height * TILE_SIZE) / 2

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
