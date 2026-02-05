"""
Weapon definitions with real-world models and prices.
"""

WEAPONS = {
    # --- Pistols ---
    "glock_17": {
        "name": "Glock 17",
        "category": "pistol",
        "price_dollars": 500,
        "price_coins": 0,  # Starter weapon
        "damage": 15,
        "fire_rate": 4.0,
        "reload_time": 1.5,
        "magazine_size": 17,
        "spread": 0.05,
        "projectile_speed": 800,
        "pellets": 1,
        "penetration": 1,
        "required_kills": 0
    },
    "beretta_m9": {
        "name": "Beretta M9",
        "category": "pistol",
        "price_dollars": 650,
        "price_coins": 500,
        "damage": 18,
        "fire_rate": 3.5,
        "reload_time": 1.3,
        "magazine_size": 15,
        "spread": 0.04,
        "projectile_speed": 850,
        "pellets": 1,
        "penetration": 1,
        "required_kills": 50
    },
    "desert_eagle": {
        "name": "Desert Eagle",
        "category": "pistol",
        "price_dollars": 1900,
        "price_coins": 2000,
        "damage": 55,
        "fire_rate": 1.5,
        "reload_time": 2.0,
        "magazine_size": 7,
        "spread": 0.08,
        "projectile_speed": 900,
        "pellets": 1,
        "penetration": 2,
        "required_kills": 200
    },

    # --- Shotguns ---
    "remington_870": {
        "name": "Remington 870",
        "category": "shotgun",
        "price_dollars": 400,
        "price_coins": 800,
        "damage": 12,  # per pellet
        "fire_rate": 1.0,
        "reload_time": 3.0,
        "magazine_size": 8,
        "spread": 0.25,
        "projectile_speed": 600,
        "pellets": 8,
        "penetration": 1,
        "required_kills": 100
    },
    "benelli_m4": {
        "name": "Benelli M4",
        "category": "shotgun",
        "price_dollars": 1800,
        "price_coins": 3500,
        "damage": 15,
        "fire_rate": 2.5,
        "reload_time": 2.5,
        "magazine_size": 7,
        "spread": 0.20,
        "projectile_speed": 650,
        "pellets": 8,
        "penetration": 1,
        "required_kills": 500
    },

    # --- Rifles ---
    "ak_47": {
        "name": "AK-47",
        "category": "rifle",
        "price_dollars": 700,
        "price_coins": 1500,
        "damage": 28,
        "fire_rate": 10.0,
        "reload_time": 2.5,
        "magazine_size": 30,
        "spread": 0.12,
        "projectile_speed": 850,
        "pellets": 1,
        "penetration": 2,
        "required_kills": 150
    },
    "m4a1": {
        "name": "M4A1",
        "category": "rifle",
        "price_dollars": 1200,
        "price_coins": 2500,
        "damage": 25,
        "fire_rate": 12.0,
        "reload_time": 2.0,
        "magazine_size": 30,
        "spread": 0.08,
        "projectile_speed": 900,
        "pellets": 1,
        "penetration": 2,
        "required_kills": 300
    },
    "scar_h": {
        "name": "SCAR-H",
        "category": "rifle",
        "price_dollars": 3000,
        "price_coins": 5000,
        "damage": 35,
        "fire_rate": 8.0,
        "reload_time": 2.2,
        "magazine_size": 20,
        "spread": 0.06,
        "projectile_speed": 950,
        "pellets": 1,
        "penetration": 3,
        "required_kills": 750
    },

    # --- Snipers ---
    "remington_700": {
        "name": "Remington 700",
        "category": "sniper",
        "price_dollars": 800,
        "price_coins": 2000,
        "damage": 90,
        "fire_rate": 0.8,
        "reload_time": 3.0,
        "magazine_size": 5,
        "spread": 0.01,
        "projectile_speed": 1200,
        "pellets": 1,
        "penetration": 3,
        "required_kills": 400
    },
    "barrett_m82": {
        "name": "Barrett M82",
        "category": "sniper",
        "price_dollars": 9000,
        "price_coins": 15000,
        "damage": 200,
        "fire_rate": 0.5,
        "reload_time": 4.0,
        "magazine_size": 10,
        "spread": 0.02,
        "projectile_speed": 1500,
        "pellets": 1,
        "penetration": 5,
        "required_kills": 2000
    },

    # === PREMIUM WEAPONS (Stars only) ===
    "awp_dragon": {
        "name": "AWP Dragon Lore",
        "category": "sniper",
        "price_dollars": 0,
        "price_coins": 0,
        "price_stars": 50,  # ~$1
        "damage": 250,
        "fire_rate": 0.6,
        "reload_time": 3.5,
        "magazine_size": 10,
        "spread": 0.01,
        "projectile_speed": 1600,
        "pellets": 1,
        "penetration": 6,
        "required_kills": 0,
        "premium": True,
        "description": "Legendary sniper with dragon skin"
    },
    "minigun": {
        "name": "M134 Minigun",
        "category": "heavy",
        "price_dollars": 0,
        "price_coins": 0,
        "price_stars": 100,  # ~$2
        "damage": 20,
        "fire_rate": 30.0,  # 30 bullets per second!
        "reload_time": 5.0,
        "magazine_size": 200,
        "spread": 0.15,
        "projectile_speed": 800,
        "pellets": 1,
        "penetration": 2,
        "required_kills": 0,
        "premium": True,
        "description": "Devastating firepower"
    },
    "golden_deagle": {
        "name": "Golden Desert Eagle",
        "category": "pistol",
        "price_dollars": 0,
        "price_coins": 0,
        "price_stars": 25,  # ~$0.50
        "damage": 70,
        "fire_rate": 1.8,
        "reload_time": 1.8,
        "magazine_size": 7,
        "spread": 0.06,
        "projectile_speed": 950,
        "pellets": 1,
        "penetration": 3,
        "required_kills": 0,
        "premium": True,
        "description": "Stylish and deadly"
    }
}


def get_weapon(code: str) -> dict:
    """Get weapon by code with defaults"""
    return WEAPONS.get(code, WEAPONS["glock_17"])


def get_starter_weapon() -> str:
    """Return the starter weapon code"""
    return "glock_17"


def get_all_weapons() -> list:
    """Return all weapons sorted by required kills"""
    return sorted(
        [{"code": k, **v} for k, v in WEAPONS.items()],
        key=lambda w: (w["required_kills"], w["price_coins"])
    )
