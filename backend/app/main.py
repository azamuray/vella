"""
VELLA - Multiplayer Zombie Shooter
FastAPI + WebSocket Backend
"""
import os
import json
import asyncio
import httpx
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as redis

from .database import init_db, get_db
from .models import Player, Weapon, PlayerWeapon
from .auth import validate_telegram_data
from .game.engine import engine
from .game.weapons import WEAPONS, get_all_weapons
from .game.rpg.world_engine import world_engine
from .game.rpg.building_types import seed_building_types
from .game.rpg.clan_routes import router as clan_router
from .game.rpg.building_routes import router as building_router
from .rewards.star_scheduler import star_scheduler

# Telegram Bot Token for payments
BOT_TOKEN = os.getenv("BOT_TOKEN", "")


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
    await _seed_building_types()
    await engine.start()
    await world_engine.start()

    # Start Telegram bot polling as background task
    bot_task = None
    bot_instance = None
    if BOT_TOKEN:
        from .bot.bot import bot as bot_instance
        from .bot.polling import start_polling
        bot_task = asyncio.create_task(start_polling())
        print("[Bot] Polling task started")
    else:
        print("[Bot] No BOT_TOKEN, skipping bot startup")

    # Start star reward scheduler (uses bot for admin notifications)
    await star_scheduler.start(bot_instance)

    yield

    # Shutdown
    if bot_task:
        from .bot.polling import stop_polling
        await stop_polling()
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
        print("[Bot] Stopped")

    await star_scheduler.stop()
    await world_engine.stop()
    await engine.stop()
    if redis_client:
        await redis_client.close()


app = FastAPI(title="VELLA", lifespan=lifespan)

# Include RPG routers
app.include_router(clan_router)
app.include_router(building_router)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def seed_weapons():
    """Seed weapons table with initial data (adds new weapons if missing)"""
    from .database import async_session
    async with async_session() as db:
        for code, data in WEAPONS.items():
            # Check if weapon already exists
            result = await db.execute(select(Weapon).where(Weapon.code == code))
            if result.scalar_one_or_none():
                continue  # Already exists

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
            print(f"[Seed] Added weapon: {code}")

        await db.commit()


async def _seed_building_types():
    """Seed building types table"""
    from .database import async_session
    async with async_session() as db:
        await seed_building_types(db)


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

    # Check coins (removed kills requirement - buy with coins only)
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


# ============== TELEGRAM STARS PAYMENTS ==============

@app.post("/api/payments/create-invoice")
async def create_invoice(
    weapon_code: str,
    init_data: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Create Telegram Stars invoice for premium weapon"""
    user_data = validate_telegram_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid auth")

    telegram_id = user_data.get("id")

    # Check weapon exists and is premium
    weapon_data = WEAPONS.get(weapon_code)
    if not weapon_data:
        raise HTTPException(status_code=404, detail="Weapon not found")

    if not weapon_data.get("premium"):
        raise HTTPException(status_code=400, detail="Not a premium weapon")

    price_stars = weapon_data.get("price_stars", 0)
    if price_stars <= 0:
        raise HTTPException(status_code=400, detail="Invalid price")

    # Check if already owned
    result = await db.execute(
        select(Weapon).where(Weapon.code == weapon_code)
    )
    weapon = result.scalar_one_or_none()
    if weapon:
        result = await db.execute(
            select(PlayerWeapon)
            .where(PlayerWeapon.player_id == telegram_id)
            .where(PlayerWeapon.weapon_id == weapon.id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Already owned")

    # Create invoice via Telegram Bot API
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink",
            json={
                "title": weapon_data["name"],
                "description": weapon_data.get("description", f"Premium weapon: {weapon_data['name']}"),
                "payload": json.dumps({"weapon_code": weapon_code, "user_id": telegram_id}),
                "currency": "XTR",  # Telegram Stars
                "prices": [{"label": weapon_data["name"], "amount": price_stars}]
            }
        )
        result = response.json()

    if not result.get("ok"):
        print(f"[Payment Error] {result}")
        raise HTTPException(status_code=500, detail="Failed to create invoice")

    return {"invoice_url": result["result"]}


@app.post("/api/payments/webhook")
async def payment_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Telegram payment webhook"""
    data = await request.json()
    print(f"[Payment Webhook] {data}")

    # Handle pre_checkout_query (confirm payment is valid)
    if "pre_checkout_query" in data:
        query = data["pre_checkout_query"]
        query_id = query["id"]

        # Always approve for now (could add validation)
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/answerPreCheckoutQuery",
                json={"pre_checkout_query_id": query_id, "ok": True}
            )
        return {"ok": True}

    # Handle successful payment
    if "message" in data and "successful_payment" in data.get("message", {}):
        payment = data["message"]["successful_payment"]
        payload = json.loads(payment["invoice_payload"])
        weapon_code = payload["weapon_code"]
        user_id = payload["user_id"]

        print(f"[Payment Success] User {user_id} bought {weapon_code}")

        # Give weapon to player
        result = await db.execute(
            select(Weapon).where(Weapon.code == weapon_code)
        )
        weapon = result.scalar_one_or_none()

        if weapon:
            # Check not already owned
            result = await db.execute(
                select(PlayerWeapon)
                .where(PlayerWeapon.player_id == user_id)
                .where(PlayerWeapon.weapon_id == weapon.id)
            )
            if not result.scalar_one_or_none():
                player_weapon = PlayerWeapon(
                    player_id=user_id,
                    weapon_id=weapon.id
                )
                db.add(player_weapon)
                await db.commit()
                print(f"[Payment] Weapon {weapon_code} added to user {user_id}")

        return {"ok": True}

    return {"ok": True}


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
    print(f"[WS] Accepted connection for {username} (id={telegram_id})")

    # Get or create player in DB
    try:
        from .database import async_session
        async with async_session() as db:
            await get_or_create_player(telegram_id, username, db)
        print(f"[WS] Player {username} ready, waiting for messages...")
    except Exception as e:
        import traceback
        print(f"[WS] ERROR creating player: {e}")
        traceback.print_exc()
        await websocket.close(code=4002, reason="DB error")
        return

    room = None
    player = None
    player_mode = None  # "room" or "world"
    world_player = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            print(f"[WS] {username}: {msg_type}")

            # ====== WORLD MODE MESSAGES ======
            if msg_type == "enter_world":
                try:
                    # Enter open world
                    if player_mode == "room" and room:
                        # Leave room first
                        room.remove_player(telegram_id)
                        if room.is_empty:
                            engine.room_manager.remove_room(room.room_code)
                        room = None
                        player = None

                    # Set equipped weapon from DB
                    weapon_code = "glock_17"
                    async with async_session() as db:
                        result = await db.execute(
                            select(PlayerWeapon, Weapon)
                            .join(Weapon)
                            .where(PlayerWeapon.player_id == telegram_id)
                            .where(PlayerWeapon.equipped == True)
                        )
                        row = result.first()
                        if row:
                            weapon_code = row[1].code

                    world_player = await world_engine.add_player(
                        telegram_id, username, websocket, weapon_code
                    )
                    player_mode = "world"

                    # Get clan base info with online members
                    from .game.rpg import world_db as _world_db
                    online_ids = set(world_engine.players.keys())
                    clan_base = await _world_db.get_player_clan_base(telegram_id, online_ids)

                    await websocket.send_json({
                        "type": "world_entered",
                        "x": world_player.x,
                        "y": world_player.y,
                        "hp": world_player.hp,
                        "max_hp": world_player.max_hp,
                        "inventory": world_player.to_inventory_state(),
                        "weapon": world_player.weapon_code,
                        "clan_base": clan_base,
                    })
                    # Now allow the game loop to send state/chunks to this player
                    world_player.ws_ready = True
                    print(f"[World] Player {username} entered world at ({world_player.x:.0f}, {world_player.y:.0f})")
                except Exception as e:
                    import traceback
                    print(f"[World] ERROR entering world: {e}")
                    traceback.print_exc()

            elif msg_type == "world_input" and player_mode == "world" and world_player:
                world_player.apply_input(
                    move_x=data.get("move_x", 0),
                    move_y=data.get("move_y", 0),
                    aim_x=data.get("aim_x", 0),
                    aim_y=data.get("aim_y", -1),
                    shooting=data.get("shooting", False),
                    reload=data.get("reload", False)
                )

            elif msg_type == "collect_resource" and player_mode == "world" and world_player:
                result = world_engine.collect_resource_for_player(telegram_id)
                if result:
                    await websocket.send_json({
                        "type": "world_resource_collected",
                        **result,
                        "inventory": world_player.to_inventory_state(),
                    })

            elif msg_type == "use_medkit" and player_mode == "world" and world_player:
                if world_player.use_medkit():
                    await websocket.send_json({
                        "type": "world_medkit_used",
                        "hp": world_player.hp,
                        "meds": world_player.meds,
                    })

            elif msg_type == "deposit_to_base" and player_mode == "world" and world_player:
                try:
                    from .game.rpg import world_db as _world_db
                    from .game.rpg.world_engine import SAFE_ZONE_RADIUS
                    # Check player has something to deposit
                    has_resources = (world_player.metal + world_player.wood +
                                    world_player.food + world_player.ammo_inv + world_player.meds) > 0
                    if not has_resources:
                        await websocket.send_json({"type": "deposit_result", "success": False, "reason": "empty"})
                    else:
                        result = await _world_db.deposit_player_resources(
                            telegram_id, world_player, SAFE_ZONE_RADIUS
                        )
                        if result:
                            await websocket.send_json({
                                "type": "deposit_result",
                                "success": True,
                                "deposited": result,
                                "inventory": world_player.to_inventory_state(),
                            })
                        else:
                            await websocket.send_json({"type": "deposit_result", "success": False, "reason": "not_at_base"})
                except Exception as e:
                    import traceback
                    print(f"[World] Deposit error: {e}")
                    traceback.print_exc()

            elif msg_type == "demolish_building" and player_mode == "world" and world_player:
                try:
                    building_id = data.get("building_id")
                    if building_id:
                        from .game.rpg.building_routes import _demolish_building_from_world
                        result = await _demolish_building_from_world(telegram_id, building_id)
                        await websocket.send_json({"type": "building_demolished", **result})
                except Exception as e:
                    await websocket.send_json({
                        "type": "building_demolished", "success": False, "reason": str(e),
                    })

            elif msg_type == "move_building" and player_mode == "world" and world_player:
                try:
                    building_id = data.get("building_id")
                    grid_x = data.get("grid_x")
                    grid_y = data.get("grid_y")
                    if building_id is not None and grid_x is not None and grid_y is not None:
                        from .game.rpg.building_routes import _move_building_from_world
                        result = await _move_building_from_world(
                            telegram_id, building_id, grid_x, grid_y
                        )
                        await websocket.send_json({"type": "building_moved", **result})
                except Exception as e:
                    await websocket.send_json({
                        "type": "building_moved", "success": False, "reason": str(e),
                    })

            elif msg_type == "collect_building" and player_mode == "world" and world_player:
                try:
                    building_id = data.get("building_id")
                    if building_id:
                        from .game.rpg.building_routes import _collect_building_from_world
                        result = await _collect_building_from_world(
                            telegram_id, building_id, world_player
                        )
                        await websocket.send_json({
                            "type": "building_collected",
                            **result,
                        })
                except Exception as e:
                    await websocket.send_json({
                        "type": "building_collected",
                        "success": False,
                        "reason": str(e),
                    })

            elif msg_type == "collect_all_buildings" and player_mode == "world" and world_player:
                try:
                    from .game.rpg.building_routes import _collect_all_buildings_from_world
                    result = await _collect_all_buildings_from_world(
                        telegram_id, world_player
                    )
                    await websocket.send_json({
                        "type": "all_buildings_collected",
                        **result,
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "all_buildings_collected",
                        "success": False,
                        "reason": str(e),
                    })

            elif msg_type == "pickup_drop" and player_mode == "world" and world_player:
                drop_id = data.get("drop_id")
                if drop_id is not None:
                    result = world_engine.pickup_ground_drop(telegram_id, drop_id)
                    if result:
                        await websocket.send_json({
                            "type": "clothing_equipped",
                            **result,
                            "clothing": world_player.to_clothing_state(),
                        })

            elif msg_type == "unequip_clothing" and player_mode == "world" and world_player:
                slot = data.get("slot")
                if slot in ("head", "body", "legs"):
                    result = world_player.unequip_clothing(slot)
                    await websocket.send_json({
                        "type": "clothing_unequipped",
                        **result,
                        "clothing": world_player.to_clothing_state(),
                    })

            elif msg_type == "leave_world" and player_mode == "world":
                await world_engine.remove_player(telegram_id)
                world_player = None
                player_mode = None
                await websocket.send_json({"type": "world_left"})

            # ====== ROOM MODE MESSAGES ======
            elif msg_type == "create_room":
                # Leave world if in it
                if player_mode == "world" and world_player:
                    await world_engine.remove_player(telegram_id)
                    world_player = None

                player_mode = "room"

                # Create a new room (public or private)
                is_public = data.get("is_public", True)
                room = engine.room_manager.create_room(is_public=is_public)
                player = room.add_player(telegram_id, username, websocket)

                # Set player's equipped weapon from DB
                async with async_session() as db:
                    result = await db.execute(
                        select(PlayerWeapon, Weapon)
                        .join(Weapon)
                        .where(PlayerWeapon.player_id == telegram_id)
                        .where(PlayerWeapon.equipped == True)
                    )
                    row = result.first()
                    if row:
                        player.switch_weapon(row[1].code)

                await websocket.send_json({
                    "type": "room_created",
                    "room_code": room.room_code,
                    "is_public": room.is_public,
                    "players": [p.to_lobby_state() for p in room.players.values()],
                    "your_id": telegram_id
                })
                print(f"[Room] Created {'public' if is_public else 'private'} room {room.room_code} by {username}")

            elif msg_type == "join_room":
                # Leave world if in it
                if player_mode == "world" and world_player:
                    await world_engine.remove_player(telegram_id)
                    world_player = None

                player_mode = "room"

                room_code = data.get("room_code")
                room = engine.room_manager.get_room(room_code)

                if not room:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Room not found"
                    })
                    continue

                if room.is_full:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Room is full"
                    })
                    continue

                if room.status != "lobby":
                    await websocket.send_json({
                        "type": "error",
                        "message": "Game already in progress"
                    })
                    continue

                player = room.add_player(telegram_id, username, websocket)

                # Set player's equipped weapon from DB
                async with async_session() as db:
                    result = await db.execute(
                        select(PlayerWeapon, Weapon)
                        .join(Weapon)
                        .where(PlayerWeapon.player_id == telegram_id)
                        .where(PlayerWeapon.equipped == True)
                    )
                    row = result.first()
                    if row:
                        player.switch_weapon(row[1].code)
                        print(f"[Join] Player {telegram_id} using equipped weapon: {row[1].code}")

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
                        # Send countdown for first wave too
                        await room.broadcast({
                            "type": "wave_countdown",
                            "next_wave": 1,
                            "countdown": room.WAVE_COUNTDOWN
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

            elif msg_type == "kill_all" and room:
                # Debug: kill all zombies
                killed_count = len(room.zombies)
                for zombie in list(room.zombies.values()):
                    if player:
                        player.add_kill(zombie.coins)
                    room.total_kills += 1
                room.zombies.clear()
                print(f"[DEBUG] Killed all {killed_count} zombies in room {room.room_code}")

            elif msg_type == "leave_room" and room:
                # Save player stats BEFORE removing from room
                if player and (player.coins_earned > 0 or player.kills > 0):
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
                            print(f"[Save] Player {telegram_id} saved: +{player.coins_earned} coins, +{player.kills} kills")

                room.remove_player(telegram_id)
                await room.broadcast(room.get_lobby_state())

                if room.is_empty:
                    engine.room_manager.remove_room(room.room_code)
                elif room.status == "wave_break" and room.all_players_ready() and room.player_count >= 1:
                    # Start next wave if remaining players are all ready
                    room.status = "countdown"
                    room.countdown = room.WAVE_COUNTDOWN
                    await room.broadcast({
                        "type": "wave_countdown",
                        "next_wave": room.wave_manager.current_wave + 1,
                        "countdown": room.WAVE_COUNTDOWN
                    })

                room = None
                player = None
                player_mode = None

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Cleanup world player on disconnect
        if player_mode == "world" and world_player:
            await world_engine.remove_player(telegram_id)

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

            # Notify others and check if wave should start
            if not room.is_empty:
                await room.broadcast(room.get_lobby_state())

                # Start next wave if remaining players are all ready
                if room.status == "wave_break" and room.all_players_ready() and room.player_count >= 1:
                    room.status = "countdown"
                    room.countdown = room.WAVE_COUNTDOWN
                    await room.broadcast({
                        "type": "wave_countdown",
                        "next_wave": room.wave_manager.current_wave + 1,
                        "countdown": room.WAVE_COUNTDOWN
                    })
            else:
                engine.room_manager.remove_room(room.room_code)


@app.get("/api/leaderboard")
async def get_leaderboard():
    """Top-10 players by highest wave (tiebreak by total kills)"""
    from .database import async_session
    async with async_session() as db:
        result = await db.execute(
            select(Player)
            .where(Player.highest_wave > 0)
            .order_by(Player.highest_wave.desc(), Player.total_kills.desc())
            .limit(10)
        )
        players = result.scalars().all()

        return [
            {
                "position": i + 1,
                "username": p.username,
                "highest_wave": p.highest_wave,
                "total_kills": p.total_kills,
                "star_balance": round(p.star_balance or 0, 2),
                "total_stars_earned": p.total_stars_earned or 0,
            }
            for i, p in enumerate(players)
        ]


@app.get("/api/rooms")
async def list_rooms():
    """List public rooms available to join"""
    return engine.room_manager.get_public_rooms()


@app.get("/api/rooms/all")
async def list_all_rooms():
    """List all rooms (for debugging)"""
    return [
        {
            "code": room.room_code,
            "players": room.player_count,
            "status": room.status,
            "wave": room.wave_manager.current_wave,
            "is_public": room.is_public
        }
        for room in engine.room_manager.rooms.values()
    ]
