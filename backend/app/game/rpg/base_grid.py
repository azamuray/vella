"""
Base grid utilities — 16x16 grid for clan buildings.
"""
from typing import List, Tuple, Optional

BASE_GRID_SIZE = 16  # 16x16 cells


def can_place_building(grid: List[List[Optional[int]]], x: int, y: int,
                       width: int, height: int) -> bool:
    """
    Check if a building can be placed at (x, y) with given dimensions.
    grid: 16x16 array where None = empty, int = building_id
    """
    if x < 0 or y < 0 or x + width > BASE_GRID_SIZE or y + height > BASE_GRID_SIZE:
        return False

    for dy in range(height):
        for dx in range(width):
            if grid[y + dy][x + dx] is not None:
                return False

    return True


def place_building(grid: List[List[Optional[int]]], x: int, y: int,
                   width: int, height: int, building_id: int):
    """Place a building on the grid."""
    for dy in range(height):
        for dx in range(width):
            grid[y + dy][x + dx] = building_id


def remove_building(grid: List[List[Optional[int]]], building_id: int):
    """Remove a building from the grid."""
    for y in range(BASE_GRID_SIZE):
        for x in range(BASE_GRID_SIZE):
            if grid[y][x] == building_id:
                grid[y][x] = None


def build_grid_from_buildings(buildings: list) -> List[List[Optional[int]]]:
    """Build grid state from list of building dicts with grid_x, grid_y, width, height, id."""
    grid = [[None for _ in range(BASE_GRID_SIZE)] for _ in range(BASE_GRID_SIZE)]
    for b in buildings:
        w = b.get("width", 1)
        h = b.get("height", 1)
        for dy in range(h):
            for dx in range(w):
                gy = b["grid_y"] + dy
                gx = b["grid_x"] + dx
                if 0 <= gy < BASE_GRID_SIZE and 0 <= gx < BASE_GRID_SIZE:
                    grid[gy][gx] = b["id"]
    return grid
