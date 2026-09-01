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
                f"👋 <b>Здрасьте, {message.from_user.first_name}!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Я Картер, этакий бот-ассистент.\n\n"
                f"<b>🎮 ОСНОВНЫЕ КОМАНДЫ</b>\n\n"
                f"🎭 <b>/role</b>\n"
                f"  └ Выбрать персонажа для боев\n\n"
                f"🎁 <b>/daily</b>\n"
                f"  └ Забрать ежедневную награду\n\n"
                f"💸 <b>/give</b>\n"
                f"  └ Отправить деньги другому юзеру\n\n"
                f"🏪 <b>/shop</b>\n"
                f"  └ Магазин товаров и титулов (обнова каждые 4 часа)\n\n"
                f"👤 <b>/profile</b>\n"
                f"  └ Посмотреть свою статистику\n\n"
                f"📊 <b>/top</b>\n"
                f"  └ Лидеры чата по разным штукам\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🔗 <b>/link</b> — ссылка на сайт\n\n"
                f"💡 <b>В ЧАТЕ:</b> ответь <code>/duel</code> на сообщение соперника"
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
            "🤖 <b>СТАТУС КАРТЕРА</b>\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "🟢 Состояние: <b>Онлайн</b>\n\n"
            f"⏱  Аптайм: <b>{uptime}</b>\n\n"
            f"🏓 Задержка: <b>~{int(ping_ms)} мс</b>\n\n"
            f"🧠 Триггеров в памяти: <b>{len(trigger_cache)}</b> шт.\n\n"
            f"⚔️  Активных дуэлей: <b>{len(active_duels)}</b>\n\n"
            "━━━━━━━━━━━━━━━━━"
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
            await message.answer(f"⏳ <b>Еще не время!</b>\n\nЗаходи через <b>{hours} ч. {minutes} мин.</b>", parse_mode="HTML")
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
        await message.answer("🎁 <b>БОНУС ПОЛУЧЕН!</b>\n━━━━━━━━━━━━━━\n\n💰 +250 кредитов\n⭐️ +50 опыта\n\n━━━━━━━━━━━━━━", parse_mode="HTML")

    @dp.message(Command("give"))
    async def cmd_give(message: types.Message):
        user_id = message.from_user.id
        args = message.text.split()
        
        # Проверка аргументов
        if len(args) < 3:
            await message.answer(
                "❌ <b>ОШИБКА!</b>\n"
                "━━━━━━━━━━━━━━\n\n"
                "Используй: <code>/give @username сумма</code>\n\n"
                "Пример: <code>/give bot_user 100</code>",
                parse_mode="HTML"
            )
            return
        
        target_username = args[1].lstrip("@").lower()
        try:
            amount = int(args[2])
        except ValueError:
            await message.answer(
                "❌ <b>ОШИБКА!</b>\n"
                "━━━━━━━━━━━━━━\n\n"
                "Сумма должна быть числом!",
                parse_mode="HTML"
            )
            return
        
        if amount <= 0:
            await message.answer(
                "❌ <b>ОШИБКА!</b>\n"
                "━━━━━━━━━━━━━━\n\n"
                "Сумма должна быть больше нуля!",
                parse_mode="HTML"
            )
            return
        
        # Получаем данные отправителя
        sender_data = await get_user(user_id)
        if not sender_data:
            await message.answer(
                "❌ <b>ОШИБКА!</b>\n"
                "━━━━━━━━━━━━━━\n\n"
                "Тебя нет в базе! Напиши /start в личку бота.",
                parse_mode="HTML"
            )
            return
        
        sender_balance = sender_data['credits'] or 0
        if sender_balance < amount:
            await message.answer(
                f"❌ <b>НЕДОСТАТОЧНО ДЕНЕГ!</b>\n"
                f"━━━━━━━━━━━━━━\n\n"
                f"У тебя есть: <b>{sender_balance} 💰</b>\n"
                f"Ты хочешь отправить: <b>{amount} 💰</b>",
                parse_mode="HTML"
            )
            return
        
        # Ищем целевого пользователя
        async with db_pool_getter().acquire() as conn:
            target = await conn.fetchrow(
                "SELECT user_id, username FROM users WHERE username = $1",
                target_username
            )
        
        if not target:
            await message.answer(
                f"❌ <b>ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН!</b>\n"
                f"━━━━━━━━━━━━━━\n\n"
                f"Юзер <b>@{target_username}</b> не в базе.",
                parse_mode="HTML"
            )
            return
        
        target_id = target['user_id']
        
        # Проверка на самопередачу
        if target_id == user_id:
            await message.answer(
                "😭 <b>Бро...</b>\n"
                "━━━━━━━━━━━━━━\n\n"
                "Ну ты долбоеб?",
                parse_mode="HTML"
            )
            return
        
        # Переводим деньги
        async with db_pool_getter().acquire() as conn:
            await conn.execute(
                "UPDATE users SET credits = COALESCE(credits, 0) - $1 WHERE user_id = $2",
                amount,
                user_id
            )
            await conn.execute(
                "UPDATE users SET credits = COALESCE(credits, 0) + $1 WHERE user_id = $2",
                amount,
                target_id
            )
        
        await message.answer(
            f"💸 <b>ПЕРЕВОД ВЫПОЛНЕН!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Отправлено: <b>{amount} кредитов</b>\n"
            f"👤 Получатель: <b>@{target['username']}</b>\n"
            f"💳 Твой баланс: <b>{sender_balance - amount}</b>",
            parse_mode="HTML"
        )
