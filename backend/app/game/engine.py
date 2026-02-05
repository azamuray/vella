"""
Game engine - manages game loop for all rooms.
"""
import asyncio
from typing import Dict
from .room import Room, RoomManager


class GameEngine:
    """
    Central game engine that runs the game loop for all active rooms.
    """

    TICK_RATE = 20  # 20 ticks per second (50ms per tick)

    def __init__(self):
        self.room_manager = RoomManager()
        self.running = False
        self._task = None

    async def start(self):
        """Start the game engine"""
        if self.running:
            return

        self.running = True
        self._task = asyncio.create_task(self._game_loop())

    async def stop(self):
        """Stop the game engine"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _game_loop(self):
        """Main game loop - runs at fixed tick rate"""
        dt = 1.0 / self.TICK_RATE

        while self.running:
            loop_start = asyncio.get_event_loop().time()

            # Update all active rooms
            for room in list(self.room_manager.rooms.values()):
                if room.status in ("countdown", "playing"):
                    try:
                        events = room.update(dt)

                        # Broadcast events
                        for event in events:
                            await room.broadcast(event)

                        # Broadcast state every tick
                        await room.broadcast(room.get_state())

                    except Exception as e:
                        print(f"Error updating room {room.room_code}: {e}")

                # Clean up empty rooms
                if room.is_empty:
                    self.room_manager.remove_room(room.room_code)

            # Sleep to maintain tick rate
            elapsed = asyncio.get_event_loop().time() - loop_start
            sleep_time = dt - elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    def get_room(self, room_code: str) -> Room:
        """Get or create a room"""
        return self.room_manager.get_or_create_room(room_code)

    def create_room(self) -> Room:
        """Create a new room"""
        return self.room_manager.create_room()


# Global engine instance
engine = GameEngine()
