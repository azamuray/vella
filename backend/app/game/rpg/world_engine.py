"""
World Engine — manages the open world tick loop, chunk loading/unloading,
and sending state updates to players.
"""
import asyncio
import math
import random
from typing import Dict, List, Optional, Set, Tuple
from fastapi import WebSocket

from .world_player import WorldPlayer
from .world_zombie_entity import WorldZombieEntity
from .world_chunk import WorldChunk
from .map_generator import map_generator, CHUNK_SIZE, TILE_SIZE, TILE_WATER, TILE_ROCK
from . import world_db
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


class WorldEngine:
    """Main world engine — runs independently from room GameEngine."""

    TICK_RATE = 20
    CHUNK_UNLOAD_DELAY = 30  # seconds before unloading empty chunk

    def __init__(self):
        self.players: Dict[int, WorldPlayer] = {}
        self.chunks: Dict[Tuple[int, int], WorldChunk] = {}
        self.projectiles: Dict[int, WorldProjectile] = {}
        self.turrets: Dict[Tuple[int, int], List[WorldTurret]] = {}  # chunk_key -> turrets
        self.running = False
        self._task = None

        # Track when chunks became empty (for delayed unload)
        self._chunk_empty_since: Dict[Tuple[int, int], float] = {}

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

        # Set weapon
        player.switch_weapon(state.get("equipped_weapon", "glock_17"))

        self.players[player_id] = player

        # Ensure visible chunks are loaded
        await self._load_chunks_around(player)

        # Clear zombies near spawn point (safe zone)
        self._clear_zombies_near(player.x, player.y, radius=300)

        return player

    async def remove_player(self, player_id: int):
        """Remove player from world, save state."""
        player = self.players.pop(player_id, None)
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
                can_shoot = player.update(dt, self._get_tile_at)
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
                chunk_events = chunk.update(dt, players_in_range)
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

        # Update projectiles
        self._update_projectiles(dt, events)

        # Update turrets — auto-fire at nearby zombies
        self._update_turrets(dt, events)

        # Unload stale chunks
        if tick % 60 == 0:  # every 3s
            await self._unload_stale_chunks()

        # Send state to each player (only what they can see)
        for player in list(self.players.values()):
            await self._send_state_to_player(player, events)

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

                            events.append({
                                "type": "world_zombie_killed",
                                "zombie_id": zombie.id,
                                "killer_id": proj.owner_id,
                                "coins": zombie.coins,
                                "loot": loot,
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
                if not turret.can_fire():
                    continue

                # Find nearest zombie in range
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

                turret.fire()

                # Create projectile aimed at the zombie
                angle = math.atan2(best_zombie.y - turret.y, best_zombie.x - turret.x)
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

    def _clear_zombies_near(self, x: float, y: float, radius: float = 300):
        """Remove all zombies within radius of a point (safe zone)."""
        for chunk in self.chunks.values():
            to_remove = [
                zid for zid, z in chunk.zombies.items()
                if distance(x, y, z.x, z.y) < radius
            ]
            for zid in to_remove:
                del chunk.zombies[zid]

    def _generate_loot(self, zombie_type: str) -> dict:
        """Generate random loot from zombie kill."""
        loot = {}
        if random.random() < 0.3:
            loot["ammo"] = random.randint(3, 10)
        if random.random() < 0.15:
            loot["food"] = random.randint(1, 3)
        if random.random() < 0.05:
            loot["meds"] = 1
        if zombie_type in ("tank", "boss"):
            if random.random() < 0.4:
                loot["metal"] = random.randint(5, 20)
        return loot

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
            player.weapon_code
        )

    async def _send_state_to_player(self, player: WorldPlayer, events: list):
        """Send world state update to a specific player (only visible entities)."""
        if not player.ws:
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

        # Send state
        try:
            await player.ws.send_json({
                "type": "world_state",
                "players": visible_players,
                "zombies": visible_zombies,
                "projectiles": visible_projectiles,
                "inventory": player.to_inventory_state(),
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
