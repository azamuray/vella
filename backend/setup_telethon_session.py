"""
One-time script to create a Telethon session file.
Run this locally, then copy the .session file to the Docker container.

Usage:
    pip install telethon
    python setup_telethon_session.py
"""
import asyncio
from telethon import TelegramClient


async def main():
    print("=== Telethon Session Setup ===")
    print("Get API_ID and API_HASH from https://my.telegram.org/apps\n")

    api_id = input("API_ID: ").strip()
    api_hash = input("API_HASH: ").strip()

    if not api_id or not api_hash:
        print("Error: API_ID and API_HASH are required")
        return

    session_name = "telethon_session"
    client = TelegramClient(session_name, int(api_id), api_hash)

    await client.start()

    me = await client.get_me()
    print(f"\nAuthorized as: {me.first_name} {me.last_name or ''} (@{me.username})")
    print(f"Session saved to: {session_name}.session")
    print(f"\nCopy this file to Docker:")
    print(f"  docker compose cp {session_name}.session backend:/app/data/")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
