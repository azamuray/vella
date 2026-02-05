"""
Процедурная генерация карты мира
"""

import random
import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# Размер чанка в пикселях
CHUNK_SIZE = 1024  # 1024x1024 пикселей
TILE_SIZE = 32     # 32x32 пикселей на тайл
TILES_PER_CHUNK = CHUNK_SIZE // TILE_SIZE  # 32x32 тайлов в чанке

# Типы тайлов
TILE_GRASS = 0
TILE_DIRT = 1
TILE_FOREST = 2
TILE_ROCK = 3
TILE_WATER = 4
TILE_ROAD = 5


@dataclass
class ResourceNode:
    """Точка добычи ресурсов"""
    x: float
    y: float
    resource_type: str  # metal, wood
    amount: int
    respawn_time: int  # seconds


@dataclass
class SpawnPoint:
    """Точка спавна зомби"""
    x: float
    y: float
    zombie_types: List[str]
    max_zombies: int
    spawn_rate: float  # zombies per minute


class MapGenerator:
    """Генератор процедурной карты"""

    def __init__(self, world_seed: int = 42):
        self.world_seed = world_seed

    def _get_chunk_seed(self, chunk_x: int, chunk_y: int) -> int:
        """Получить seed для конкретного чанка"""
        return hash((self.world_seed, chunk_x, chunk_y)) & 0xFFFFFFFF

    def _noise(self, x: float, y: float, seed: int) -> float:
        """Простой шум для генерации terrain"""
        random.seed(seed + int(x * 1000 + y))
        return random.random()

    def _perlin_like(self, x: float, y: float, seed: int, octaves: int = 4) -> float:
        """Упрощённый perlin-подобный шум"""
        value = 0.0
        amplitude = 1.0
        frequency = 1.0
        max_value = 0.0

        for _ in range(octaves):
            ix, iy = int(x * frequency), int(y * frequency)
            value += self._noise(ix, iy, seed) * amplitude
            max_value += amplitude
            amplitude *= 0.5
            frequency *= 2.0

        return value / max_value

    def generate_chunk(self, chunk_x: int, chunk_y: int) -> Dict:
        """
        Сгенерировать чанк карты

        Returns:
            {
                "terrain": [[tile_type, ...], ...],
                "resources": [ResourceNode, ...],
                "spawn_points": [SpawnPoint, ...]
            }
        """
        seed = self._get_chunk_seed(chunk_x, chunk_y)
        random.seed(seed)

        # Генерация terrain
        terrain = []
        for ty in range(TILES_PER_CHUNK):
            row = []
            for tx in range(TILES_PER_CHUNK):
                # Мировые координаты тайла
                world_x = chunk_x * TILES_PER_CHUNK + tx
                world_y = chunk_y * TILES_PER_CHUNK + ty

                # Шум для определения типа тайла
                noise_val = self._perlin_like(world_x * 0.1, world_y * 0.1, seed)

                if noise_val < 0.15:
                    tile = TILE_WATER
                elif noise_val < 0.3:
                    tile = TILE_DIRT
                elif noise_val < 0.6:
                    tile = TILE_GRASS
                elif noise_val < 0.8:
                    tile = TILE_FOREST
                else:
                    tile = TILE_ROCK

                row.append(tile)
            terrain.append(row)

        # Генерация ресурсов
        resources = []
        num_resources = random.randint(3, 8)
        for _ in range(num_resources):
            tx = random.randint(2, TILES_PER_CHUNK - 3)
            ty = random.randint(2, TILES_PER_CHUNK - 3)

            # Проверяем что не на воде
            if terrain[ty][tx] == TILE_WATER:
                continue

            # Тип ресурса зависит от terrain
            tile = terrain[ty][tx]
            if tile == TILE_ROCK:
                res_type = "metal"
                amount = random.randint(50, 150)
            elif tile == TILE_FOREST:
                res_type = "wood"
                amount = random.randint(30, 100)
            else:
                continue

            # Мировые координаты
            world_x = chunk_x * CHUNK_SIZE + tx * TILE_SIZE + TILE_SIZE // 2
            world_y = chunk_y * CHUNK_SIZE + ty * TILE_SIZE + TILE_SIZE // 2

            resources.append({
                "x": world_x,
                "y": world_y,
                "resource_type": res_type,
                "amount": amount,
                "respawn_time": 3600  # 1 hour
            })

        # Генерация точек спавна зомби
        spawn_points = []
        num_spawns = random.randint(2, 5)

        # Дальше от центра = больше зомби
        distance_from_center = math.sqrt(chunk_x ** 2 + chunk_y ** 2)
        danger_multiplier = min(2.0, 1.0 + distance_from_center * 0.1)

        for _ in range(num_spawns):
            tx = random.randint(5, TILES_PER_CHUNK - 6)
            ty = random.randint(5, TILES_PER_CHUNK - 6)

            if terrain[ty][tx] == TILE_WATER:
                continue

            world_x = chunk_x * CHUNK_SIZE + tx * TILE_SIZE + TILE_SIZE // 2
            world_y = chunk_y * CHUNK_SIZE + ty * TILE_SIZE + TILE_SIZE // 2

            # Типы зомби зависят от опасности зоны
            zombie_types = ["normal"]
            if danger_multiplier > 1.2:
                zombie_types.append("fast")
            if danger_multiplier > 1.5:
                zombie_types.append("tank")
            if danger_multiplier > 1.8 and random.random() < 0.1:
                zombie_types.append("boss")

            spawn_points.append({
                "x": world_x,
                "y": world_y,
                "zombie_types": zombie_types,
                "max_zombies": int(5 * danger_multiplier),
                "spawn_rate": 0.5 * danger_multiplier  # per minute
            })

        return {
            "terrain": terrain,
            "resources": resources,
            "spawn_points": spawn_points,
            "seed": seed
        }

    def get_safe_spawn_position(self, chunk_x: int, chunk_y: int) -> Tuple[float, float]:
        """Найти безопасную позицию для спавна в чанке"""
        chunk_data = self.generate_chunk(chunk_x, chunk_y)
        terrain = chunk_data["terrain"]

        # Ищем тайл с травой или землёй
        for attempt in range(100):
            tx = random.randint(5, TILES_PER_CHUNK - 6)
            ty = random.randint(5, TILES_PER_CHUNK - 6)

            if terrain[ty][tx] in [TILE_GRASS, TILE_DIRT]:
                world_x = chunk_x * CHUNK_SIZE + tx * TILE_SIZE + TILE_SIZE // 2
                world_y = chunk_y * CHUNK_SIZE + ty * TILE_SIZE + TILE_SIZE // 2
                return (world_x, world_y)

        # Fallback to center
        return (
            chunk_x * CHUNK_SIZE + CHUNK_SIZE // 2,
            chunk_y * CHUNK_SIZE + CHUNK_SIZE // 2
        )

    def find_base_location(self, preferred_chunk_x: int = 0, preferred_chunk_y: int = 0) -> Tuple[int, int]:
        """
        Найти подходящее место для базы клана

        Returns:
            (chunk_x, chunk_y) для размещения базы
        """
        # Ищем по спирали от центра
        for radius in range(1, 50):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) != radius and abs(dy) != radius:
                        continue

                    chunk_x = preferred_chunk_x + dx
                    chunk_y = preferred_chunk_y + dy

                    chunk_data = self.generate_chunk(chunk_x, chunk_y)
                    terrain = chunk_data["terrain"]

                    # Проверяем есть ли достаточно места (центр чанка)
                    center = TILES_PER_CHUNK // 2
                    suitable = True
                    for tx in range(center - 5, center + 5):
                        for ty in range(center - 5, center + 5):
                            if terrain[ty][tx] in [TILE_WATER, TILE_ROCK]:
                                suitable = False
                                break
                        if not suitable:
                            break

                    if suitable:
                        return (chunk_x, chunk_y)

        # Fallback
        return (preferred_chunk_x, preferred_chunk_y)


# Singleton instance
map_generator = MapGenerator(world_seed=12345)
