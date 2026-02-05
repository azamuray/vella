from sqlalchemy import Column, BigInteger, Integer, String, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class Player(Base):
    __tablename__ = "players"

    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String(64), nullable=True)

    # Currency & Stats
    coins = Column(Integer, default=0)
    total_kills = Column(Integer, default=0)
    highest_wave = Column(Integer, default=0)
    games_played = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    last_online = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    weapons = relationship("PlayerWeapon", back_populates="owner", cascade="all, delete-orphan")


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
