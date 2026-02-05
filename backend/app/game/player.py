"""
Player entity for the game.
"""
import math
import time
from typing import Optional, Dict, Any
from .weapons import get_weapon, get_starter_weapon
from .collision import clamp, normalize


class PlayerEntity:
    # Game constants
    SPEED = 200  # pixels per second
    MAX_HP = 100
    RESPAWN_TIME = 3.0  # seconds
    PLAYER_SIZE = 20  # collision radius

    def __init__(self, player_id: int, username: Optional[str], x: float, y: float):
        self.id = player_id
        self.username = username

        # Position
        self.x = x
        self.y = y

        # Stats
        self.hp = self.MAX_HP
        self.max_hp = self.MAX_HP
        self.is_dead = False
        self.death_time = 0.0

        # Weapon
        self.weapon_code = get_starter_weapon()
        self.ammo = 0
        self.reloading = False
        self.reload_timer = 0.0
        self.fire_cooldown = 0.0

        # Input state
        self.move_x = 0.0
        self.move_y = 0.0
        self.aim_x = 0.0
        self.aim_y = 1.0  # Default aim up
        self.shooting = False
        self.wants_reload = False

        # Stats tracking
        self.kills = 0
        self.coins_earned = 0

        # Lobby state
        self.is_ready = False

        # Initialize ammo
        self._refill_ammo()

    def _refill_ammo(self):
        """Fill ammo to magazine size"""
        weapon = get_weapon(self.weapon_code)
        self.ammo = weapon["magazine_size"]

    @property
    def aim_angle(self) -> float:
        """Get aim angle in radians"""
        return math.atan2(self.aim_y, self.aim_x)

    @property
    def weapon(self) -> dict:
        """Get current weapon data"""
        return get_weapon(self.weapon_code)

    def apply_input(self, move_x: float, move_y: float, aim_x: float, aim_y: float,
                    shooting: bool, reload: bool):
        """Apply player input"""
        self.move_x = clamp(move_x, -1.0, 1.0)
        self.move_y = clamp(move_y, -1.0, 1.0)

        # Only update aim if joystick is being used
        if abs(aim_x) > 0.1 or abs(aim_y) > 0.1:
            # Normalize aim vector
            length = math.sqrt(aim_x * aim_x + aim_y * aim_y)
            if length > 0:
                self.aim_x = aim_x / length
                self.aim_y = aim_y / length

        self.shooting = shooting
        self.wants_reload = reload

    def update(self, dt: float, game_width: int, game_height: int) -> bool:
        """
        Update player state. Returns True if player can shoot this tick.
        """
        # Handle respawn
        if self.is_dead:
            return False

        # Movement
        if abs(self.move_x) > 0.01 or abs(self.move_y) > 0.01:
            # Normalize diagonal movement
            nx, ny = normalize(self.move_x, self.move_y)
            self.x += nx * self.SPEED * dt
            self.y += ny * self.SPEED * dt

            # Clamp to game bounds (with margin for player size)
            margin = self.PLAYER_SIZE
            self.x = clamp(self.x, margin, game_width - margin)
            self.y = clamp(self.y, margin, game_height - margin)

        # Update fire cooldown
        if self.fire_cooldown > 0:
            self.fire_cooldown -= dt

        # Handle reload
        if self.reloading:
            self.reload_timer -= dt
            if self.reload_timer <= 0:
                self._refill_ammo()
                self.reloading = False
                self.reload_timer = 0.0
        elif self.wants_reload and self.ammo < self.weapon["magazine_size"]:
            self._start_reload()

        # Check if can shoot
        can_shoot = (
            self.shooting and
            not self.reloading and
            self.ammo > 0 and
            self.fire_cooldown <= 0
        )

        if can_shoot:
            self.ammo -= 1
            self.fire_cooldown = 1.0 / self.weapon["fire_rate"]

            # Auto-reload when empty
            if self.ammo == 0:
                self._start_reload()

        return can_shoot

    def _start_reload(self):
        """Start reloading"""
        if not self.reloading:
            self.reloading = True
            self.reload_timer = self.weapon["reload_time"]

    def take_damage(self, damage: int) -> bool:
        """Take damage, returns True if player died"""
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
        """Respawn player at position"""
        self.x = x
        self.y = y
        self.hp = self.max_hp
        self.is_dead = False
        self._refill_ammo()
        self.reloading = False

    def can_respawn(self) -> bool:
        """Check if enough time has passed to respawn"""
        if not self.is_dead:
            return False
        return time.time() - self.death_time >= self.RESPAWN_TIME

    def switch_weapon(self, weapon_code: str):
        """Switch to a different weapon"""
        from .weapons import WEAPONS
        if weapon_code in WEAPONS:
            self.weapon_code = weapon_code
            self._refill_ammo()
            self.reloading = False
            self.fire_cooldown = 0.5  # Brief cooldown on weapon switch

    def add_kill(self, coins: int):
        """Record a kill and add coins"""
        self.kills += 1
        self.coins_earned += coins

    def to_state(self) -> Dict[str, Any]:
        """Convert to state dict for network sync"""
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
            "is_dead": self.is_dead
        }

    def to_lobby_state(self) -> Dict[str, Any]:
        """Convert to lobby state dict"""
        return {
            "id": self.id,
            "username": self.username,
            "is_ready": self.is_ready,
            "weapon": self.weapon_code,
            "kills": self.kills,
            "highest_wave": 0  # Will be filled from DB
        }
