"""
VELLA - Multiplayer Zombie Shooter
FastAPI + WebSocket Backend
"""
import os
import json
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as redis

from .database import init_db, get_db
from .models import Player, Weapon, PlayerWeapon
from .auth import validate_telegram_data
from .game.engine import engine
from .game.weapons import WEAPONS, get_all_weapons


# Redis for additional state if needed
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
redis_client: Optional[redis.Redis] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global redis_client

    # Startup
    await init_db()
    redis_client = await redis.from_url(REDIS_URL)
    await seed_weapons()
    await engine.start()

    yield

    # Shutdown
    await engine.stop()
    if redis_client:
        await redis_client.close()


app = FastAPI(title="VELLA", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def seed_weapons():
    """Seed weapons table with initial data"""
    from .database import async_session
    async with async_session() as db:
        result = await db.execute(select(Weapon).limit(1))
        if result.scalar_one_or_none():
            return  # Already seeded

        for code, data in WEAPONS.items():
            weapon = Weapon(
                code=code,
                name=data["name"],
                category=data["category"],
                damage=data["damage"],
                fire_rate=data["fire_rate"],
                reload_time=data["reload_time"],
                magazine_size=data["magazine_size"],
                spread=data["spread"],
                projectile_speed=data["projectile_speed"],
                pellets=data.get("pellets", 1),
                penetration=data.get("penetration", 1),
                price_dollars=data["price_dollars"],
                price_coins=data["price_coins"],
                required_kills=data["required_kills"]
            )
            db.add(weapon)

        await db.commit()


# ============== AUTH HELPERS ==============

async def get_or_create_player(telegram_id: int, username: Optional[str], db: AsyncSession) -> Player:
    """Get existing player or create new one"""
    result = await db.execute(
        select(Player).where(Player.telegram_id == telegram_id)
    )
    player = result.scalar_one_or_none()

    if not player:
        player = Player(
            telegram_id=telegram_id,
            username=username
        )
        db.add(player)
        await db.commit()
        await db.refresh(player)

        # Give starter weapon
        result = await db.execute(
            select(Weapon).where(Weapon.code == "glock_17")
        )
        starter_weapon = result.scalar_one_or_none()
        if starter_weapon:
            player_weapon = PlayerWeapon(
                player_id=player.telegram_id,
                weapon_id=starter_weapon.id,
                equipped=True
            )
            db.add(player_weapon)
            await db.commit()

    return player


# ============== REST API ==============

@app.get("/api/player")
async def get_player_info(
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get player info"""
    user_data = validate_telegram_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid auth")

    telegram_id = user_data.get("id")
    username = user_data.get("username")

    player = await get_or_create_player(telegram_id, username, db)

    # Get player's weapons
    result = await db.execute(
        select(PlayerWeapon, Weapon)
        .join(Weapon)
        .where(PlayerWeapon.player_id == player.telegram_id)
    )
    owned_weapons = []
    equipped_weapon = "glock_17"

    for pw, weapon in result.all():
        owned_weapons.append({
            "code": weapon.code,
            "name": weapon.name,
            "kills": pw.kills_with,
            "equipped": pw.equipped
        })
        if pw.equipped:
            equipped_weapon = weapon.code

    return {
        "id": player.telegram_id,
        "username": player.username,
        "coins": player.coins,
        "total_kills": player.total_kills,
        "highest_wave": player.highest_wave,
        "games_played": player.games_played,
        "weapons": owned_weapons,
        "equipped_weapon": equipped_weapon
    }


@app.get("/api/weapons")
async def get_weapons(
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get all weapons with ownership status"""
    user_data = validate_telegram_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid auth")

    telegram_id = user_data.get("id")

    # Get player's owned weapons
    result = await db.execute(
        select(PlayerWeapon.weapon_id)
        .where(PlayerWeapon.player_id == telegram_id)
    )
    owned_ids = {row[0] for row in result.all()}

    # Get player's kills for unlock check
    result = await db.execute(
        select(Player.total_kills)
        .where(Player.telegram_id == telegram_id)
    )
    player_kills = result.scalar_one_or_none() or 0

    weapons = []
    for weapon_data in get_all_weapons():
        weapon_id = await _get_weapon_id(db, weapon_data["code"])
        weapons.append({
            **weapon_data,
            "owned": weapon_id in owned_ids if weapon_id else False,
            "can_unlock": player_kills >= weapon_data["required_kills"]
        })

    return weapons


async def _get_weapon_id(db: AsyncSession, code: str) -> Optional[int]:
    result = await db.execute(select(Weapon.id).where(Weapon.code == code))
    row = result.first()
    return row[0] if row else None


@app.post("/api/weapons/buy")
async def buy_weapon(
    weapon_code: str,
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Buy a weapon"""
    user_data = validate_telegram_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid auth")

    telegram_id = user_data.get("id")

    # Get player
    result = await db.execute(
        select(Player).where(Player.telegram_id == telegram_id)
    )
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Get weapon
    result = await db.execute(
        select(Weapon).where(Weapon.code == weapon_code)
    )
    weapon = result.scalar_one_or_none()
    if not weapon:
        raise HTTPException(status_code=404, detail="Weapon not found")

    # Check if already owned
    result = await db.execute(
        select(PlayerWeapon)
        .where(PlayerWeapon.player_id == telegram_id)
        .where(PlayerWeapon.weapon_id == weapon.id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already owned")

    # Check kills requirement
    if player.total_kills < weapon.required_kills:
        raise HTTPException(status_code=400, detail="Not enough kills to unlock")

    # Check coins
    if player.coins < weapon.price_coins:
        raise HTTPException(status_code=400, detail="Not enough coins")

    # Purchase
    player.coins -= weapon.price_coins
    player_weapon = PlayerWeapon(
        player_id=telegram_id,
        weapon_id=weapon.id
    )
    db.add(player_weapon)
    await db.commit()

    return {"success": True, "coins": player.coins}


@app.post("/api/weapons/equip")
async def equip_weapon(
    weapon_code: str,
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Equip a weapon"""
    user_data = validate_telegram_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid auth")

    telegram_id = user_data.get("id")

    # Unequip all
    result = await db.execute(
        select(PlayerWeapon).where(PlayerWeapon.player_id == telegram_id)
    )
    for pw in result.scalars():
        pw.equipped = False

    # Equip selected
    result = await db.execute(
        select(PlayerWeapon, Weapon)
        .join(Weapon)
        .where(PlayerWeapon.player_id == telegram_id)
        .where(Weapon.code == weapon_code)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Weapon not owned")

    row[0].equipped = True
    await db.commit()

    return {"success": True}


# ============== WEBSOCKET ==============

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    init_data: str = Query(...)
):
    """Main game WebSocket endpoint"""
    # Validate auth
    user_data = validate_telegram_data(init_data)
    if not user_data:
        await websocket.close(code=4001, reason="Invalid auth")
        return

    telegram_id = user_data.get("id")
    username = user_data.get("username")

    if not telegram_id:
        await websocket.close(code=4001, reason="No user ID")
        return

    await websocket.accept()

    # Get or create player in DB
    from .database import async_session
    async with async_session() as db:
        await get_or_create_player(telegram_id, username, db)

    room = None
    player = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "join_room":
                room_code = data.get("room_code")
                room = engine.get_room(room_code)

                player = room.add_player(telegram_id, username, websocket)

                # Send room joined confirmation
                await websocket.send_json({
                    "type": "room_joined",
                    "room_code": room.room_code,
                    "players": [p.to_lobby_state() for p in room.players.values()],
                    "your_id": telegram_id
                })

                # Broadcast lobby update to others
                await room.broadcast(room.get_lobby_state())

            elif msg_type == "ready" and room and player:
                player.is_ready = data.get("is_ready", False)
                await room.broadcast(room.get_lobby_state())

                # Check if all ready to start/continue
                if room.all_players_ready() and room.player_count >= 1:
                    if room.status == "lobby":
                        # Start new game
                        room.start_game()
                        await room.broadcast({
                            "type": "game_start",
                            "players": [p.to_state() for p in room.players.values()]
                        })
                    elif room.status == "wave_break":
                        # Continue to next wave
                        room.status = "countdown"
                        room.countdown = room.WAVE_COUNTDOWN
                        await room.broadcast({
                            "type": "wave_countdown",
                            "next_wave": room.wave_manager.current_wave + 1,
                            "countdown": room.WAVE_COUNTDOWN
                        })

            elif msg_type == "input" and room and player:
                player.apply_input(
                    move_x=data.get("move_x", 0),
                    move_y=data.get("move_y", 0),
                    aim_x=data.get("aim_x", 0),
                    aim_y=data.get("aim_y", -1),
                    shooting=data.get("shooting", False),
                    reload=data.get("reload", False)
                )

            elif msg_type == "switch_weapon" and room and player:
                weapon_code = data.get("weapon_code", "glock_17")
                player.switch_weapon(weapon_code)

            elif msg_type == "leave_room" and room:
                room.remove_player(telegram_id)
                await room.broadcast(room.get_lobby_state())

                if room.is_empty:
                    engine.room_manager.remove_room(room.room_code)

                room = None
                player = None

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Cleanup on disconnect
        if room and player:
            room.remove_player(telegram_id)

            # Save player stats to DB
            if player.coins_earned > 0 or player.kills > 0:
                async with async_session() as db:
                    result = await db.execute(
                        select(Player).where(Player.telegram_id == telegram_id)
                    )
                    db_player = result.scalar_one_or_none()
                    if db_player:
                        db_player.coins += player.coins_earned
                        db_player.total_kills += player.kills
                        db_player.games_played += 1
                        if room.wave_manager.current_wave > db_player.highest_wave:
                            db_player.highest_wave = room.wave_manager.current_wave
                        await db.commit()

            # Notify others
            if not room.is_empty:
                await room.broadcast(room.get_lobby_state())
            else:
                engine.room_manager.remove_room(room.room_code)


@app.get("/api/rooms")
async def list_rooms():
    """List available rooms (for debugging)"""
    return [
        {
            "code": room.room_code,
            "players": room.player_count,
            "status": room.status,
            "wave": room.wave_manager.current_wave
        }
        for room in engine.room_manager.rooms.values()
    ]
