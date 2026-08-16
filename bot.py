import os
import sqlite3
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

TOKEN = "8883956292:AAF0wZaZJVdw6JSQ3UaPk6E4TMOE86FUqCs"
WEBHOOK_PATH = "/webhook"
ADMIN_USERNAMES = ["sialens_xd"]

bot = Bot(token=TOKEN)
dp = Dispatcher()
DB_NAME = "bot_data.db"

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            role TEXT,
            role_changes INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
    print("База данных успешно инициализирована", flush=True)

def get_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT role, role_changes FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def save_user_role(user_id: int, username: str, new_role: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    user = get_user(user_id)
    
    if user is None:
        cursor.execute(
            "INSERT INTO users (user_id, username, role, role_changes) VALUES (?, ?, ?, 0)",
            (user_id, username, new_role)
        )
    else:
        cursor.execute(
            "UPDATE users SET role = ?, role_changes = role_changes + 1, username = ? WHERE user_id = ?",
            (new_role, username, user_id)
        )
    conn.commit()
    conn.close()

# --- КЛАВИАТУРЫ И ХЕНДЛЕРЫ ---
def get_roles_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🗡️ Рыцарь", callback_data="role_knight")
    builder.button(text="💡 Нико", callback_data="role_niko")
    builder.button(text="💀 Санс", callback_data="role_sans")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(Command("role"))
async def cmd_role(message: types.Message):
    await message.answer(
        f"Привет, {message.from_user.first_name}! Выбери свою роль во вселенной Indie Space:",
        reply_markup=get_roles_keyboard()
    )

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_data = get_user(message.from_user.id)
    if user_data:
        role, changes = user_data
        status = f"🎭 Роль: {role}\n🔄 Изменений роли: {changes}/1"
    else:
        status = "🎭 Роль: Без роли (выбери через /role)"
        
    await message.answer(f"👤 Профиль {message.from_user.first_name}\n{status}", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("role_"))
async def callbacks_num(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    is_admin = username.lower() in [adm.lower() for adm in ADMIN_USERNAMES]
    
    roles_map = {
        "role_knight": "🗡️ Рыцарь",
        "role_niko": "💡 Нико",
        "role_sans": "💀 Санс"
    }
    role_name = roles_map.get(callback.data, "Неизвестно")
    user_data = get_user(user_id)

    if user_data is not None:
        _, role_changes = user_data
        if role_changes >= 1 and not is_admin:
            await callback.answer(
                "❌ Вы уже исчерпали лимит смены роли! Обратитесь к админу @sialens_xd",
                show_alert=True
            )
            return

    save_user_role(user_id, username, role_name)
    admin_note = " 🛡️ *(Админ-доступ)*" if is_admin and user_data and user_data[1] >= 1 else ""
    await callback.message.edit_text(f"Успешно! Твоя роль теперь: {role_name}{admin_note}", parse_mode="Markdown")
    await callback.answer("Роль сохранена!")

# --- РУЧКА ПРОВЕРКИ ЗДОРОВЬЯ СЕРВЕРА (HEALTH CHECK) ---
async def health_check(request):
    return web.Response(text="Bot status: OK", status=200)
async def on_startup(bot: Bot):
    init_db()
    base_url = os.environ.get("RENDER_EXTERNAL_URL")
    if base_url:
        webhook_url = f"{base_url}{WEBHOOK_PATH}"
        print(f"Ставим вебхук на: {webhook_url}", flush=True)
        await bot.set_webhook(webhook_url, drop_pending_updates=True)

def main():
    dp.startup.register(on_startup)
    app = web.Application()

    # Главная страница для Render и UptimeRobot
    app.router.add_get('/', health_check)

    # Вебхук для Telegram
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    port = int(os.environ.get("PORT", 10000))
    print(f"Сервер запускается на порту {port}...", flush=True)
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "main":
    main()