"""
Типы зданий для базы клана
"""
from sqlalchemy import select

BUILDING_TYPES = [
    # Защитные
    {
        "code": "wall_wood",
        "name": "Деревянная стена",
        "category": "defense",
        "width": 1, "height": 1,
        "max_hp": 100,
        "cost_wood": 20,
        "build_time": 30
    },
    {
        "code": "wall_metal",
        "name": "Металлическая стена",
        "category": "defense",
        "width": 1, "height": 1,
        "max_hp": 300,
        "cost_metal": 30, "cost_wood": 10,
        "build_time": 60
    },
    {
        "code": "turret_basic",
        "name": "Базовая турель",
        "category": "defense",
        "width": 1, "height": 1,
        "max_hp": 150,
        "damage": 10, "fire_rate": 2.0, "attack_range": 300,
        "cost_metal": 50, "cost_wood": 20,
        "build_time": 120
    },
    {
        "code": "turret_heavy",
        "name": "Тяжёлая турель",
        "category": "defense",
        "width": 2, "height": 2,
        "max_hp": 300,
        "damage": 25, "fire_rate": 1.0, "attack_range": 400,
        "cost_metal": 150, "cost_wood": 50,
        "build_time": 300
    },

    {
        "code": "gate_wood",
        "name": "Деревянные ворота",
        "category": "defense",
        "width": 1, "height": 1,
        "max_hp": 80,
        "cost_wood": 30,
        "build_time": 45
    },
    {
        "code": "gate_metal",
        "name": "Металлические ворота",
        "category": "defense",
        "width": 1, "height": 1,
        "max_hp": 250,
        "cost_metal": 40, "cost_wood": 15,
        "build_time": 90
    },

    # Производство
    {
        "code": "mine",
        "name": "Шахта",
        "category": "production",
        "width": 2, "height": 2,
        "max_hp": 200,
        "produces_resource": "metal", "production_rate": 10,  # per hour
        "cost_metal": 30, "cost_wood": 50,
        "build_time": 180
    },
    {
        "code": "sawmill",
        "name": "Лесопилка",
        "category": "production",
        "width": 2, "height": 2,
        "max_hp": 150,
        "produces_resource": "wood", "production_rate": 15,
        "cost_metal": 20, "cost_wood": 30,
        "build_time": 120
    },
    {
        "code": "farm",
        "name": "Ферма",
        "category": "production",
        "width": 3, "height": 2,
        "max_hp": 100,
        "produces_resource": "food", "production_rate": 8,
        "cost_wood": 40,
        "build_time": 150
    },
    {
        "code": "ammo_factory",
        "name": "Оружейная",
        "category": "production",
        "width": 2, "height": 2,
        "max_hp": 200,
        "produces_resource": "ammo", "production_rate": 5,
        "cost_metal": 80, "cost_wood": 30,
        "build_time": 240
    },
    {
        "code": "med_station",
        "name": "Медпункт",
        "category": "production",
        "width": 2, "height": 2,
        "max_hp": 150,
        "produces_resource": "meds", "production_rate": 2,
        "cost_metal": 40, "cost_food": 20,
        "build_time": 200
    },

    # Утилиты
    {
        "code": "bunker",
        "name": "Бункер",
        "category": "utility",
        "width": 3, "height": 3,
        "max_hp": 500,
        "cost_metal": 200, "cost_wood": 100,
        "build_time": 600
    },
    {
        "code": "barracks",
        "name": "Казарма",
        "category": "utility",
        "width": 2, "height": 2,
        "max_hp": 200,
        "cost_metal": 60, "cost_wood": 40, "cost_food": 30,
        "build_time": 300
    },
    {
        "code": "arena",
        "name": "Арена",
        "category": "utility",
        "width": 4, "height": 4,
        "max_hp": 300,
        "cost_metal": 100, "cost_wood": 100,
        "build_time": 400
    },
]


async def seed_building_types(db):
    """Заполнить таблицу типов зданий"""
    from ...models import BuildingType

    for bt_data in BUILDING_TYPES:
        existing = await db.execute(
            select(BuildingType).where(BuildingType.code == bt_data["code"])
        )
        if existing.scalar_one_or_none() is None:
            bt = BuildingType(**bt_data)
            db.add(bt)

    await db.commit()
