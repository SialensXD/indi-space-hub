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
from aiogram.types import TelegramObject

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

TOKEN = "8883956292:AAF0wZaZJVdw6JSQ3UaPk6E4TMOE86FUqCs"
WEBHOOK_PATH = "/webhook"
ADMIN_USERNAMES = ["sialens_xd"]
DATABASE_URL = os.environ.get("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
db_pool = None

# --- БАЗА ДАННЫХ (POSTGRESQL) ---
async def init_db():
    global db_pool
    if not DATABASE_URL:
        logging.error("❌ DATABASE_URL не найден!")
        return
    
    dsn = DATABASE_URL.replace("postgres://", "postgresql://")
    try:
        db_pool = await asyncpg.create_pool(dsn=dsn)
        logging.info("✅ Успешное подключение к БД!")
    except Exception as e:
        logging.error(f"❌ Ошибка подключения: {e}")

async def get_roles():
    async with db_pool.acquire() as conn:
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
        f"Здорово, {message.from_user.first_name}! Выбирай себе персонажа:",
        reply_markup=kb
    )

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_data = await get_user(message.from_user.id)
    if user_data:
        role_str = user_data['role_name'] if user_data['role_name'] else "Без роли"
        credits_val = user_data['credits'] or 100
        xp_val = user_data['xp'] or 0
        status = (
            f"🎭 Персонаж: {role_str}\n"
            f"💳 Кредиты: {credits_val} 💰\n"
            f"⭐️ Опыт: {xp_val} XP\n"
            f"🔄 Смен роли: {1 - user_data['role_changes']}/1"
        )
    else:
        status = "🎭 Персонаж: Не выбран"
    await message.answer(f"👤 Профиль {message.from_user.first_name}\n\n{status}", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("role_"))
async def callbacks_num(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    role_id = int(callback.data.split("_")[1])
    is_admin = username.lower() in [adm.lower() for adm in ADMIN_USERNAMES]

    user_data = await get_user(user_id)
    if user_data and user_data['role_changes'] >= 1 and not is_admin:
        await callback.answer("❌ Выбор уже сделан!", show_alert=True)
        return

    async with db_pool.acquire() as conn:
        occupied_by = await conn.fetchval(
            "SELECT user_id FROM users WHERE role_id = $1 AND user_id != $2",
            role_id, user_id
        )
        if occupied_by:
            await callback.answer("🔒 Персонаж уже занят!", show_alert=True)
            kb = await get_roles_keyboard(user_id)
            await callback.message.edit_reply_markup(reply_markup=kb)
            return

    await save_user_role(user_id, username, role_id)
    updated_user = await get_user(user_id)
    await callback.message.edit_text(f"Ты забронировал персонажа: {updated_user['role_name']}", parse_mode="Markdown")
    await callback.answer("Персонаж за тобой!")

# --- СЕРВЕР ---
async def health_check(request):
    return web.Response(text="Bot is alive!", status=200)

async def on_startup(bot: Bot):
    await init_db()
    base_url = os.environ.get("RENDER_EXTERNAL_URL")
    if base_url:
        await bot.set_webhook(f"{base_url}{WEBHOOK_PATH}", drop_pending_updates=True)

def main():
    dp.startup.register(on_startup)
    app = web.Application()
    app.router.add_get('/', health_check)
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

main()