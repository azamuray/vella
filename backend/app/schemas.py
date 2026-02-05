from typing import Optional, List, Literal
from pydantic import BaseModel


# ============== Client -> Server ==============

class JoinRoom(BaseModel):
    type: Literal["join_room"] = "join_room"
    room_code: Optional[str] = None  # None = create new room


class PlayerInput(BaseModel):
    type: Literal["input"] = "input"
    seq: int  # Sequence number for reconciliation
    move_x: float  # -1 to 1
    move_y: float
    aim_x: float  # -1 to 1
    aim_y: float
    shooting: bool = False
    reload: bool = False


class ReadyToggle(BaseModel):
    type: Literal["ready"] = "ready"
    is_ready: bool


class SwitchWeapon(BaseModel):
    type: Literal["switch_weapon"] = "switch_weapon"
    weapon_code: str


class LeaveRoom(BaseModel):
    type: Literal["leave_room"] = "leave_room"


# ============== Server -> Client ==============

class PlayerStateData(BaseModel):
    id: int
    username: Optional[str]
    x: float
    y: float
    hp: int
    max_hp: int
    weapon: str
    ammo: int
    max_ammo: int
    reloading: bool
    reload_progress: float  # 0.0 to 1.0
    aim_angle: float
    is_dead: bool


class ZombieStateData(BaseModel):
    id: int
    type: str  # normal, fast, tank, boss
    x: float
    y: float
    hp: int
    max_hp: int


class ProjectileStateData(BaseModel):
    id: int
    x: float
    y: float
    angle: float
    owner_id: int


class LobbyPlayerData(BaseModel):
    id: int
    username: Optional[str]
    is_ready: bool
    weapon: str
    kills: int
    highest_wave: int


class RoomJoined(BaseModel):
    type: Literal["room_joined"] = "room_joined"
    room_code: str
    players: List[LobbyPlayerData]
    your_id: int


class LobbyUpdate(BaseModel):
    type: Literal["lobby_update"] = "lobby_update"
    players: List[LobbyPlayerData]


class GameStart(BaseModel):
    type: Literal["game_start"] = "game_start"
    players: List[PlayerStateData]


class GameState(BaseModel):
    type: Literal["state"] = "state"
    tick: int
    players: List[PlayerStateData]
    zombies: List[ZombieStateData]
    projectiles: List[ProjectileStateData]
    wave: int
    wave_countdown: Optional[float] = None  # seconds until next wave
    zombies_remaining: int


class WaveStart(BaseModel):
    type: Literal["wave_start"] = "wave_start"
    wave: int
    zombie_count: int
    special_zombies: List[str]


class WaveComplete(BaseModel):
    type: Literal["wave_complete"] = "wave_complete"
    wave: int
    bonus_coins: int


class PlayerDied(BaseModel):
    type: Literal["player_died"] = "player_died"
    player_id: int
    killed_by: str


class PlayerRespawn(BaseModel):
    type: Literal["player_respawn"] = "player_respawn"
    player_id: int
    x: float
    y: float


class ZombieKilled(BaseModel):
    type: Literal["zombie_killed"] = "zombie_killed"
    zombie_id: int
    killer_id: int
    coins: int
    zombie_type: str


class GameOver(BaseModel):
    type: Literal["game_over"] = "game_over"
    wave_reached: int
    total_kills: int
    player_stats: List[dict]
    coins_earned: int


class Error(BaseModel):
    type: Literal["error"] = "error"
    message: str
