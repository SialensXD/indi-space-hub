import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = "8883956292:AAF0wZaZJVdw6JSQ3UaPk6E4TMOE86FUqCs"

bot = Bot(token=TOKEN)
dp = Dispatcher()
user_roles = {}

# Мини-сервер для бесплатного тарифа Render
async def handle_health(request):
    return web.Response(text="Bot is running!")

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

async def main():
    # Запускаем фоновый веб-сервер для Render на порту 10000
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()

    print("Бот Indie Space запущен!")
    await dp.start_polling(bot)

if __name__ == "main":
    asyncio.run(main())