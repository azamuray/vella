"""
Star reward scheduler — periodically awards stars to top wave players
and notifies admin to send them manually.
"""
import os
import asyncio
import traceback
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, desc

from ..database import async_session
from ..models import Player, StarRewardLog

# Award interval in seconds (1 hour)
REWARD_INTERVAL = 3600

# Budget: ~100 RUB/day = ~55 stars/day (182 RUB per 100 stars)
# Split 60/30/10 across 24 hours:
STAR_RATES = {
    1: 1.375,     # 1st place: ~33 stars/day → 100⭐ in ~3 days
    2: 0.6875,    # 2nd place: ~16.5 stars/day → 100⭐ in ~6 days
    3: 0.229,     # 3rd place: ~5.5 stars/day → 100⭐ in ~18 days
}

# Minimum stars to trigger a notification (= min Telegram gift)
MIN_SEND_AMOUNT = 100

ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID") or 0)


class StarScheduler:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._bot: Bot | None = None

    async def start(self, bot: Bot | None = None):
        self._bot = bot
        self._running = True
        self._task = asyncio.create_task(self._loop())
        print(f"[StarScheduler] Started (interval={REWARD_INTERVAL}s, admin={ADMIN_TELEGRAM_ID or 'not set'})")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("[StarScheduler] Stopped")

    async def _loop(self):
        # Wait a bit before first cycle
        await asyncio.sleep(10)

        while self._running:
            try:
                await self._award_stars()
                await self._notify_admin()
            except Exception as e:
                print(f"[StarScheduler] Error in loop: {e}")
                traceback.print_exc()

            await asyncio.sleep(REWARD_INTERVAL)

    async def _award_stars(self):
        """Award stars to top 3 wave leaderboard players"""
        async with async_session() as db:
            result = await db.execute(
                select(Player)
                .where(Player.highest_wave > 0)
                .order_by(desc(Player.highest_wave), desc(Player.total_kills))
                .limit(3)
            )
            top_players = result.scalars().all()

            if not top_players:
                return

            for position, player in enumerate(top_players, start=1):
                rate = STAR_RATES.get(position, 0)
                if rate <= 0:
                    continue

                player.star_balance = (player.star_balance or 0) + rate
                print(
                    f"[StarScheduler] #{position} {player.username} "
                    f"(wave {player.highest_wave}): +{rate:.3f} stars "
                    f"(balance: {player.star_balance:.3f})"
                )

            await db.commit()

    async def _notify_admin(self):
        """Notify admin about players with enough stars to send"""
        if not self._bot or not ADMIN_TELEGRAM_ID:
            return

        async with async_session() as db:
            result = await db.execute(
                select(Player)
                .where(Player.star_balance >= MIN_SEND_AMOUNT)
                .order_by(desc(Player.star_balance))
            )
            players = result.scalars().all()

            if not players:
                return

            # Create pending logs and build message
            lines = []
            buttons = []

            for player in players:
                amount = int(player.star_balance)

                log = StarRewardLog(
                    player_id=player.telegram_id,
                    amount=amount,
                    status="pending",
                )
                db.add(log)
                await db.flush()  # get log.id

                name = f"@{player.username}" if player.username else f"id:{player.telegram_id}"
                link = f'<a href="tg://user?id={player.telegram_id}">{name}</a>'

                lines.append(
                    f"  {link} — <b>{amount}</b> ⭐ "
                    f"(волна {player.highest_wave}, {player.total_kills} kills)"
                )
                buttons.append([
                    InlineKeyboardButton(
                        text=f"✅ {name} — {amount}⭐",
                        callback_data=f"stars_confirm:{log.id}:{player.telegram_id}:{amount}",
                    )
                ])

            await db.commit()

        # Send notification to admin
        text = (
            "⭐ <b>Пора отправить звёзды!</b>\n\n"
            + "\n".join(lines)
            + "\n\nОтправь звёзды через профиль игрока и нажми кнопку."
        )

        try:
            await self._bot.send_message(
                ADMIN_TELEGRAM_ID,
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            )
            print(f"[StarScheduler] Notified admin about {len(players)} pending payouts")
        except Exception as e:
            print(f"[StarScheduler] Failed to notify admin: {e}")


# Singleton
star_scheduler = StarScheduler()
