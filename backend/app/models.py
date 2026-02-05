from sqlalchemy import Column, BigInteger, Integer, String, Float, Boolean, DateTime, ForeignKey, Index, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


# =============================================================================
# RPG MODELS - Open World System
# =============================================================================

class Clan(Base):
    """Клан привязан к Telegram группе"""
    __tablename__ = "clans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_chat_id = Column(BigInteger, unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)

    # Base position on world map
    base_x = Column(Integer, default=0)
    base_y = Column(Integer, default=0)

    # Resources stored in base
    metal = Column(Integer, default=100)
    wood = Column(Integer, default=100)
    food = Column(Integer, default=50)
    ammo = Column(Integer, default=50)
    meds = Column(Integer, default=10)

    # Defense stats
    offline_shield_until = Column(DateTime, nullable=True)  # When shield expires

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    last_activity = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    members = relationship("ClanMember", back_populates="clan", cascade="all, delete-orphan")
    buildings = relationship("Building", back_populates="clan", cascade="all, delete-orphan")


class ClanMember(Base):
    """Членство игрока в клане"""
    __tablename__ = "clan_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    clan_id = Column(Integer, ForeignKey("clans.id", ondelete="CASCADE"))
    player_id = Column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"))

    role = Column(String(16), default="member")  # leader, officer, member
    joined_at = Column(DateTime, server_default=func.now())

    # Relationships
    clan = relationship("Clan", back_populates="members")
    player = relationship("Player", back_populates="clan_membership")

    __table_args__ = (
        Index('idx_clan_member', 'clan_id', 'player_id', unique=True),
    )


class BuildingType(Base):
    """Типы зданий (справочник)"""
    __tablename__ = "building_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(32), unique=True, nullable=False)  # wall, turret, bunker, mine, farm, etc.
    name = Column(String(64), nullable=False)
    category = Column(String(32), nullable=False)  # defense, production, utility

    # Size on grid
    width = Column(Integer, default=1)
    height = Column(Integer, default=1)

    # Stats
    max_hp = Column(Integer, default=100)

    # Production (for mines/farms)
    produces_resource = Column(String(16), nullable=True)  # metal, wood, food, ammo, meds
    production_rate = Column(Float, default=0)  # per hour

    # Combat (for turrets)
    damage = Column(Integer, default=0)
    fire_rate = Column(Float, default=0)
    attack_range = Column(Float, default=0)

    # Cost to build
    cost_metal = Column(Integer, default=0)
    cost_wood = Column(Integer, default=0)
    cost_food = Column(Integer, default=0)

    # Build time in seconds
    build_time = Column(Integer, default=60)


class Building(Base):
    """Конкретное здание на базе клана"""
    __tablename__ = "buildings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    clan_id = Column(Integer, ForeignKey("clans.id", ondelete="CASCADE"))
    building_type_id = Column(Integer, ForeignKey("building_types.id"))

    # Position on base grid
    grid_x = Column(Integer, nullable=False)
    grid_y = Column(Integer, nullable=False)

    # State
    hp = Column(Integer, default=100)
    level = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)

    # For production buildings
    last_collected = Column(DateTime, server_default=func.now())

    # Build progress
    build_started = Column(DateTime, nullable=True)
    build_complete = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    clan = relationship("Clan", back_populates="buildings")
    building_type = relationship("BuildingType")

    __table_args__ = (
        Index('idx_building_position', 'clan_id', 'grid_x', 'grid_y', unique=True),
    )


class PlayerInventory(Base):
    """Инвентарь игрока (ресурсы при себе)"""
    __tablename__ = "player_inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), unique=True)

    # Resources carried
    metal = Column(Integer, default=0)
    wood = Column(Integer, default=0)
    food = Column(Integer, default=0)
    ammo = Column(Integer, default=30)  # Start with some ammo
    meds = Column(Integer, default=1)   # Start with 1 medkit

    # Equipment slots
    equipped_weapon = Column(String(32), default="glock_17")
    equipped_armor = Column(String(32), nullable=True)

    # Relationships
    player = relationship("Player", back_populates="inventory")


class WorldState(Base):
    """Состояние игрока в открытом мире"""
    __tablename__ = "world_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"), unique=True)

    # Position in world
    x = Column(Float, default=0)
    y = Column(Float, default=0)

    # State
    hp = Column(Integer, default=100)
    max_hp = Column(Integer, default=100)
    is_alive = Column(Boolean, default=True)

    # Last known state
    last_direction = Column(Float, default=0)  # Angle in radians
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    player = relationship("Player", back_populates="world_state")


class MapChunk(Base):
    """Чанк карты (процедурно сгенерированный)"""
    __tablename__ = "map_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_x = Column(Integer, nullable=False)
    chunk_y = Column(Integer, nullable=False)

    # Terrain data (JSON with tile types)
    terrain = Column(JSON, nullable=False)

    # Resource nodes in this chunk
    resources = Column(JSON, nullable=True)

    # Zombie spawn points
    spawn_points = Column(JSON, nullable=True)

    # Generation seed (for reproducibility)
    seed = Column(Integer, nullable=False)

    generated_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index('idx_chunk_coords', 'chunk_x', 'chunk_y', unique=True),
    )


class WorldZombie(Base):
    """Зомби в открытом мире (persistent)"""
    __tablename__ = "world_zombies"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Position
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    chunk_x = Column(Integer, nullable=False, index=True)
    chunk_y = Column(Integer, nullable=False, index=True)

    # Type and stats
    zombie_type = Column(String(16), default="normal")  # normal, fast, tank, boss
    hp = Column(Integer, default=50)
    max_hp = Column(Integer, default=50)

    # State
    is_alive = Column(Boolean, default=True)
    target_player_id = Column(BigInteger, nullable=True)

    # Respawn
    spawn_point_id = Column(Integer, nullable=True)
    respawn_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index('idx_zombie_chunk', 'chunk_x', 'chunk_y'),
        Index('idx_zombie_alive', 'is_alive'),
    )


class ClanWar(Base):
    """История войн/рейдов между кланами"""
    __tablename__ = "clan_wars"

    id = Column(Integer, primary_key=True, autoincrement=True)
    attacker_clan_id = Column(Integer, ForeignKey("clans.id", ondelete="SET NULL"), nullable=True)
    defender_clan_id = Column(Integer, ForeignKey("clans.id", ondelete="SET NULL"), nullable=True)

    # Results
    status = Column(String(16), default="ongoing")  # ongoing, attacker_won, defender_won, draw

    # Loot stolen
    metal_stolen = Column(Integer, default=0)
    wood_stolen = Column(Integer, default=0)
    food_stolen = Column(Integer, default=0)
    ammo_stolen = Column(Integer, default=0)
    meds_stolen = Column(Integer, default=0)

    # Casualties
    attacker_kills = Column(Integer, default=0)
    defender_kills = Column(Integer, default=0)
    buildings_destroyed = Column(Integer, default=0)

    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)


class Player(Base):
    __tablename__ = "players"

    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String(64), nullable=True)

    # Currency & Stats
    coins = Column(Integer, default=0)
    total_kills = Column(Integer, default=0)
    highest_wave = Column(Integer, default=0)
    games_played = Column(Integer, default=0)

    # RPG Stats
    total_pvp_kills = Column(Integer, default=0)
    total_deaths = Column(Integer, default=0)
    raids_participated = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    last_online = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    weapons = relationship("PlayerWeapon", back_populates="owner", cascade="all, delete-orphan")
    clan_membership = relationship("ClanMember", back_populates="player", uselist=False)
    inventory = relationship("PlayerInventory", back_populates="player", uselist=False, cascade="all, delete-orphan")
    world_state = relationship("WorldState", back_populates="player", uselist=False, cascade="all, delete-orphan")


class Weapon(Base):
    __tablename__ = "weapons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(32), unique=True, nullable=False)
    name = Column(String(64), nullable=False)
    category = Column(String(32), nullable=False)  # pistol, shotgun, rifle, sniper

    # Combat stats
    damage = Column(Integer, default=10)
    fire_rate = Column(Float, default=1.0)  # shots per second
    reload_time = Column(Float, default=2.0)  # seconds
    magazine_size = Column(Integer, default=10)
    spread = Column(Float, default=0.1)  # radians
    projectile_speed = Column(Float, default=800.0)  # pixels per second
    pellets = Column(Integer, default=1)  # for shotguns
    penetration = Column(Integer, default=1)  # how many zombies can pierce

    # Economy
    price_dollars = Column(Integer, default=0)  # real-world reference
    price_coins = Column(Integer, default=0)  # in-game cost
    required_kills = Column(Integer, default=0)  # kills to unlock


class PlayerWeapon(Base):
    __tablename__ = "player_weapons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(BigInteger, ForeignKey("players.telegram_id", ondelete="CASCADE"))
    weapon_id = Column(Integer, ForeignKey("weapons.id"))

    kills_with = Column(Integer, default=0)
    equipped = Column(Boolean, default=False)

    purchased_at = Column(DateTime, server_default=func.now())

    # Relationships
    owner = relationship("Player", back_populates="weapons")
    weapon = relationship("Weapon")

    __table_args__ = (
        Index('idx_player_weapon', 'player_id', 'weapon_id', unique=True),
    )


class GameSession(Base):
    __tablename__ = "game_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_code = Column(String(8), unique=True, index=True)

    status = Column(String(16), default="lobby")  # lobby, playing, finished
    current_wave = Column(Integer, default=0)
    total_kills = Column(Integer, default=0)
    max_players = Column(Integer, default=10)

    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    participants = relationship("GameParticipant", back_populates="session", cascade="all, delete-orphan")


class GameParticipant(Base):
    __tablename__ = "game_participants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("game_sessions.id", ondelete="CASCADE"))
    player_id = Column(BigInteger, ForeignKey("players.telegram_id"))

    kills = Column(Integer, default=0)
    deaths = Column(Integer, default=0)
    coins_earned = Column(Integer, default=0)
    survived_waves = Column(Integer, default=0)

    # Relationships
    session = relationship("GameSession", back_populates="participants")
    player = relationship("Player")

    __table_args__ = (
        Index('idx_session_player', 'session_id', 'player_id', unique=True),
    )
