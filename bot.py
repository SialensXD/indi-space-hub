print("=== СТАРТ БОТА ===", flush=True)
import os
import sys
import time
import logging
import asyncio
import asyncpg
from typing import Callable, Dict, Any, Awaitable
from datetime import datetime, timezone, timedelta

from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import TelegramObject

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

TOKEN = "8883956292:AAF0wZaZJVdw6JSQ3UaPk6E4TMOE86FUqCs"
WEBHOOK_PATH = "/webhook"
ADMIN_USERNAMES = ["sialens_xd"]
DATABASE_URL = os.environ.get("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
db_pool = None

# --- АНТИ-СПАМ ФИЛЬТР ---
class AntiSpamMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 1.0):
        self.limit = limit
        self.users = {}

    async def call(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            now = time.time()
            last = self.users.get(user.id, 0)
            if now - last < self.limit:
                if isinstance(event, types.CallbackQuery):
                    await event.answer("Гой, притормози! Не тапай так часто 🖐", show_alert=True)
                return
            self.users[user.id] = now
        return await handler(event, data)

# --- БАЗА ДАННЫХ (POSTGRESQL) ---
async def init_db():
    global db_pool
    if not DATABASE_URL:
        logging.error("❌ DATABASE_URL не найден в переменных окружения!")
        return
    
    dsn = DATABASE_URL.replace("postgres://", "postgresql://")
    try:
        db_pool = await asyncpg.create_pool(dsn=dsn)
        logging.info("✅ Успешное подключение к БД!")
    except Exception as e:
        logging.error(f"❌ Ошибка подключения к БД: {e}")

async def get_roles():
    async with db_pool.acquire() as conn:
        # Достаем роли и смотри, кто их занял
        return await conn.fetch(
            """
            SELECT r.id, r.name, 
                   (SELECT user_id FROM users WHERE role_id = r.id LIMIT 1) as occupied_by
            FROM roles r
            ORDER BY r.id ASC
            """
        )

async def get_user(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT u.role_id, u.role_changes, u.credits, u.xp, u.last_daily, r.name as role_name 
            FROM users u 
            LEFT JOIN roles r ON u.role_id = r.id 
            WHERE u.user_id = $1
            """,
            user_id
        )

async def save_user_role(user_id: int, username: str, role_id: int):
    async with db_pool.acquire() as conn:
        user = await get_user(user_id)
        if user is None:
            await conn.execute(
                "INSERT INTO users (user_id, username, role_id, role_changes, credits, xp) VALUES ($1, $2, $3, 0, 100, 0)",
                user_id, username, role_id
            )
        else:
            await conn.execute(
                "UPDATE users SET role_id = $1, role_changes = role_changes + 1, username = $2 WHERE user_id = $3",
                role_id, username, user_id
            )

# --- КЛАВИАТУРЫ И ХЕНДЛЕРЫ ---
async def get_roles_keyboard(current_user_id: int):
    roles = await get_roles()
    builder = InlineKeyboardBuilder()
    for role in roles:
        if role['occupied_by'] and role['occupied_by'] != current_user_id:
            btn_text = f"🔒 {role['name']} (Занято)"
        elif role['occupied_by'] == current_user_id:
            btn_text = f"✅ {role['name']} (Твой перс)"
        else:
            btn_text = f"✨ {role['name']}"
            
        builder.button(text=btn_text, callback_data=f"role_{role['id']}")
    builder.adjust(1)
    return builder.as_markup()
@dp.message(Command("role"))
async def cmd_role(message: types.Message):
    kb = await get_roles_keyboard(message.from_user.id)
    await message.answer(
        f"Здорово, {message.from_user.first_name}! Выбирай себе персонажа (занятые помечены 🔒):",
        reply_markup=kb
    )

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_data = await get_user(message.from_user.id)
    if user_data:
        role_str = user_data['role_name'] if user_data['role_name'] else "Без роли (выбери через /role)"
        credits_val = user_data['credits'] if user_data['credits'] is not None else 100
        xp_val = user_data['xp'] if user_data['xp'] is not None else 0
        status = (
            f"🎭 Персонаж: {role_str}\n"
            f"💳 Бабосики: {credits_val} 💰\n"
            f"⭐ Опыт: {xp_val} XP\n"
            f"🔄 Смен роли оставлено: {1 - user_data['role_changes']}/1"
        )
    else:
        status = "🎭 Персонаж: Не выбран (выбери через /role)"
        
    await message.answer(f"👤 Профиль {message.from_user.first_name}\n\n{status}", parse_mode="Markdown")

@dp.message(Command("daily"))
async def cmd_daily(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    user_data = await get_user(user_id)

    if not user_data:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, username, credits, xp, role_changes) VALUES ($1, $2, 100, 0, 0)",
                user_id, username
            )
        user_data = await get_user(user_id)

    now = datetime.now(timezone.utc)
    last_daily = user_data['last_daily']

    if last_daily and (now - last_daily) < timedelta(hours=24):
        remaining = timedelta(hours=24) - (now - last_daily)
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        await message.answer(f"⏳ Рано еще! Заходи через {hours} ч. {minutes} мин.")
        return

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users 
            SET credits = COALESCE(credits, 0) + 250, 
                xp = COALESCE(xp, 0) + 50, 
                last_daily = $1 
            WHERE user_id = $2
            """,
            now, user_id
        )

    await message.answer("🎁 Вот и твой ежедневный бонус!\n\n+250 Кредитов 💰\n+50 XP ⭐", parse_mode="Markdown")

@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    username = message.from_user.username or ""
    if username.lower() not in [adm.lower() for adm in ADMIN_USERNAMES]:
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("⚠️ Пиши так: /reset @username", parse_mode="Markdown")
        return
        
    target_username = args[1].replace("@", "")
    
    async with db_pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET role_changes = 0 WHERE username = $1", 
            target_username
        )
        
    if result == "UPDATE 1":
        await message.answer(f"✅ Обнулил лимит для @{target_username}!")
    else:
        await message.answer(f"❌ Нет такого чела в базе.")

@dp.message(Command("send"))
async def cmd_broadcast(message: types.Message):
    username = message.from_user.username or ""
    if username.lower() not in [adm.lower() for adm in ADMIN_USERNAMES]:
        return

    text_to_send = message.text.replace("/send", "").strip()
    if not text_to_send:
        await message.answer("⚠️ Пиши так: /send Твой текст", parse_mode="Markdown")
        return

    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users")
    
    if not users:
        await message.answer("База пустая, некому слать.")
        return
    await message.answer(f"🚀 Запускаю рассылку на {len(users)} юзеров...")
    
    success_count = 0
    fail_count = 0
    
    for user in users:
        try:
            await bot.send_message(user['user_id'], text_to_send)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.error(f"Ошибка отправки {user['user_id']}: {e}")
            fail_count += 1
            
    await message.answer(
        f"✅ Готово!\nДошло: {success_count}\nОтвалилось: {fail_count}"
    )

@dp.callback_query(F.data.startswith("role_"))
async def callbacks_num(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    role_id = int(callback.data.split("_")[1])
    is_admin = username.lower() in [adm.lower() for adm in ADMIN_USERNAMES]

    user_data = await get_user(user_id)

    # 1. Проверка лимита смен (для не-админов)
    if user_data is not None:
        if user_data['role_changes'] >= 1 and not is_admin:
            await callback.answer(
                "❌ Всё, свой выбор ты уже сделал! Пиши админу @sialens_xd",
                show_alert=True
            )
            return

    # 2. Проверка: не занят ли перс другим челом?
    async with db_pool.acquire() as conn:
        occupied_by = await conn.fetchval(
            "SELECT user_id FROM users WHERE role_id = $1 AND user_id != $2",
            role_id, user_id
        )
        if occupied_by:
            await callback.answer("🔒 Увы и ах! Этого персонажа уже забрали!", show_alert=True)
            kb = await get_roles_keyboard(user_id)
            await callback.message.edit_reply_markup(reply_markup=kb)
            return

    # 3. Сохранение роли
    await save_user_role(user_id, username, role_id)
    
    updated_user = await get_user(user_id)
    role_name = updated_user['role_name'] if updated_user else "Выбрана"
    
    admin_note = " 🛡 *(Админка)*" if is_admin and user_data and user_data['role_changes'] >= 1 else ""
    await callback.message.edit_text(f"Ты забронировал персонажа: {role_name}{admin_note}", parse_mode="Markdown")
    await callback.answer("Персонаж за тобой!")

# --- СЕРВЕР И ФОНОВЫЕ ЗАДАЧИ ---
async def health_check(request):
    return web.Response(text="Bot is alive and running!", status=200)

async def set_webhook_background(bot: Bot, webhook_url: str):
    try:
        logging.info(f"Установка вебхука: {webhook_url}")
        await bot.set_webhook(webhook_url, drop_pending_updates=True)
        logging.info("✅ Вебхук установлен!")
    except Exception as e:
        logging.error(f"❌ Ошибка вебхука: {e}")

async def on_startup(bot: Bot):
    await init_db()
    base_url = os.environ.get("RENDER_EXTERNAL_URL")
    if base_url:
        webhook_url = f"{base_url}{WEBHOOK_PATH}"
        asyncio.create_task(set_webhook_background(bot, webhook_url))

def main():
    dp.message.middleware(AntiSpamMiddleware(limit=1.0))
    dp.callback_query.middleware(AntiSpamMiddleware(limit=1.0))

    dp.startup.register(on_startup)
    app = web.Application()

    app.router.add_get('/', health_check)
    
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    port = int(os.environ.get("PORT", 10000))
    logging.info(f"🚀 Запуск сервера на порту {port}...")
    web.run_app(app, host="0.0.0.0", port=port)

print("--- ЗАПУСК MAIN ---", flush=True)
main()