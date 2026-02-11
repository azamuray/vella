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

    # Damage per second a single zombie deals to a wall
    WALL_DPS = 100.0 / 3600.0  # wooden wall (100 HP) breaks in 1 hour per zombie

    def update(self, dt: float, players: List, safe_zones: list = None,
               walls: list = None) -> dict:
        """
        Update zombie AI. Returns dict with:
          - 'attacked_player': player_id or None
          - 'wall_damage': list of {'wall_id': id, 'damage': float} or []
        players: list of WorldPlayer
        walls: list of {'id', 'x', 'y', 'width', 'height', 'type_code'}
        """
        result = {'attacked_player': None, 'wall_damage': []}

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
            return result

        self.target_id = nearest_player.id

        # Attack range
        attack_range = self.size + nearest_player.PLAYER_SIZE
        if nearest_dist < attack_range:
            if self.attack_cooldown <= 0:
                self.attack_cooldown = 1.0
                result['attacked_player'] = nearest_player.id
        else:
            # Move towards player (only if within aggro range)
            aggro_range = 600  # pixels
            if nearest_dist < aggro_range:
                dx = nearest_player.x - self.x
                dy = nearest_player.y - self.y
                nx, ny = normalize(dx, dy)
                new_x = self.x + nx * self.speed * dt
                new_y = self.y + ny * self.speed * dt

                # Don't enter clan base safe zones
                if safe_zones:
                    for sx, sy in safe_zones:
                        ddx = new_x - sx
                        ddy = new_y - sy
                        if ddx * ddx + ddy * ddy < 450 * 450:
                            return result

                # Check wall collisions
                blocked = False
                if walls:
                    for wall in walls:
                        wx, wy = wall['x'], wall['y']
                        ww, wh = wall['width'], wall['height']
                        # Check if new position overlaps with wall rect (with zombie size margin)
                        if (new_x + self.size > wx and new_x - self.size < wx + ww and
                                new_y + self.size > wy and new_y - self.size < wy + wh):
                            blocked = True
                            # Attack the wall
                            dmg = self.WALL_DPS * dt
                            result['wall_damage'].append({
                                'wall_id': wall['id'],
                                'damage': dmg,
                            })
                            break

                if not blocked:
                    self.x = new_x
                    self.y = new_y

        return result

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
