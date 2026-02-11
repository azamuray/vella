"""
Telethon client for sending Telegram Stars gifts
Uses MTProto API via user account (not bot)
"""
import os
from telethon import TelegramClient

API_ID = os.getenv("TELETHON_API_ID", "")
API_HASH = os.getenv("TELETHON_API_HASH", "")
SESSION_PATH = os.getenv("TELETHON_SESSION_PATH", "/app/data/telethon_session")

_client: TelegramClient | None = None


async def get_telethon_client() -> TelegramClient | None:
    """Connect to existing Telethon session. Returns None if not configured."""
    global _client

    if not API_ID or not API_HASH:
        print("[Telethon] TELETHON_API_ID or TELETHON_API_HASH not set, skipping")
        return None

    try:
        _client = TelegramClient(SESSION_PATH, int(API_ID), API_HASH)
        await _client.connect()

        if not await _client.is_user_authorized():
            print("[Telethon] Session not authorized. Run setup_telethon_session.py first")
            await _client.disconnect()
            _client = None
            return None

        me = await _client.get_me()
        print(f"[Telethon] Connected as {me.first_name} (id={me.id})")
        return _client

    except Exception as e:
        print(f"[Telethon] Failed to connect: {e}")
        _client = None
        return None


async def disconnect_telethon():
    """Disconnect Telethon client"""
    global _client
    if _client:
        await _client.disconnect()
        _client = None
        print("[Telethon] Disconnected")
