"""
Room and lobby management.
"""
import random
import string
import asyncio
from typing import Dict, Optional, List, Set
from fastapi import WebSocket

from .player import PlayerEntity
from .zombie import ZombieEntity, ZombieSpawner
from .wave import WaveManager, ZOMBIE_TYPES
from .collision import circle_collision, line_circle_intersection


class Projectile:
    _next_id = 1

    def __init__(self, owner_id: int, x: float, y: float, angle: float, weapon: dict):
        self.id = Projectile._next_id
        Projectile._next_id += 1

        self.owner_id = owner_id
        self.x = x
        self.y = y
        self.angle = angle
        self.speed = weapon["projectile_speed"]
        self.damage = weapon["damage"]
        self.remaining_damage = weapon["damage"]  # Damage left to deal
        self.hit_zombies: Set[int] = set()  # Track already hit zombies

        # Calculate velocity
        import math
        self.vx = math.cos(angle) * self.speed
        self.vy = math.sin(angle) * self.speed

    def update(self, dt: float) -> bool:
        """Update position, returns True if should be removed (out of bounds)"""
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Remove if out of bounds (with margin)
        return self.x < -100 or self.x > 2000 or self.y < -200 or self.y > 1200

    def to_state(self) -> dict:
        return {
            "id": self.id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "angle": round(self.angle, 2),
            "owner_id": self.owner_id
        }


class Room:
    """A game room that can hold up to 10 players"""

    GAME_WIDTH = 1920
    GAME_HEIGHT = 1080
    TICK_RATE = 20  # ticks per second
    MAX_PLAYERS = 10
    WAVE_COUNTDOWN = 3.0  # seconds between waves

    def __init__(self, room_code: str):
        self.room_code = room_code
        self.status = "lobby"  # lobby, countdown, playing, finished

        # Players
        self.players: Dict[int, PlayerEntity] = {}
        self.connections: Dict[int, WebSocket] = {}

        # Game state
        self.zombies: Dict[int, ZombieEntity] = {}
        self.projectiles: Dict[int, Projectile] = {}
        self.wave_manager = WaveManager()
        self.zombie_spawner = ZombieSpawner(self.GAME_WIDTH, self.GAME_HEIGHT)

        self.tick = 0
        self.countdown = 0.0
        self.is_running = False

        # Stats
        self.total_kills = 0

    def add_player(self, player_id: int, username: Optional[str], ws: WebSocket) -> PlayerEntity:
        """Add a player to the room"""
        # Spawn position at bottom of screen
        x = self.GAME_WIDTH / 2 + random.uniform(-200, 200)
        y = self.GAME_HEIGHT - 100

        player = PlayerEntity(player_id, username, x, y)
        self.players[player_id] = player
        self.connections[player_id] = ws

        return player

    def remove_player(self, player_id: int):
        """Remove a player from the room"""
        self.players.pop(player_id, None)
        self.connections.pop(player_id, None)

    def get_player(self, player_id: int) -> Optional[PlayerEntity]:
        return self.players.get(player_id)

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def is_empty(self) -> bool:
        return len(self.players) == 0

    @property
    def is_full(self) -> bool:
        return len(self.players) >= self.MAX_PLAYERS

    def all_players_ready(self) -> bool:
        """Check if all players are ready"""
        if len(self.players) == 0:
            return False
        return all(p.is_ready for p in self.players.values())

    def all_players_dead(self) -> bool:
        """Check if all players are dead"""
        return all(p.is_dead for p in self.players.values())

    async def broadcast(self, message: dict):
        """Send message to all players in room"""
        disconnected = []
        for player_id, ws in self.connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(player_id)

        # Clean up disconnected
        for player_id in disconnected:
            self.remove_player(player_id)

    async def send_to_player(self, player_id: int, message: dict):
        """Send message to specific player"""
        ws = self.connections.get(player_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.remove_player(player_id)

    def start_game(self):
        """Start the game from lobby"""
        print(f"[Room {self.room_code}] Starting game with {len(self.players)} players")
        self.status = "countdown"
        self.countdown = self.WAVE_COUNTDOWN
        self.wave_manager.current_wave = 0

        # Reset all players
        for i, player in enumerate(self.players.values()):
            player.is_ready = False
            player.kills = 0
            player.coins_earned = 0
            player.hp = player.max_hp
            player.is_dead = False

            # Spread players across bottom
            player.x = 200 + i * 150
            player.y = self.GAME_HEIGHT - 100

    def update(self, dt: float) -> List[dict]:
        """
        Update game state. Returns list of events to broadcast.
        """
        events = []

        if self.status == "countdown":
            self.countdown -= dt
            if self.countdown <= 0:
                self.status = "playing"
                next_wave = self.wave_manager.current_wave + 1
                wave_info = self.wave_manager.start_wave(next_wave)
                print(f"[Room {self.room_code}] Wave {next_wave} started: {wave_info}")
                events.append({"type": "wave_start", **wave_info})

        elif self.status == "playing":
            # Spawn zombies
            for zombie_type in self.wave_manager.update(dt):
                zombie = self.zombie_spawner.spawn_zombie(zombie_type)
                self.zombies[zombie.id] = zombie
                print(f"[Room {self.room_code}] Spawned zombie {zombie.id} type={zombie_type} at ({zombie.x:.0f}, {zombie.y:.0f})")

            # Update players
            players_list = list(self.players.values())
            for player in players_list:
                if player.is_dead and player.can_respawn():
                    # Respawn player
                    x = self.GAME_WIDTH / 2 + random.uniform(-100, 100)
                    y = self.GAME_HEIGHT - 100
                    player.respawn(x, y)
                    events.append({
                        "type": "player_respawn",
                        "player_id": player.id,
                        "x": player.x,
                        "y": player.y
                    })
                elif not player.is_dead:
                    if player.update(dt, self.GAME_WIDTH, self.GAME_HEIGHT):
                        # Player shot - create projectiles
                        self._create_projectiles(player, events)

            # Update zombies
            for zombie in list(self.zombies.values()):
                attacked_player_id = zombie.update(dt, players_list)
                if attacked_player_id:
                    player = self.players.get(attacked_player_id)
                    if player and player.take_damage(zombie.damage):
                        events.append({
                            "type": "player_died",
                            "player_id": player.id,
                            "killed_by": zombie.type
                        })

            # Update projectiles
            self._update_projectiles(dt, events)

            # Check wave complete
            if self.wave_manager.is_wave_complete(len(self.zombies)):
                bonus = self.wave_manager.get_wave_bonus()

                # Distribute bonus to alive players
                alive_players = [p for p in self.players.values() if not p.is_dead]
                if alive_players:
                    bonus_per_player = bonus // len(alive_players)
                    for p in alive_players:
                        p.coins_earned += bonus_per_player

                # Go to wave break - wait for players to ready up
                self.status = "wave_break"
                self.wave_manager.wave_active = False

                # Reset all players' ready status
                for p in self.players.values():
                    p.is_ready = False
                    # Heal players between waves
                    p.hp = p.max_hp
                    p.is_dead = False

                print(f"[Room {self.room_code}] Wave {self.wave_manager.current_wave} complete! Waiting for ready...")

                events.append({
                    "type": "wave_complete",
                    "wave": self.wave_manager.current_wave,
                    "bonus_coins": bonus,
                    "next_wave": self.wave_manager.current_wave + 1
                })

            # Check game over (all dead)
            if self.all_players_dead():
                self.status = "finished"
                events.append(self._get_game_over_event())

        self.tick += 1
        return events

    def _create_projectiles(self, player: PlayerEntity, events: list):
        """Create projectiles when player shoots"""
        import math
        weapon = player.weapon
        pellets = weapon.get("pellets", 1)
        spread = weapon["spread"]

        for _ in range(pellets):
            # Add spread to angle
            angle = player.aim_angle + random.uniform(-spread, spread)

            projectile = Projectile(
                owner_id=player.id,
                x=player.x,
                y=player.y,
                angle=angle,
                weapon=weapon
            )
            self.projectiles[projectile.id] = projectile

    def _update_projectiles(self, dt: float, events: list):
        """Update projectiles and check collisions"""
        to_remove = []

        for proj in self.projectiles.values():
            old_x, old_y = proj.x, proj.y

            if proj.update(dt):
                to_remove.append(proj.id)
                continue

            # Check collision with zombies
            for zombie in list(self.zombies.values()):
                # Skip if already hit this zombie
                if zombie.id in proj.hit_zombies:
                    continue

                if line_circle_intersection(
                    old_x, old_y, proj.x, proj.y,
                    zombie.x, zombie.y, zombie.size
                ):
                    # Mark as hit
                    proj.hit_zombies.add(zombie.id)

                    # Calculate damage: min of remaining damage and zombie HP
                    zombie_hp_before = zombie.hp
                    damage_to_deal = min(proj.remaining_damage, zombie_hp_before)

                    if zombie.take_damage(damage_to_deal):
                        # Zombie killed
                        player = self.players.get(proj.owner_id)
                        if player:
                            player.add_kill(zombie.coins)
                        self.total_kills += 1

                        events.append({
                            "type": "zombie_killed",
                            "zombie_id": zombie.id,
                            "killer_id": proj.owner_id,
                            "coins": zombie.coins,
                            "zombie_type": zombie.type
                        })
                        del self.zombies[zombie.id]

                    # Subtract zombie's HP from remaining damage
                    proj.remaining_damage -= zombie_hp_before

                    # Remove projectile if no damage left
                    if proj.remaining_damage <= 0:
                        to_remove.append(proj.id)
                        break

        for proj_id in to_remove:
            self.projectiles.pop(proj_id, None)

    def _get_game_over_event(self) -> dict:
        """Generate game over event"""
        player_stats = []
        total_coins = 0

        for player in self.players.values():
            total_coins += player.coins_earned
            player_stats.append({
                "id": player.id,
                "username": player.username,
                "kills": player.kills,
                "coins": player.coins_earned
            })

        return {
            "type": "game_over",
            "wave_reached": self.wave_manager.current_wave,
            "total_kills": self.total_kills,
            "player_stats": sorted(player_stats, key=lambda x: x["kills"], reverse=True),
            "coins_earned": total_coins
        }

    def get_state(self) -> dict:
        """Get current game state for sync"""
        return {
            "type": "state",
            "tick": self.tick,
            "players": [p.to_state() for p in self.players.values()],
            "zombies": [z.to_state() for z in self.zombies.values()],
            "projectiles": [p.to_state() for p in self.projectiles.values()],
            "wave": self.wave_manager.current_wave,
            "wave_countdown": self.countdown if self.status == "countdown" else None,
            "zombies_remaining": self.wave_manager.zombies_remaining + len(self.zombies)
        }

    def get_lobby_state(self) -> dict:
        """Get lobby state"""
        return {
            "type": "lobby_update",
            "players": [p.to_lobby_state() for p in self.players.values()]
        }


class RoomManager:
    """Manages all active rooms"""

    def __init__(self):
        self.rooms: Dict[str, Room] = {}

    def create_room(self) -> Room:
        """Create a new room with unique code"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if code not in self.rooms:
                break

        room = Room(code)
        self.rooms[code] = room
        return room

    def get_room(self, room_code: str) -> Optional[Room]:
        """Get room by code"""
        return self.rooms.get(room_code)

    def get_or_create_room(self, room_code: Optional[str] = None) -> Room:
        """Get existing room or create new one"""
        if room_code and room_code in self.rooms:
            room = self.rooms[room_code]
            if not room.is_full and room.status == "lobby":
                return room

        return self.create_room()

    def remove_room(self, room_code: str):
        """Remove an empty room"""
        self.rooms.pop(room_code, None)

    def cleanup_empty_rooms(self):
        """Remove all empty rooms"""
        empty_codes = [code for code, room in self.rooms.items() if room.is_empty]
        for code in empty_codes:
            del self.rooms[code]
