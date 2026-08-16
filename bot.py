import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

TOKEN = "8883956292:AAF0wZaZJVdw6JSQ3UaPk6E4TMOE86FUqCs"
WEBHOOK_PATH = "/webhook"

bot = Bot(token=TOKEN)
dp = Dispatcher()
user_roles = {}

def get_roles_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🗡️ Рыцарь", callback_data="role_knight")
    builder.button(text="💡 Нико", callback_data="role_keeper")
    builder.button(text="💀 Санс", callback_data="role_shadow")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(Command("role"))
async def cmd_role(message: types.Message):
    await message.answer(
        f"Привет, {message.from_user.first_name}! Выбери свою роль во флуде Indie Space:",
        reply_markup=get_roles_keyboard()
    )

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    role = user_roles.get(user_id, "Без роли (выбери через /role)")
    await message.answer(f"👤 Профиль {message.from_user.first_name}\n🎭 Роль: {role}", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("role_"))
async def callbacks_num(callback: types.CallbackQuery):
    role_name = ""
    if callback.data == "role_knight":
        role_name = "🗡️ Рыцарь"
    elif callback.data == "role_keeper":
        role_name = "💡 Нико"
    elif callback.data == "role_shadow":
        role_name = "💀 Санс"

    user_roles[callback.from_user.id] = role_name
    await callback.message.edit_text(f"Успешно! Твоя роль теперь: {role_name}", parse_mode="Markdown")
    await callback.answer("Роль сохранена!")

async def on_startup(bot: Bot):
    # Render автоматически подставит сюда твой домен (напр., https://твое-название.onrender.com)
    base_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not base_url:
        print("Внимание: RENDER_EXTERNAL_URL не найден. Бот запущен локально?", flush=True)
        return

    webhook_url = f"{base_url}{WEBHOOK_PATH}"
    print(f"Регистрируем вебхук в Telegram: {webhook_url}", flush=True)
    
    # Говорим Телеграму, куда слать апдейты
    await bot.set_webhook(webhook_url, drop_pending_updates=True)

def main():
    # Регистрируем функцию, которая сработает при старте сервера
    dp.startup.register(on_startup)

    # Создаем честный веб-сервер
    app = web.Application()
    
    # Привязываем наш aiogram-диспетчер к веб-серверу
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # Получаем порт от системы
    port = int(os.environ.get("PORT", 10000))
    print(f"Запуск честного веб-сервера на порту {port}...", flush=True)
    
    # Запускаем приложение (это блокирующий вызов, скрипт не завершится)
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "main":
    main()