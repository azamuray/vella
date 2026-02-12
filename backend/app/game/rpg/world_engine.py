"""
World Engine — manages the open world tick loop, chunk loading/unloading,
and sending state updates to players.
"""
import asyncio
import math
import random
import time
from typing import Dict, List, Optional, Set, Tuple
from fastapi import WebSocket

from .world_player import WorldPlayer
from .world_zombie_entity import WorldZombieEntity
from .world_chunk import WorldChunk
from .map_generator import map_generator, CHUNK_SIZE, TILE_SIZE, TILE_WATER, TILE_ROCK
from . import world_db
from .clothing import generate_clothing_drop, CLOTHING_ITEMS
from ..collision import distance, line_circle_intersection, normalize


class WorldProjectile:
    """A bullet flying through the open world."""
    _next_id = 500000

    def __init__(self, owner_id: int, x: float, y: float, angle: float, weapon: dict):
        self.id = WorldProjectile._next_id
        WorldProjectile._next_id += 1
        self.owner_id = owner_id
        self.x = x
        self.y = y
        self.angle = angle
        self.speed = weapon["projectile_speed"]
        self.damage = weapon["damage"]
        self.remaining_damage = weapon["damage"]
        self.hit_zombies: set = set()

        self.vx = math.cos(angle) * self.speed
        self.vy = math.sin(angle) * self.speed
        self.lifetime = 2.0  # seconds

    def update(self, dt: float) -> bool:
        """Returns True if should be removed."""
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.lifetime -= dt
        return self.lifetime <= 0

    def to_state(self) -> dict:
        return {
            "id": self.id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "angle": round(self.angle, 2),
            "owner_id": self.owner_id,
        }


class WorldTurret:
    """A turret placed on a clan base that auto-fires at zombies."""

    def __init__(self, building_id: int, x: float, y: float, damage: int,
                 fire_rate: float, attack_range: float, type_code: str):
        self.building_id = building_id
        self.x = x
        self.y = y
        self.damage = damage
        self.fire_rate = fire_rate  # shots per second
        self.attack_range = attack_range
        self.type_code = type_code
        self.cooldown = 0.0
        self.aim_angle = 0.0  # current aim direction (radians)

    def update(self, dt: float):
        if self.cooldown > 0:
            self.cooldown -= dt

    def can_fire(self) -> bool:
        return self.cooldown <= 0

    def fire(self):
        if self.fire_rate > 0:
            self.cooldown = 1.0 / self.fire_rate
        else:
            self.cooldown = 1.0


SAFE_ZONE_RADIUS = 450  # pixels around clan base center


class WorldEngine:
    """Main world engine — runs independently from room GameEngine."""

    TICK_RATE = 20
    CHUNK_UNLOAD_DELAY = 30  # seconds before unloading empty chunk

    def __init__(self):
        self.players: Dict[int, WorldPlayer] = {}
        self.chunks: Dict[Tuple[int, int], WorldChunk] = {}
        self.projectiles: Dict[int, WorldProjectile] = {}
        self.turrets: Dict[Tuple[int, int], List[WorldTurret]] = {}  # chunk_key -> turrets
        self.safe_zones: List[Tuple[float, float]] = []  # clan base positions
        self._player_clans: Dict[int, int] = {}  # player_id -> clan_id
        self._building_clans: Dict[int, int] = {}  # building_id -> clan_id
        self._open_gates: Set[int] = set()  # building_ids of currently open gates
        self.ground_drops: Dict[int, dict] = {}  # drop_id -> {id, code, x, y, created_at}
        self._next_drop_id = 900000
        self.running = False
        self._task = None

        # Track when chunks became empty (for delayed unload)
        self._chunk_empty_since: Dict[Tuple[int, int], float] = {}

        # Wall damage tracking
        self._walls_to_destroy: List[int] = []
        self._walls_dirty_chunks: Set[Tuple[int, int]] = set()
        self._wall_hp_sync: Dict[int, float] = {}  # wall_id -> accumulated damage for DB sync

        # Storage full notification tracking (avoid spam)
        self._notified_storage: Set[int] = set()  # building_ids already notified

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._game_loop())
        print("[WorldEngine] Started")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # Save all players
        for player in list(self.players.values()):
            await self._save_player(player)
        # Save all chunks
        for key, chunk in list(self.chunks.items()):
            await self._save_chunk(chunk)
        self.turrets.clear()
        print("[WorldEngine] Stopped")

    async def add_player(self, player_id: int, username: str, ws: WebSocket, weapon_code: str) -> WorldPlayer:
        """Add player to open world."""
        # Load from DB
        state = await world_db.get_or_create_world_state(player_id)

        player = WorldPlayer(player_id, username, state["x"], state["y"])
        player.hp = state["hp"]
        player.is_alive = state["is_alive"]
        player.ws = ws

        # Load inventory
        inv = state["inventory"]
        player.metal = inv["metal"]
        player.wood = inv["wood"]
        player.food = inv["food"]
        player.ammo_inv = inv["ammo"]
        player.meds = inv["meds"]

        # Ensure player has at least some starting ammo
        if player.ammo_inv <= 0:
            player.ammo_inv = 30

        # Set weapon, then fill magazine from inventory
        player.switch_weapon(state.get("equipped_weapon", "glock_17"))

        # Restore clothing
        saved_clothing = state.get("equipped_clothing")
        if saved_clothing and isinstance(saved_clothing, dict):
            for slot in ("head", "body", "legs"):
                item = saved_clothing.get(slot)
                if item and isinstance(item, dict) and "code" in item and "durability" in item:
                    player.clothing[slot] = {"code": item["code"], "durability": item["durability"]}

        self.players[player_id] = player

        # Load player's clan membership
        clan_base = await world_db.get_player_clan_base(player_id, set())
        if clan_base:
            self._player_clans[player_id] = clan_base["clan_id"]

        # Ensure visible chunks are loaded
        await self._load_chunks_around(player)

        # Clear zombies near spawn point (safe zone)
        self._clear_zombies_near(player.x, player.y, radius=300)

        return player

    async def remove_player(self, player_id: int):
        """Remove player from world, save state."""
        player = self.players.pop(player_id, None)
        self._player_clans.pop(player_id, None)
        if player:
            await self._save_player(player)

    def get_player(self, player_id: int) -> Optional[WorldPlayer]:
        return self.players.get(player_id)

    async def _game_loop(self):
        dt = 1.0 / self.TICK_RATE
        tick = 0

        while self.running:
            loop_start = asyncio.get_event_loop().time()

            try:
                await self._tick(dt, tick)
            except Exception as e:
                import traceback
                print(f"[WorldEngine] Error: {e}")
                traceback.print_exc()

            tick += 1

            elapsed = asyncio.get_event_loop().time() - loop_start
            sleep_time = dt - elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def _tick(self, dt: float, tick: int):
        if not self.players:
            return

        events: List[dict] = []

        # Update all players
        for player in list(self.players.values()):
            if player.is_dead and player.can_respawn():
                spawn_x, spawn_y = map_generator.get_safe_spawn_position(0, 0)
                player.respawn(spawn_x, spawn_y)
                # Clear zombies near respawn point
                self._clear_zombies_near(spawn_x, spawn_y, radius=300)
                await self._send_to_player(player, {
                    "type": "world_player_respawn",
                    "x": player.x, "y": player.y,
                })

            if not player.is_dead:
                # Building collision callback for this player
                def _bld_check(nx, ny, pid=player.id):
                    return self._check_building_collision(nx, ny, pid)
                can_shoot = player.update(dt, self._get_tile_at, _bld_check)
                if can_shoot:
                    self._create_projectiles(player)

        # Load/unload chunks around players
        if tick % 10 == 0:  # every 0.5s
            await self._manage_chunks()

        # Update active chunks
        all_visible_players = list(self.players.values())
        for chunk_key, chunk in list(self.chunks.items()):
            # Only update chunks with nearby players
            players_in_range = [
                p for p in all_visible_players
                if (chunk.chunk_x, chunk.chunk_y) in set(p.get_visible_chunks())
            ]
            if players_in_range:
                chunk_events = chunk.update(dt, players_in_range, self.safe_zones)
                for event in chunk_events:
                    # Process zombie attacks
                    if event["type"] == "world_zombie_attack":
                        target = self.players.get(event["player_id"])
                        if target and not target.is_dead:
                            died = target.take_damage(event["damage"])
                            if died:
                                events.append({
                                    "type": "world_player_died",
                                    "player_id": target.id,
                                })
                    elif event["type"] == "world_wall_damage":
                        self._apply_wall_damage(chunk, event["wall_id"], event["damage"])

        # Update projectiles
        self._update_projectiles(dt, events)

        # Update turrets — auto-fire at nearby zombies
        self._update_turrets(dt, events)

        # Update gate open/close states
        if tick % 5 == 0:
            self._update_gate_states()

        # Enforce safe zones — remove zombies that wandered in
        if self.safe_zones and tick % 10 == 5:
            self._enforce_safe_zones()

        # Auto-pickup ground drops
        if tick % 5 == 0:
            self._auto_pickup_drops()

        # Expire old ground drops
        if tick % 60 == 0:
            self._expire_ground_drops()

        # Process wall destruction + notify clients
        if self._walls_to_destroy or self._walls_dirty_chunks:
            await self._sync_wall_damage()

        # Check production storage full (every ~10s)
        if tick % 200 == 50:
            await self._check_production_storage_full()

        # Unload stale chunks
        if tick % 60 == 0:  # every 3s
            await self._unload_stale_chunks()

        # Send state to each player (only what they can see)
        for player in list(self.players.values()):
            await self._send_state_to_player(player, events)

    def _check_building_collision(self, new_x: float, new_y: float,
                                    player_id: int, player_size: float = 20) -> bool:
        """Check if a player position collides with a wall, turret, or closed gate.
        Returns True if blocked."""
        cx = int(math.floor(new_x / CHUNK_SIZE))
        cy = int(math.floor(new_y / CHUNK_SIZE))

        player_clan = self._player_clans.get(player_id)

        for dx in range(-1, 2):
            for dy in range(-1, 2):
                chunk = self.chunks.get((cx + dx, cy + dy))
                if not chunk:
                    continue
                for b in chunk.buildings:
                    tc = b.get('type_code', '')
                    # Only collide with walls, turrets, and gates
                    if not (tc.startswith('wall_') or tc.startswith('turret_') or tc.startswith('gate_')):
                        continue

                    # Gates: open for clan members, or if gate is physically open
                    if tc.startswith('gate_'):
                        bld_id = b['id']
                        if bld_id in self._open_gates:
                            continue  # gate is open (clan member nearby)
                        bld_clan = b.get('clan_id') or self._building_clans.get(bld_id)
                        if player_clan and bld_clan == player_clan:
                            continue  # own clan gate always passable

                    bx, by = b['x'], b['y']
                    bw, bh = b['width'], b['height']
                    if (new_x + player_size > bx and new_x - player_size < bx + bw and
                            new_y + player_size > by and new_y - player_size < by + bh):
                        return True
        return False

    def _update_gate_states(self):
        """Track which gates are open (clan member nearby). Updates self._open_gates."""
        new_open = set()
        for chunk in self.chunks.values():
            for b in chunk.buildings:
                tc = b.get('type_code', '')
                if not tc.startswith('gate_'):
                    continue
                bld_clan = b.get('clan_id') or self._building_clans.get(b['id'])
                if not bld_clan:
                    continue
                gcx = b['x'] + b['width'] / 2
                gcy = b['y'] + b['height'] / 2
                # Check if any clan member is within 60px
                for p in self.players.values():
                    if p.is_dead:
                        continue
                    if self._player_clans.get(p.id) != bld_clan:
                        continue
                    if distance(p.x, p.y, gcx, gcy) < 60:
                        new_open.add(b['id'])
                        break
        self._open_gates = new_open

    def _get_tile_at(self, world_x: float, world_y: float) -> int:
        """Get tile type at world coordinates. Used for collision."""
        cx = int(math.floor(world_x / CHUNK_SIZE))
        cy = int(math.floor(world_y / CHUNK_SIZE))
        chunk = self.chunks.get((cx, cy))
        if chunk:
            tile = chunk.get_tile_at_world(world_x, world_y)
            if tile is not None:
                return tile
        return 0  # grass by default

    def _create_projectiles(self, player: WorldPlayer):
        weapon = player.weapon
        pellets = weapon.get("pellets", 1)
        spread = weapon["spread"]

        for _ in range(pellets):
            angle = player.aim_angle + random.uniform(-spread, spread)
            proj = WorldProjectile(player.id, player.x, player.y, angle, weapon)
            self.projectiles[proj.id] = proj

    def _update_projectiles(self, dt: float, events: list):
        to_remove = []

        for proj in list(self.projectiles.values()):
            old_x, old_y = proj.x, proj.y

            if proj.update(dt):
                to_remove.append(proj.id)
                continue

            # Check collision with all zombies in loaded chunks
            for chunk in self.chunks.values():
                for zombie in list(chunk.zombies.values()):
                    if zombie.id in proj.hit_zombies:
                        continue

                    if line_circle_intersection(
                        old_x, old_y, proj.x, proj.y,
                        zombie.x, zombie.y, zombie.size
                    ):
                        proj.hit_zombies.add(zombie.id)
                        zombie_hp_before = zombie.hp
                        damage_to_deal = min(proj.remaining_damage, zombie_hp_before)

                        if zombie.take_damage(damage_to_deal):
                            # Zombie killed
                            player = self.players.get(proj.owner_id)
                            if player:
                                player.add_kill(zombie.coins)

                            # Random loot drop
                            loot = self._generate_loot(zombie.type)

                            # Clothing drop
                            clothing_code = generate_clothing_drop(zombie.type)
                            clothing_drop = None
                            if clothing_code:
                                drop_id = self._next_drop_id
                                self._next_drop_id += 1
                                self.ground_drops[drop_id] = {
                                    "id": drop_id,
                                    "code": clothing_code,
                                    "x": zombie.x,
                                    "y": zombie.y,
                                    "created_at": time.time(),
                                }
                                clothing_drop = {
                                    "id": drop_id,
                                    "code": clothing_code,
                                    "name": CLOTHING_ITEMS[clothing_code]["name"],
                                }

                            events.append({
                                "type": "world_zombie_killed",
                                "zombie_id": zombie.id,
                                "killer_id": proj.owner_id,
                                "coins": zombie.coins,
                                "loot": loot,
                                "clothing_drop": clothing_drop,
                            })
                            del chunk.zombies[zombie.id]
                        else:
                            events.append({
                                "type": "world_zombie_hurt",
                                "zombie_id": zombie.id,
                                "damage": damage_to_deal,
                            })

                        proj.remaining_damage -= zombie_hp_before
                        if proj.remaining_damage <= 0:
                            to_remove.append(proj.id)
                            break

                if proj.id in to_remove:
                    break

        for pid in to_remove:
            self.projectiles.pop(pid, None)

    def _update_turrets(self, dt: float, events: list):
        """Turrets auto-fire at the nearest zombie in range."""
        for chunk_key, turret_list in self.turrets.items():
            chunk = self.chunks.get(chunk_key)
            if not chunk:
                continue

            # Gather zombies from this chunk and adjacent ones
            nearby_zombies = []
            cx, cy = chunk_key
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    adj = self.chunks.get((cx + dx, cy + dy))
                    if adj:
                        nearby_zombies.extend(adj.zombies.values())

            if not nearby_zombies:
                continue

            for turret in turret_list:
                turret.update(dt)

                # Find nearest zombie in range (always, for aiming)
                best_zombie = None
                best_dist = turret.attack_range + 1

                for zombie in nearby_zombies:
                    if zombie.hp <= 0:
                        continue
                    d = distance(turret.x, turret.y, zombie.x, zombie.y)
                    if d < turret.attack_range and d < best_dist:
                        best_dist = d
                        best_zombie = zombie

                if best_zombie is None:
                    continue

                # Always track target
                angle = math.atan2(best_zombie.y - turret.y, best_zombie.x - turret.x)
                turret.aim_angle = angle

                if not turret.can_fire():
                    continue

                turret.fire()
                proj = WorldProjectile(
                    owner_id=0,  # turret, not a player
                    x=turret.x, y=turret.y,
                    angle=angle,
                    weapon={
                        "projectile_speed": 800,
                        "damage": turret.damage,
                        "spread": 0,
                        "pellets": 1,
                    }
                )
                self.projectiles[proj.id] = proj

    async def _sync_wall_damage(self):
        """Delete destroyed walls from DB and notify clients."""
        from ...database import async_session
        from ...models import Building
        from sqlalchemy import select

        if self._walls_to_destroy:
            async with async_session() as db:
                for wall_id in self._walls_to_destroy:
                    result = await db.execute(
                        select(Building).where(Building.id == wall_id)
                    )
                    building = result.scalar_one_or_none()
                    if building:
                        await db.delete(building)
                await db.commit()
            self._walls_to_destroy.clear()

        # Notify clients about building updates for affected chunks
        for ck in self._walls_dirty_chunks:
            chunk = self.chunks.get(ck)
            if not chunk:
                continue
            for player in self.players.values():
                if ck in player.loaded_chunks:
                    try:
                        await player.ws.send_json({
                            "type": "world_chunk_buildings_update",
                            "chunk_x": ck[0],
                            "chunk_y": ck[1],
                            "buildings": chunk.buildings,
                        })
                    except Exception:
                        pass
        self._walls_dirty_chunks.clear()

    def _apply_wall_damage(self, chunk, wall_id: int, damage: float):
        """Apply damage to a wall in chunk.buildings. Destroy if HP <= 0."""
        for b in chunk.buildings:
            if b['id'] == wall_id:
                b['hp'] = b.get('hp', 100) - damage
                if b['hp'] <= 0:
                    # Wall destroyed — schedule DB deletion and refresh
                    chunk.buildings = [wb for wb in chunk.buildings if wb['id'] != wall_id]
                    self._walls_to_destroy.append(wall_id)
                    self._walls_dirty_chunks.add((chunk.chunk_x, chunk.chunk_y))
                break

    def _clear_zombies_near(self, x: float, y: float, radius: float = 300):
        """Remove all zombies within radius of a point (safe zone)."""
        for chunk in self.chunks.values():
            to_remove = [
                zid for zid, z in chunk.zombies.items()
                if distance(x, y, z.x, z.y) < radius
            ]
            for zid in to_remove:
                del chunk.zombies[zid]

    def _is_in_safe_zone(self, x: float, y: float) -> bool:
        """Check if a world position falls within any clan base safe zone."""
        for sx, sy in self.safe_zones:
            if distance(x, y, sx, sy) < SAFE_ZONE_RADIUS:
                return True
        return False

    def _enforce_safe_zones(self):
        """Remove any zombies that are inside a clan base safe zone."""
        for chunk in self.chunks.values():
            to_remove = [
                zid for zid, z in chunk.zombies.items()
                if self._is_in_safe_zone(z.x, z.y)
            ]
            for zid in to_remove:
                del chunk.zombies[zid]

    def _generate_loot(self, zombie_type: str) -> dict:
        """Generate random loot from zombie kill."""
        loot = {}
        if random.random() < 0.10:
            loot["ammo"] = random.randint(2, 5)
        if random.random() < 0.15:
            loot["food"] = random.randint(1, 3)
        if random.random() < 0.03:
            loot["meds"] = 1
        if zombie_type in ("tank", "boss"):
            if random.random() < 0.4:
                loot["metal"] = random.randint(5, 20)
        return loot

    def pickup_ground_drop(self, player_id: int, drop_id: int) -> Optional[dict]:
        """Pick up a ground drop if player is close enough."""
        player = self.players.get(player_id)
        if not player or player.is_dead:
            return None
        drop = self.ground_drops.get(drop_id)
        if not drop:
            return None
        if distance(player.x, player.y, drop["x"], drop["y"]) > 50:
            return None
        del self.ground_drops[drop_id]
        return player.equip_clothing(drop["code"])

    def _auto_pickup_drops(self):
        """Auto-pickup drops within 30px of any player."""
        picked = []
        for drop_id, drop in list(self.ground_drops.items()):
            for player in self.players.values():
                if player.is_dead:
                    continue
                if distance(player.x, player.y, drop["x"], drop["y"]) < 30:
                    result = player.equip_clothing(drop["code"])
                    if result and result.get("equipped"):
                        picked.append((player, drop_id, result))
                    break
        for player, drop_id, result in picked:
            self.ground_drops.pop(drop_id, None)
            if player.ws:
                try:
                    asyncio.ensure_future(player.ws.send_json({
                        "type": "clothing_equipped",
                        **result,
                        "clothing": player.to_clothing_state(),
                    }))
                except Exception:
                    pass

    def _expire_ground_drops(self):
        """Remove drops older than 60 seconds."""
        now = time.time()
        expired = [did for did, d in self.ground_drops.items()
                   if now - d["created_at"] > 60]
        for did in expired:
            del self.ground_drops[did]

    async def _check_production_storage_full(self):
        """Send one-time notification when a production building's storage is full."""
        now = time.time()
        for chunk in self.chunks.values():
            for b in chunk.buildings:
                if b.get('category') != 'production' or not b.get('last_collected_ts'):
                    continue
                rate = b.get('production_rate', 0)
                cap = b.get('storage_capacity', 0)
                if rate <= 0 or cap <= 0:
                    continue

                hours = (now - b['last_collected_ts']) / 3600
                fill = (hours * rate) / cap

                bld_id = b['id']
                if fill >= 1.0:
                    if bld_id not in self._notified_storage:
                        self._notified_storage.add(bld_id)
                        clan_id = b.get('clan_id')
                        if clan_id:
                            for p in self.players.values():
                                if self._player_clans.get(p.id) == clan_id:
                                    try:
                                        await p.ws.send_json({
                                            "type": "storage_full_notification",
                                            "building_id": bld_id,
                                            "building_name": b.get('type_name', ''),
                                            "resource": b.get('produces_resource', ''),
                                        })
                                    except Exception:
                                        pass
                else:
                    self._notified_storage.discard(bld_id)

    async def _manage_chunks(self):
        """Load/unload chunks based on player positions."""
        needed: Set[Tuple[int, int]] = set()
        for player in self.players.values():
            for ck in player.get_visible_chunks():
                needed.add(ck)

        # Load new chunks
        for ck in needed:
            if ck not in self.chunks:
                await self._load_chunk(ck[0], ck[1])

        # Mark empty chunks for unload
        import time
        now = time.time()
        for ck in list(self.chunks.keys()):
            if ck not in needed:
                if ck not in self._chunk_empty_since:
                    self._chunk_empty_since[ck] = now
            else:
                self._chunk_empty_since.pop(ck, None)

    async def _unload_stale_chunks(self):
        import time
        now = time.time()
        to_unload = [
            ck for ck, since in self._chunk_empty_since.items()
            if now - since > self.CHUNK_UNLOAD_DELAY
        ]
        for ck in to_unload:
            chunk = self.chunks.pop(ck, None)
            self._chunk_empty_since.pop(ck, None)
            self.turrets.pop(ck, None)
            # Remove safe zones that belonged to this chunk
            cx, cy = ck
            min_x, max_x = cx * CHUNK_SIZE, (cx + 1) * CHUNK_SIZE
            min_y, max_y = cy * CHUNK_SIZE, (cy + 1) * CHUNK_SIZE
            self.safe_zones = [
                (sx, sy) for sx, sy in self.safe_zones
                if not (min_x <= sx < max_x and min_y <= sy < max_y)
            ]
            if chunk:
                await self._save_chunk(chunk)

    async def _load_chunk(self, chunk_x: int, chunk_y: int):
        """Load chunk from DB or generate new one."""
        db_data = await world_db.load_chunk_from_db(chunk_x, chunk_y)

        if db_data:
            chunk = WorldChunk(
                chunk_x, chunk_y,
                db_data["terrain"], db_data["resources"],
                db_data["spawn_points"], db_data["seed"]
            )
        else:
            # Generate new chunk
            gen_data = map_generator.generate_chunk(chunk_x, chunk_y)
            chunk = WorldChunk(
                chunk_x, chunk_y,
                gen_data["terrain"], gen_data["resources"],
                gen_data["spawn_points"], gen_data["seed"]
            )
            # Save to DB
            await world_db.save_chunk_to_db(
                chunk_x, chunk_y,
                gen_data["terrain"], gen_data["resources"],
                gen_data["spawn_points"], gen_data["seed"]
            )

        # Load persisted zombies
        db_zombies = await world_db.load_chunk_zombies(chunk_x, chunk_y)
        for zd in db_zombies:
            zombie = WorldZombieEntity(zd["type"], zd["x"], zd["y"], db_id=zd["db_id"])
            zombie.hp = zd["hp"]
            zombie.chunk_x = chunk_x
            zombie.chunk_y = chunk_y
            chunk.zombies[zombie.id] = zombie

        # Load buildings for this chunk (if a clan base is here)
        buildings_data = await world_db.load_buildings_for_chunk(chunk_x, chunk_y)
        chunk.buildings = buildings_data

        # Map building_id -> clan_id for gate logic
        for b in buildings_data:
            if b.get('clan_id'):
                self._building_clans[b['id']] = b['clan_id']

        self.chunks[(chunk_x, chunk_y)] = chunk

        # Load turrets for this chunk (if a clan base is here)
        turret_data = await world_db.load_turrets_for_chunk(chunk_x, chunk_y)
        if turret_data:
            self.turrets[(chunk_x, chunk_y)] = [
                WorldTurret(
                    td["id"], td["x"], td["y"],
                    td["damage"], td["fire_rate"], td["attack_range"], td["type_code"]
                )
                for td in turret_data
            ]

        # Load clan bases for safe zone enforcement
        clan_bases = await world_db.load_clan_bases_for_chunk(chunk_x, chunk_y)
        for cb in clan_bases:
            pos = (cb["x"], cb["y"])
            if pos not in self.safe_zones:
                self.safe_zones.append(pos)
            # Clear any zombies already inside the safe zone
            self._clear_zombies_near(cb["x"], cb["y"], radius=SAFE_ZONE_RADIUS)

    async def _save_chunk(self, chunk: WorldChunk):
        """Save chunk zombies to DB."""
        zombies_data = [
            {"x": z.x, "y": z.y, "type": z.type, "hp": z.hp, "max_hp": z.max_hp}
            for z in chunk.zombies.values()
        ]
        await world_db.save_chunk_zombies(chunk.chunk_x, chunk.chunk_y, zombies_data)

    async def _save_player(self, player: WorldPlayer):
        """Save player state to DB."""
        await world_db.save_world_state(
            player.id,
            player.x, player.y,
            player.hp, not player.is_dead,
            player.to_inventory_state(),
            player.weapon_code,
            player.clothing
        )

    async def _send_state_to_player(self, player: WorldPlayer, events: list):
        """Send world state update to a specific player (only visible entities)."""
        if not player.ws or not player.ws_ready:
            return

        visible_chunks = set(player.get_visible_chunks())

        # Check for new/removed chunks for client
        new_chunks = visible_chunks - player.loaded_chunks
        removed_chunks = player.loaded_chunks - visible_chunks

        # Send new chunk data
        for ck in new_chunks:
            chunk = self.chunks.get(ck)
            if chunk:
                try:
                    await player.ws.send_json({
                        "type": "world_chunk_load",
                        **chunk.to_state()
                    })
                except Exception:
                    pass

        # Notify removed chunks
        for ck in removed_chunks:
            try:
                await player.ws.send_json({
                    "type": "world_chunk_unload",
                    "chunk_x": ck[0],
                    "chunk_y": ck[1],
                })
            except Exception:
                pass

        player.loaded_chunks = visible_chunks.copy()

        # Gather visible entities
        visible_players = []
        visible_zombies = []
        visible_projectiles = []

        for p in self.players.values():
            pchunk = (p.chunk_x, p.chunk_y)
            if pchunk in visible_chunks or any(
                abs(p.chunk_x - ck[0]) <= 1 and abs(p.chunk_y - ck[1]) <= 1
                for ck in visible_chunks
            ):
                visible_players.append(p.to_state())

        for ck in visible_chunks:
            chunk = self.chunks.get(ck)
            if chunk:
                for z in chunk.zombies.values():
                    visible_zombies.append(z.to_state())

        for proj in self.projectiles.values():
            pcx = int(math.floor(proj.x / CHUNK_SIZE))
            pcy = int(math.floor(proj.y / CHUNK_SIZE))
            if (pcx, pcy) in visible_chunks:
                visible_projectiles.append(proj.to_state())

        # Gather visible turret states
        visible_turrets = []
        for ck in visible_chunks:
            for turret in self.turrets.get(ck, []):
                visible_turrets.append({
                    "id": turret.building_id,
                    "x": turret.x,
                    "y": turret.y,
                    "aim_angle": round(turret.aim_angle, 3),
                    "type_code": turret.type_code,
                })

        # Gather visible open gate IDs
        visible_open_gates = []
        for ck in visible_chunks:
            chunk = self.chunks.get(ck)
            if chunk:
                for b in chunk.buildings:
                    if b.get('type_code', '').startswith('gate_') and b['id'] in self._open_gates:
                        visible_open_gates.append(b['id'])

        # Gather visible ground drops
        visible_drops = []
        for d in self.ground_drops.values():
            dcx = int(math.floor(d["x"] / CHUNK_SIZE))
            dcy = int(math.floor(d["y"] / CHUNK_SIZE))
            if (dcx, dcy) in visible_chunks:
                info = CLOTHING_ITEMS.get(d["code"], {})
                visible_drops.append({
                    "id": d["id"],
                    "code": d["code"],
                    "x": d["x"],
                    "y": d["y"],
                    "name": info.get("name", d["code"]),
                    "rarity": info.get("rarity", "common"),
                })

        # Filter events relevant to this player
        player_events = []
        for event in events:
            etype = event.get("type", "")
            if etype == "world_player_died" and event["player_id"] == player.id:
                player_events.append(event)
            elif etype == "world_zombie_killed" and event.get("killer_id") == player.id:
                # Add loot to player inventory
                loot = event.get("loot", {})
                for resource, amount in loot.items():
                    player.collect_resource(resource, amount)
                player_events.append(event)
            elif etype in ("world_zombie_killed", "world_zombie_hurt"):
                player_events.append(event)

        # Broken clothing notification
        if player._broken_items:
            player_events.append({
                "type": "clothing_broken",
                "items": [{"code": c, "name": CLOTHING_ITEMS.get(c, {}).get("name", c)}
                          for c in player._broken_items],
            })
            player._broken_items.clear()

        # Send state
        try:
            await player.ws.send_json({
                "type": "world_state",
                "players": visible_players,
                "zombies": visible_zombies,
                "projectiles": visible_projectiles,
                "turrets": visible_turrets,
                "open_gates": visible_open_gates,
                "ground_drops": visible_drops,
                "inventory": player.to_inventory_state(),
                "clothing": player.to_clothing_state(),
                "events": player_events,
            })
        except Exception:
            pass

    async def _send_to_player(self, player: WorldPlayer, msg: dict):
        if player.ws:
            try:
                await player.ws.send_json(msg)
            except Exception:
                pass

    async def _load_chunks_around(self, player: WorldPlayer):
        """Ensure all chunks around player are loaded."""
        for ck in player.get_visible_chunks():
            if ck not in self.chunks:
                await self._load_chunk(ck[0], ck[1])

    async def refresh_buildings_for_base(self, base_x: float, base_y: float):
        """Reload buildings & turrets for the chunk that contains a clan base.
        Called after placing or demolishing a building via REST API."""
        cx = int(math.floor(base_x / CHUNK_SIZE))
        cy = int(math.floor(base_y / CHUNK_SIZE))
        chunk = self.chunks.get((cx, cy))
        if not chunk:
            return

        # Reload buildings from DB
        buildings_data = await world_db.load_buildings_for_chunk(cx, cy)
        chunk.buildings = buildings_data

        # Reload turrets from DB
        turret_data = await world_db.load_turrets_for_chunk(cx, cy)
        if turret_data:
            self.turrets[(cx, cy)] = [
                WorldTurret(
                    td["id"], td["x"], td["y"],
                    td["damage"], td["fire_rate"], td["attack_range"], td["type_code"]
                )
                for td in turret_data
            ]
        else:
            self.turrets.pop((cx, cy), None)

        # Re-send chunk to all players who have it loaded
        for player in self.players.values():
            if (cx, cy) in player.loaded_chunks:
                try:
                    await player.ws.send_json({
                        "type": "world_chunk_buildings_update",
                        "chunk_x": cx,
                        "chunk_y": cy,
                        "buildings": buildings_data,
                    })
                except Exception:
                    pass

    def collect_resource_for_player(self, player_id: int) -> Optional[dict]:
        """Try to collect a resource near the player."""
        player = self.players.get(player_id)
        if not player or player.is_dead:
            return None

        cx, cy = player.chunk_x, player.chunk_y
        # Check current and adjacent chunks
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                chunk = self.chunks.get((cx + dx, cy + dy))
                if chunk:
                    node = chunk.find_resource_near(player.x, player.y, 60)
                    if node:
                        res_type, amount = node.collect()
                        # Trash cans give random ammo or meds
                        if res_type == "trash":
                            if random.random() < 0.7:
                                res_type = "ammo"
                                amount = random.randint(5, 15)
                            else:
                                res_type = "meds"
                                amount = random.randint(1, 2)
                        player.collect_resource(res_type, amount)
                        return {
                            "resource_type": res_type,
                            "amount": amount,
                            "node_id": node.id,
                            "remaining": node.amount,
                        }
        return None


# Global singleton
world_engine = WorldEngine()
