"""
Active chunk in memory — holds terrain, resources, zombies, handles spawning.
"""
import random
import time
import math
from typing import Dict, List, Optional, Tuple

from .map_generator import (
    MapGenerator, map_generator,
    CHUNK_SIZE, TILE_SIZE, TILES_PER_CHUNK,
    TILE_WATER, TILE_ROCK
)
from .world_zombie_entity import WorldZombieEntity


class ResourceNode:
    """An active resource node in a chunk"""
    _next_id = 1

    def __init__(self, x: float, y: float, resource_type: str, amount: int, respawn_time: int):
        self.id = ResourceNode._next_id
        ResourceNode._next_id += 1
        self.x = x
        self.y = y
        self.resource_type = resource_type
        self.amount = amount
        self.max_amount = amount
        self.respawn_time = respawn_time
        self.depleted_at: Optional[float] = None

    @property
    def is_available(self) -> bool:
        if self.amount > 0:
            return True
        if self.depleted_at and time.time() - self.depleted_at >= self.respawn_time:
            self.amount = self.max_amount
            self.depleted_at = None
            return True
        return False

    def collect(self, max_take: int = 10) -> Tuple[str, int]:
        """Collect resources. Returns (type, amount_collected)."""
        take = min(self.amount, max_take)
        self.amount -= take
        if self.amount <= 0:
            self.depleted_at = time.time()
        return self.resource_type, take

    def to_state(self) -> dict:
        return {
            "id": self.id,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "type": self.resource_type,
            "amount": self.amount,
            "available": self.is_available,
        }


class WorldChunk:
    """An active chunk loaded into memory."""

    ZOMBIE_SPAWN_INTERVAL = 15.0  # seconds between spawn checks

    def __init__(self, chunk_x: int, chunk_y: int, terrain: list, resources_data: list,
                 spawn_points_data: list, seed: int):
        self.chunk_x = chunk_x
        self.chunk_y = chunk_y
        self.terrain = terrain  # 32x32 grid of tile types
        self.seed = seed

        # Resources
        self.resources: Dict[int, ResourceNode] = {}
        for r in resources_data:
            node = ResourceNode(
                x=r["x"], y=r["y"],
                resource_type=r["resource_type"],
                amount=r["amount"],
                respawn_time=r.get("respawn_time", 3600)
            )
            self.resources[node.id] = node

        # Spawn points
        self.spawn_points = spawn_points_data

        # Buildings (loaded from DB, sent to client)
        self.buildings: list = []

        # Zombies in this chunk
        self.zombies: Dict[int, WorldZombieEntity] = {}

        # Spawn timer
        self.spawn_timer = 0.0
        self.last_update = time.time()

        # Seed initial zombies if none loaded from DB
        if not self.zombies:
            self._seed_initial_zombies()

    def _seed_initial_zombies(self):
        """Spawn a few zombies at each spawn point when chunk is first created."""
        for sp in self.spawn_points:
            initial_count = random.randint(1, 2)
            zombie_types = sp.get("zombie_types", ["normal"])
            for _ in range(initial_count):
                zombie_type = random.choice(zombie_types)
                ox = random.uniform(-150, 150)
                oy = random.uniform(-150, 150)
                zombie = WorldZombieEntity(zombie_type, sp["x"] + ox, sp["y"] + oy)
                zombie.chunk_x = self.chunk_x
                zombie.chunk_y = self.chunk_y
                self.zombies[zombie.id] = zombie

    def get_tile_at_local(self, tx: int, ty: int) -> int:
        """Get tile type at local tile coordinates"""
        if 0 <= tx < TILES_PER_CHUNK and 0 <= ty < TILES_PER_CHUNK:
            return self.terrain[ty][tx]
        return 0  # default grass

    def get_tile_at_world(self, world_x: float, world_y: float) -> Optional[int]:
        """Get tile type at world pixel coordinates (if within this chunk)"""
        local_x = world_x - self.chunk_x * CHUNK_SIZE
        local_y = world_y - self.chunk_y * CHUNK_SIZE
        if 0 <= local_x < CHUNK_SIZE and 0 <= local_y < CHUNK_SIZE:
            tx = int(local_x / TILE_SIZE)
            ty = int(local_y / TILE_SIZE)
            return self.get_tile_at_local(tx, ty)
        return None

    def _get_walls(self) -> list:
        """Extract wall and gate buildings for zombie collision checks."""
        walls = []
        for b in self.buildings:
            tc = b.get('type_code', '')
            if tc.startswith('wall_') or tc.startswith('gate_'):
                walls.append(b)
        return walls

    def update(self, dt: float, players: list, safe_zones: list = None) -> List[dict]:
        """Update chunk: spawn zombies, update existing ones. Returns events."""
        events = []

        # Spawn zombies
        self.spawn_timer += dt
        if self.spawn_timer >= self.ZOMBIE_SPAWN_INTERVAL:
            self.spawn_timer = 0.0
            self._try_spawn_zombies(safe_zones)

        # Get walls for collision
        walls = self._get_walls()

        # Update zombies
        for zombie in list(self.zombies.values()):
            result = zombie.update(dt, players, safe_zones, walls)

            if result.get('attacked_player'):
                events.append({
                    "type": "world_zombie_attack",
                    "zombie_id": zombie.id,
                    "player_id": result['attacked_player'],
                    "damage": zombie.damage,
                })

            for wd in result.get('wall_damage', []):
                events.append({
                    "type": "world_wall_damage",
                    "wall_id": wd['wall_id'],
                    "damage": wd['damage'],
                })

        return events

    def _try_spawn_zombies(self, safe_zones: list = None):
        """Try to spawn zombies at spawn points"""
        for sp in self.spawn_points:
            # Skip spawn points inside clan base safe zones
            if safe_zones:
                in_safe = False
                for sx, sy in safe_zones:
                    dx = sp["x"] - sx
                    dy = sp["y"] - sy
                    if dx * dx + dy * dy < 450 * 450:  # SAFE_ZONE_RADIUS squared
                        in_safe = True
                        break
                if in_safe:
                    continue

            # Count zombies near this spawn point
            nearby = sum(1 for z in self.zombies.values()
                        if abs(z.x - sp["x"]) < 200 and abs(z.y - sp["y"]) < 200)

            if nearby >= sp.get("max_zombies", 5):
                continue

            # Spawn chance based on rate
            rate = sp.get("spawn_rate", 0.5)
            if random.random() < rate * 0.5:  # Scale down since we check periodically
                zombie_type = random.choice(sp.get("zombie_types", ["normal"]))
                # Random offset from spawn point
                ox = random.uniform(-100, 100)
                oy = random.uniform(-100, 100)
                zombie = WorldZombieEntity(zombie_type, sp["x"] + ox, sp["y"] + oy)
                zombie.chunk_x = self.chunk_x
                zombie.chunk_y = self.chunk_y
                self.zombies[zombie.id] = zombie

    def find_resource_near(self, x: float, y: float, radius: float = 50) -> Optional[ResourceNode]:
        """Find a collectible resource near given position"""
        for node in self.resources.values():
            if node.is_available:
                dx = node.x - x
                dy = node.y - y
                if math.sqrt(dx * dx + dy * dy) < radius:
                    return node
        return None

    def to_state(self) -> dict:
        """Serialize chunk data for sending to client"""
        return {
            "chunk_x": self.chunk_x,
            "chunk_y": self.chunk_y,
            "terrain": self.terrain,
            "resources": [r.to_state() for r in self.resources.values()],
            "buildings": self.buildings,
        }
