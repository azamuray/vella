"""
Clothing system — items that drop from zombies and provide armor.
"""
import random

CLOTHING_ITEMS = {
    # Head
    "cap": {
        "slot": "head",
        "name": "Кепка",
        "armor": 0.03,
        "max_durability": 50,
        "rarity": "common",
    },
    "helmet": {
        "slot": "head",
        "name": "Шлем",
        "armor": 0.06,
        "max_durability": 80,
        "rarity": "uncommon",
    },
    "riot_helmet": {
        "slot": "head",
        "name": "Каска",
        "armor": 0.10,
        "max_durability": 120,
        "rarity": "rare",
    },
    # Body
    "tshirt": {
        "slot": "body",
        "name": "Футболка",
        "armor": 0.04,
        "max_durability": 60,
        "rarity": "common",
    },
    "jacket": {
        "slot": "body",
        "name": "Куртка",
        "armor": 0.08,
        "max_durability": 100,
        "rarity": "uncommon",
    },
    "kevlar": {
        "slot": "body",
        "name": "Бронежилет",
        "armor": 0.15,
        "max_durability": 150,
        "rarity": "rare",
    },
    # Legs
    "jeans": {
        "slot": "legs",
        "name": "Джинсы",
        "armor": 0.03,
        "max_durability": 50,
        "rarity": "common",
    },
    "cargo": {
        "slot": "legs",
        "name": "Карго-штаны",
        "armor": 0.06,
        "max_durability": 80,
        "rarity": "uncommon",
    },
    "military_pants": {
        "slot": "legs",
        "name": "Военные штаны",
        "armor": 0.10,
        "max_durability": 120,
        "rarity": "rare",
    },
}

# Drop chance per zombie type
_DROP_CHANCE = {
    "normal": 0.10,
    "fast": 0.15,
    "tank": 0.25,
    "boss": 0.50,
}

# Weighted rarity pools
_RARITY_WEIGHTS = {
    "common": 60,
    "uncommon": 30,
    "rare": 10,
}

# Pre-build pools by rarity
_POOLS = {}
for _code, _item in CLOTHING_ITEMS.items():
    r = _item["rarity"]
    _POOLS.setdefault(r, []).append(_code)


def generate_clothing_drop(zombie_type: str):
    """Generate a random clothing drop from a killed zombie.
    Returns clothing code (str) or None."""
    chance = _DROP_CHANCE.get(zombie_type, 0.10)
    if random.random() > chance:
        return None

    # Weighted rarity selection
    rarities = list(_RARITY_WEIGHTS.keys())
    weights = list(_RARITY_WEIGHTS.values())
    rarity = random.choices(rarities, weights=weights, k=1)[0]

    pool = _POOLS.get(rarity, [])
    if not pool:
        return None

    return random.choice(pool)
