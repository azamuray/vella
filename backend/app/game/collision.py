"""
Collision detection utilities.
"""
import math
from typing import Tuple


def distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """Calculate distance between two points"""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def circle_collision(
    x1: float, y1: float, r1: float,
    x2: float, y2: float, r2: float
) -> bool:
    """Check if two circles collide"""
    return distance(x1, y1, x2, y2) < (r1 + r2)


def point_in_circle(px: float, py: float, cx: float, cy: float, r: float) -> bool:
    """Check if point is inside circle"""
    return distance(px, py, cx, cy) < r


def line_circle_intersection(
    x1: float, y1: float,  # line start
    x2: float, y2: float,  # line end
    cx: float, cy: float,  # circle center
    r: float  # circle radius
) -> bool:
    """Check if line segment intersects circle (for projectiles)"""
    # Vector from start to end
    dx = x2 - x1
    dy = y2 - y1

    # Vector from start to circle center
    fx = x1 - cx
    fy = y1 - cy

    a = dx * dx + dy * dy
    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r

    discriminant = b * b - 4 * a * c

    if discriminant < 0:
        return False

    discriminant = math.sqrt(discriminant)

    t1 = (-b - discriminant) / (2 * a)
    t2 = (-b + discriminant) / (2 * a)

    # Check if intersection is within line segment (0 <= t <= 1)
    return (0 <= t1 <= 1) or (0 <= t2 <= 1)


def normalize(x: float, y: float) -> Tuple[float, float]:
    """Normalize a vector"""
    length = math.sqrt(x * x + y * y)
    if length == 0:
        return 0.0, 0.0
    return x / length, y / length


def angle_to_vector(angle: float) -> Tuple[float, float]:
    """Convert angle (radians) to unit vector"""
    return math.cos(angle), math.sin(angle)


def vector_to_angle(x: float, y: float) -> float:
    """Convert vector to angle (radians)"""
    return math.atan2(y, x)


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value between min and max"""
    return max(min_val, min(max_val, value))
