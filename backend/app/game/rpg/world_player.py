"""
Player entity for open world mode.
Reuses the weapon system from room-based game.
"""
import math
import time
from typing import Optional, Dict, Any, List
from ..weapons import get_weapon, get_starter_weapon
from ..collision import clamp, normalize

from .map_generator import CHUNK_SIZE, TILE_SIZE, TILES_PER_CHUNK, TILE_WATER, TILE_ROCK


class WorldPlayer:
    SPEED = 180  # pixels per second (slightly slower in open world)
    MAX_HP = 100
    RESPAWN_TIME = 5.0
    PLAYER_SIZE = 20
    VIEW_RANGE = 1  # sees 3x3 chunks (current ± 1)

    def __init__(self, player_id: int, username: Optional[str], x: float, y: float):
        self.id = player_id
        self.username = username

        # Position in world coordinates
        self.x = x
        self.y = y

        # Stats
        self.hp = self.MAX_HP
        self.max_hp = self.MAX_HP
        self.is_dead = False
        self.death_time = 0.0

        # Weapon (same system as rooms)
        self.weapon_code = get_starter_weapon()
        self.ammo = 0
        self.reloading = False
        self.reload_timer = 0.0
        self.fire_cooldown = 0.0

        # Input state
        self.move_x = 0.0
        self.move_y = 0.0
        self.aim_x = 0.0
        self.aim_y = -1.0
        self.shooting = False
        self.wants_reload = False

        # Inventory
        self.metal = 0
        self.wood = 0
        self.food = 0
        self.ammo_inv = 30
        self.meds = 1

        # Stats
        self.kills = 0
        self.coins_earned = 0

        # WebSocket reference
        self.ws = None

        # Track which chunks are loaded on client
        self.loaded_chunks: set = set()

        # Initialize ammo
        self._refill_ammo()

    def _refill_ammo(self):
        weapon = get_weapon(self.weapon_code)
        self.ammo = weapon["magazine_size"]

    @property
    def aim_angle(self) -> float:
        return math.atan2(self.aim_y, self.aim_x)

    @property
    def weapon(self) -> dict:
        return get_weapon(self.weapon_code)

    @property
    def chunk_x(self) -> int:
        return int(math.floor(self.x / CHUNK_SIZE))

    @property
    def chunk_y(self) -> int:
        return int(math.floor(self.y / CHUNK_SIZE))

    def get_visible_chunks(self) -> List[tuple]:
        """Get list of (chunk_x, chunk_y) that player can see"""
        cx, cy = self.chunk_x, self.chunk_y
        chunks = []
        for dx in range(-self.VIEW_RANGE, self.VIEW_RANGE + 1):
            for dy in range(-self.VIEW_RANGE, self.VIEW_RANGE + 1):
                chunks.append((cx + dx, cy + dy))
        return chunks

    def apply_input(self, move_x: float, move_y: float, aim_x: float, aim_y: float,
                    shooting: bool, reload: bool):
        self.move_x = clamp(move_x, -1.0, 1.0)
        self.move_y = clamp(move_y, -1.0, 1.0)

        if abs(aim_x) > 0.1 or abs(aim_y) > 0.1:
            length = math.sqrt(aim_x * aim_x + aim_y * aim_y)
            if length > 0:
                self.aim_x = aim_x / length
                self.aim_y = aim_y / length

        self.shooting = shooting
        self.wants_reload = reload

    def update(self, dt: float, get_tile_at=None) -> bool:
        """
        Update player. Returns True if player can shoot this tick.
        get_tile_at: callback(world_x, world_y) -> tile_type or None
        """
        if self.is_dead:
            return False

        # Movement with terrain collision
        if abs(self.move_x) > 0.01 or abs(self.move_y) > 0.01:
            nx, ny = normalize(self.move_x, self.move_y)
            new_x = self.x + nx * self.SPEED * dt
            new_y = self.y + ny * self.SPEED * dt

            # Check terrain collision
            if get_tile_at:
                tile = get_tile_at(new_x, new_y)
                if tile not in (TILE_WATER, TILE_ROCK):
                    self.x = new_x
                    self.y = new_y
            else:
                self.x = new_x
                self.y = new_y

        # Fire cooldown
        if self.fire_cooldown > 0:
            self.fire_cooldown -= dt

        # Reload
        if self.reloading:
            self.reload_timer -= dt
            if self.reload_timer <= 0:
                self._refill_ammo()
                self.reloading = False
                self.reload_timer = 0.0
        elif self.wants_reload and self.ammo < self.weapon["magazine_size"]:
            self._start_reload()

        # Shooting
        can_shoot = (
            self.shooting and
            not self.reloading and
            self.ammo > 0 and
            self.fire_cooldown <= 0
        )

        if can_shoot:
            self.ammo -= 1
            self.fire_cooldown = 1.0 / self.weapon["fire_rate"]
            if self.ammo == 0:
                self._start_reload()

        return can_shoot

    def _start_reload(self):
        if not self.reloading:
            self.reloading = True
            self.reload_timer = self.weapon["reload_time"]

    def take_damage(self, damage: int) -> bool:
        if self.is_dead:
            return False
        self.hp -= damage
        if self.hp <= 0:
            self.hp = 0
            self.is_dead = True
            self.death_time = time.time()
            return True
        return False

    def respawn(self, x: float, y: float):
        self.x = x
        self.y = y
        self.hp = self.max_hp
        self.is_dead = False
        self._refill_ammo()
        self.reloading = False

    def can_respawn(self) -> bool:
        if not self.is_dead:
            return False
        return time.time() - self.death_time >= self.RESPAWN_TIME

    def switch_weapon(self, weapon_code: str):
        from ..weapons import WEAPONS
        if weapon_code in WEAPONS:
            self.weapon_code = weapon_code
            self._refill_ammo()
            self.reloading = False
            self.fire_cooldown = 0.5

    def use_medkit(self) -> bool:
        """Use a medkit. Returns True if used."""
        if self.meds <= 0 or self.is_dead or self.hp >= self.max_hp:
            return False
        self.meds -= 1
        self.hp = min(self.hp + 40, self.max_hp)
        return True

    def collect_resource(self, resource_type: str, amount: int):
        """Add resources to inventory"""
        if resource_type == "metal":
            self.metal += amount
        elif resource_type == "wood":
            self.wood += amount
        elif resource_type == "food":
            self.food += amount
        elif resource_type == "ammo":
            self.ammo_inv += amount
        elif resource_type == "meds":
            self.meds += amount

    def add_kill(self, coins: int):
        self.kills += 1
        self.coins_earned += coins

    def to_state(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "hp": self.hp,
            "max_hp": self.max_hp,
            "weapon": self.weapon_code,
            "ammo": self.ammo,
            "max_ammo": self.weapon["magazine_size"],
            "reloading": self.reloading,
            "reload_progress": 1.0 - (self.reload_timer / self.weapon["reload_time"]) if self.reloading else 1.0,
            "aim_angle": round(self.aim_angle, 2),
            "is_dead": self.is_dead,
        }

    def to_inventory_state(self) -> Dict[str, Any]:
        return {
            "metal": self.metal,
            "wood": self.wood,
            "food": self.food,
            "ammo": self.ammo_inv,
            "meds": self.meds,
        }
