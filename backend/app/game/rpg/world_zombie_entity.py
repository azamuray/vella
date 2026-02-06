"""
Zombie entity for open world.
Same AI as room zombies — find nearest player, move, attack.
"""
import math
from typing import Optional, Dict, Any, List
from ..wave import ZOMBIE_TYPES
from ..collision import distance, normalize


class WorldZombieEntity:
    _next_id = 100000  # offset to avoid collisions with room zombie IDs

    def __init__(self, zombie_type: str, x: float, y: float, db_id: Optional[int] = None):
        self.id = WorldZombieEntity._next_id
        WorldZombieEntity._next_id += 1

        self.db_id = db_id  # ID in world_zombies table (None if not persisted yet)
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

        # Chunk tracking
        self.chunk_x = 0
        self.chunk_y = 0

        # AI state
        self.target_id: Optional[int] = None
        self.attack_cooldown = 0.0

    def update(self, dt: float, players: List) -> Optional[int]:
        """
        Update zombie AI. Returns player ID if attacking.
        players: list of WorldPlayer
        """
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

        # Attack range
        attack_range = self.size + nearest_player.PLAYER_SIZE
        if nearest_dist < attack_range:
            if self.attack_cooldown <= 0:
                self.attack_cooldown = 1.0
                return nearest_player.id
        else:
            # Move towards player (only if within aggro range)
            aggro_range = 600  # pixels
            if nearest_dist < aggro_range:
                dx = nearest_player.x - self.x
                dy = nearest_player.y - self.y
                nx, ny = normalize(dx, dy)
                self.x += nx * self.speed * dt
                self.y += ny * self.speed * dt

        return None

    def take_damage(self, damage: int) -> bool:
        self.hp -= damage
        return self.hp <= 0

    def to_state(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "hp": self.hp,
            "max_hp": self.max_hp,
            "size": self.size,
        }
