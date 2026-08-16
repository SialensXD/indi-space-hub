import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = "8883956292:AAF0wZaZJVdw6JSQ3UaPk6E4TMOE86FUqCs"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Временное хранилище ролей в памяти
user_roles = {}

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
    elif callback.data == "role_niko":
        role_name = "💡 Нико"
    elif callback.data == "role_sans":
        role_name = "💀 Санс"

    user_roles[callback.from_user.id] = role_name
    await callback.message.edit_text(f"Успешно! Твоя роль теперь: {role_name}", parse_mode="Markdown")
    await callback.answer("Роль сохранена!")

async def main():
    logging.basicConfig(level=logging.INFO)
    # Сбрасываем старые накопившиеся апдейты и запускаем поллинг
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "main":
    asyncio.run(main())