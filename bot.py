print("=== СТАРТ БОТА ===", flush=True)
import os
import sys
import logging
import asyncio
import asyncpg
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

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
        logging.error("❌ DATABASE_URL не найден в переменных окружения!")
        return
    
    # Корректируем формат DSN при необходимости
    dsn = DATABASE_URL.replace("postgres://", "postgresql://")
    try:
        db_pool = await asyncpg.create_pool(dsn=dsn)
        logging.info("✅ Успешное подключение к PostgreSQL (Supabase)!")
    except Exception as e:
        logging.error(f"❌ Ошибка подключения к БД: {e}")

async def get_roles():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT id, name FROM roles ORDER BY id ASC")

async def get_user(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT u.role_id, u.role_changes, r.name as role_name 
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
                "INSERT INTO users (user_id, username, role_id, role_changes) VALUES ($1, $2, $3, 0)",
                user_id, username, role_id
            )
        else:
            await conn.execute(
                "UPDATE users SET role_id = $1, role_changes = role_changes + 1, username = $2 WHERE user_id = $3",
                role_id, username, user_id
            )

# --- КЛАВИАТУРЫ И ХЕНДЛЕРЫ ---
async def get_roles_keyboard():
    roles = await get_roles()
    builder = InlineKeyboardBuilder()
    for role in roles:
        builder.button(text=role['name'], callback_data=f"role_{role['id']}")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(Command("role"))
async def cmd_role(message: types.Message):
    kb = await get_roles_keyboard()
    await message.answer(
        f"Привет, {message.from_user.first_name}! Выбери свою роль во вселенной Indie Space:",
        reply_markup=kb
    )

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_data = await get_user(message.from_user.id)
    if user_data and user_data['role_name']:
        status = f"🎭 Роль: {user_data['role_name']}\n🔄 Изменений роли: {user_data['role_changes']}/1"
    else:
        status = "🎭 Роль: Без роли (выбери через /role)"
        
    await message.answer(f"👤 Профиль {message.from_user.first_name}\n{status}", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("role_"))
async def callbacks_num(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    role_id = int(callback.data.split("_")[1])
    is_admin = username.lower() in [adm.lower() for adm in ADMIN_USERNAMES]

    user_data = await get_user(user_id)

    if user_data is not None:
        if user_data['role_changes'] >= 1 and not is_admin:
            await callback.answer(
                "❌ Лимит смены роли исчерпан! Обратитесь к админу @sialens_xd",
                show_alert=True
            )
            return
        await save_user_role(user_id, username, role_id)
    
    # Получаем название выбранной роли
    updated_user = await get_user(user_id)
    role_name = updated_user['role_name'] if updated_user else "Выбрана"
    
    admin_note = " 🛡️ *(Админ-доступ)*" if is_admin and user_data and user_data['role_changes'] >= 1 else ""
    await callback.message.edit_text(f"Успешно! Твоя роль: {role_name}{admin_note}", parse_mode="Markdown")
    await callback.answer("Роль сохранена!")

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
    dp.startup.register(on_startup)
    app = web.Application()

    app.router.add_get('/', health_check)
    
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    port = int(os.environ.get("PORT", 10000))
    logging.info(f"🚀 Запуск сервера на порту {port}...")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "main":
    try:
        main()
    except Exception as e:
        print(f"=== ОШИБКА ПРИ ЗАПУСКЕ ===\n{e}", flush=True)