"""
Wave system and zombie type definitions.
"""
import random
from typing import List, Dict

ZOMBIE_TYPES = {
    "normal": {
        "hp": 50,
        "speed": 80,  # pixels per second
        "damage": 10,
        "coins": 5,
        "size": 60,  # collision radius - generous hitbox for mobile
        "color": "#4a7c59"  # for debug/placeholder
    },
    "fast": {
        "hp": 30,
        "speed": 150,
        "damage": 8,
        "coins": 8,
        "size": 50,
        "color": "#7c4a4a"
    },
    "tank": {
        "hp": 200,
        "speed": 50,
        "damage": 25,
        "coins": 20,
        "size": 80,
        "color": "#4a4a7c"
    },
    "boss": {
        "hp": 500,
        "speed": 40,
        "damage": 50,
        "coins": 100,
        "size": 100,
        "color": "#7c2a2a"
    }
}

# Wave configurations: wave_num -> zombie counts
WAVE_CONFIG = {
    1: {"normal": 10, "fast": 0, "tank": 0, "boss": 0, "spawn_rate": 2.0},
    2: {"normal": 15, "fast": 2, "tank": 0, "boss": 0, "spawn_rate": 1.8},
    3: {"normal": 20, "fast": 5, "tank": 1, "boss": 0, "spawn_rate": 1.5},
    4: {"normal": 22, "fast": 7, "tank": 2, "boss": 0, "spawn_rate": 1.3},
    5: {"normal": 25, "fast": 10, "tank": 3, "boss": 1, "spawn_rate": 1.2},
    6: {"normal": 28, "fast": 12, "tank": 4, "boss": 1, "spawn_rate": 1.1},
    7: {"normal": 30, "fast": 15, "tank": 5, "boss": 1, "spawn_rate": 1.0},
    8: {"normal": 35, "fast": 18, "tank": 6, "boss": 2, "spawn_rate": 0.9},
    9: {"normal": 38, "fast": 20, "tank": 7, "boss": 2, "spawn_rate": 0.85},
    10: {"normal": 40, "fast": 25, "tank": 8, "boss": 2, "spawn_rate": 0.8},
}


class WaveManager:
    def __init__(self):
        self.current_wave = 0
        self.zombies_to_spawn: List[str] = []
        self.spawn_timer = 0.0
        self.spawn_rate = 1.0  # zombies per second
        self.wave_active = False
        self.countdown = 0.0  # countdown before wave starts

    def start_wave(self, wave_num: int) -> Dict:
        """Start a new wave, returns wave info"""
        self.current_wave = wave_num
        config = self._get_wave_config(wave_num)

        # Build spawn queue
        self.zombies_to_spawn = []
        special_zombies = []

        for zombie_type in ["normal", "fast", "tank", "boss"]:
            count = config.get(zombie_type, 0)
            self.zombies_to_spawn.extend([zombie_type] * count)
            if zombie_type != "normal" and count > 0:
                special_zombies.append(f"{count}x {zombie_type}")

        random.shuffle(self.zombies_to_spawn)
        self.spawn_rate = config.get("spawn_rate", 1.0)
        self.spawn_timer = 0.0
        self.wave_active = True

        return {
            "wave": wave_num,
            "zombie_count": len(self.zombies_to_spawn),
            "special_zombies": special_zombies
        }

    def _get_wave_config(self, wave_num: int) -> Dict:
        """Get config for a wave, scaling beyond defined waves"""
        if wave_num in WAVE_CONFIG:
            return WAVE_CONFIG[wave_num].copy()

        # Beyond max defined wave - scale exponentially
        max_defined = max(WAVE_CONFIG.keys())
        base_config = WAVE_CONFIG[max_defined].copy()
        scale = 1.15 ** (wave_num - max_defined)

        return {
            "normal": int(base_config["normal"] * scale),
            "fast": int(base_config["fast"] * scale),
            "tank": int(base_config["tank"] * scale),
            "boss": int(base_config["boss"] * (1 + (wave_num - max_defined) * 0.5)),
            "spawn_rate": max(0.3, base_config["spawn_rate"] - (wave_num - max_defined) * 0.05)
        }

    def update(self, dt: float) -> List[str]:
        """Update spawn timer, returns list of zombies to spawn this tick"""
        if not self.wave_active or not self.zombies_to_spawn:
            return []

        spawned = []
        self.spawn_timer += dt

        spawn_interval = 1.0 / self.spawn_rate
        while self.spawn_timer >= spawn_interval and self.zombies_to_spawn:
            self.spawn_timer -= spawn_interval
            spawned.append(self.zombies_to_spawn.pop(0))

        return spawned

    def is_wave_complete(self, active_zombies: int) -> bool:
        """Check if wave is complete (no more to spawn and none alive)"""
        return self.wave_active and not self.zombies_to_spawn and active_zombies == 0

    def get_wave_bonus(self) -> int:
        """Calculate bonus coins for completing wave"""
        return self.current_wave * 50

    @property
    def zombies_remaining(self) -> int:
        """Total zombies left to spawn"""
        return len(self.zombies_to_spawn)
