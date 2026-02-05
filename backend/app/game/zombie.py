"""
Zombie entity and spawning logic.
"""
import math
import random
from typing import Optional, Dict, Any, List, Tuple
from .wave import ZOMBIE_TYPES
from .collision import distance, normalize


class ZombieEntity:
    _next_id = 1

    def __init__(self, zombie_type: str, x: float, y: float):
        self.id = ZombieEntity._next_id
        ZombieEntity._next_id += 1

        self.type = zombie_type
        self.x = x
        self.y = y

        # Get type stats
        stats = ZOMBIE_TYPES.get(zombie_type, ZOMBIE_TYPES["normal"])
        self.hp = stats["hp"]
        self.max_hp = stats["hp"]
        self.speed = stats["speed"]
        self.damage = stats["damage"]
        self.coins = stats["coins"]
        self.size = stats["size"]

        # AI state
        self.target_id: Optional[int] = None
        self.attack_cooldown = 0.0

    def update(self, dt: float, players: List['PlayerEntity']) -> Optional[int]:
        """
        Update zombie AI. Returns player ID if attacking, None otherwise.
        """
        # Update attack cooldown
        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt

        # Find nearest alive player
        nearest_player = None
        nearest_dist = float('inf')

        for player in players:
            if player.is_dead:
                continue
            d = distance(self.x, self.y, player.x, player.y)
            if d < nearest_dist:
                nearest_dist = d
                nearest_player = player

        if not nearest_player:
            return None

        self.target_id = nearest_player.id

        # Check if close enough to attack
        attack_range = self.size + nearest_player.PLAYER_SIZE
        if nearest_dist < attack_range:
            # Attack
            if self.attack_cooldown <= 0:
                self.attack_cooldown = 1.0  # Attack once per second
                return nearest_player.id
        else:
            # Move towards player
            dx = nearest_player.x - self.x
            dy = nearest_player.y - self.y
            nx, ny = normalize(dx, dy)

            self.x += nx * self.speed * dt
            self.y += ny * self.speed * dt

        return None

    def take_damage(self, damage: int) -> bool:
        """Take damage, returns True if zombie died"""
        self.hp -= damage
        return self.hp <= 0

    def to_state(self) -> Dict[str, Any]:
        """Convert to state dict for network sync"""
        return {
            "id": self.id,
            "type": self.type,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "hp": self.hp,
            "max_hp": self.max_hp
        }


class ZombieSpawner:
    """Handles zombie spawn positions"""

    def __init__(self, game_width: int, game_height: int):
        self.game_width = game_width
        self.game_height = game_height
        self.spawn_margin = 50  # Distance from edge

    def get_spawn_position(self) -> Tuple[float, float]:
        """
        Get a random spawn position at the top of the screen.
        Zombies spawn from the top and move down.
        """
        x = random.uniform(self.spawn_margin, self.game_width - self.spawn_margin)
        y = -self.spawn_margin  # Spawn above screen
        return x, y

    def spawn_zombie(self, zombie_type: str) -> ZombieEntity:
        """Spawn a zombie of given type"""
        x, y = self.get_spawn_position()
        return ZombieEntity(zombie_type, x, y)
