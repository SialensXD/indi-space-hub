"""Basic user-facing commands."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from aiogram import types
from aiogram.filters import Command


def register_user_handlers(
    dp,
    *,
    db_pool_getter: Callable,
    get_user: Callable,
    start_time: datetime,
    trigger_cache: dict,
    active_duels: dict,
    site_url: str,
):
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        user_id = message.from_user.id
        username = message.from_user.username or ""
        async with db_pool_getter().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (user_id, username, credits, xp, role_changes)
                VALUES ($1, $2, 100, 0, 0)
                ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
                """,
                user_id,
                username,
            )

        if message.chat.type == "private":
            text = (
                f"👋 <b>Здрасьте, {message.from_user.first_name}!</b>\n\n"
                "Я Картер, этакий бот-ассистент. Вот основные команды:\n\n"
                "🎭 <b>/role</b> — выбрать персонажа для боев\n"
                "🎁 <b>/daily</b> — забрать ежедневную награду\n"
                "🏪 <b>/shop</b> — заглянуть в магазин товаров и титулов, там обнова каждые 4 часа\n"
                "👤 <b>/profile</b> — посмотреть свою статистику\n"
                "📊 <b>/top</b> — глянуть лидеров чата по разным штукам\n\n"
                "🔗 <b>/link</b> — получить ссылку на сайт\n\n"
                "А в чате ответь командой <code>/duel</code> на сообщение соперника, чтобы вызвать его на бой"
            )
        else:
            text = (
                f"Приветствую, {message.from_user.first_name}."
                "Нужны команды? тогда бегом ко мне в ЛС и там пропиши <code>/start</code>."
            )
        await message.answer(text, parse_mode="HTML")

    @dp.message(Command("link"))
    async def cmd_link(message: types.Message):
        await message.answer(f"Вот ссылка на сайт: {site_url}")

    @dp.message(Command("status", "ping"))
    async def cmd_status(message: types.Message):
        uptime = datetime.now(timezone.utc) - start_time
        uptime -= timedelta(microseconds=uptime.microseconds)
        ping_ms = (datetime.now(timezone.utc) - message.date).total_seconds() * 1000
        text = (
            "🤖 <b>Статус Картера:</b>\n\n"
            "🟢 <b>Состояние:</b> Онлайн\n"
            f"⏱ <b>Аптайм:</b> {uptime}\n"
            f"🏓 <b>Задержка:</b> ~{int(ping_ms)} мс\n"
            f"🧠 <b>Триггеров в памяти:</b> {len(trigger_cache)} шт.\n"
            f"⚔️ <b>Активных дуэлей:</b> {len(active_duels)}"
        )
        await message.answer(text, parse_mode="HTML")

    @dp.message(Command("daily"))
    async def cmd_daily(message: types.Message):
        user_id = message.from_user.id
        username = message.from_user.username or ""
        user_data = await get_user(user_id)
        if not user_data:
            async with db_pool_getter().acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO users (user_id, username, credits, xp, role_changes)
                    VALUES ($1, $2, 100, 0, 0)
                    ON CONFLICT DO NOTHING
                    """,
                    user_id,
                    username,
                )
            user_data = await get_user(user_id)

        now = datetime.now(timezone.utc)
        last_daily = user_data["last_daily"]
        if last_daily and (now - last_daily) < timedelta(hours=24):
            remaining = timedelta(hours=24) - (now - last_daily)
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            await message.answer(f"⏳ Заходи через {hours} ч. {minutes} мин.")
            return

        async with db_pool_getter().acquire() as conn:
            await conn.execute(
                """
                UPDATE users
                SET credits = COALESCE(credits, 0) + 250,
                    xp = COALESCE(xp, 0) + 50,
                    last_daily = $1
                WHERE user_id = $2
                """,
                now,
                user_id,
            )
        await message.answer("🎁 Бонус получен!\n\n+250 💰\n+50 XP ⭐️")
