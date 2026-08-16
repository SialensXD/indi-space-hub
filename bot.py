import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Ваш токен от BotFather
TOKEN = "8883956292:AAF0wZaZJVdw6JSQ3UaPk6E4TMOE86FUqCs"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Простая база данных ролей прямо в памяти (Имя юзера: Роль)
user_roles = {}

# Клавиатура выбора ролей
def get_roles_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🗡️ Рыцарь", callback_data="role_knight")
    builder.button(text="💡 Нико", callback_data="role_keeper")
    builder.button(text="💀 Санс", callback_data="role_shadow")
    builder.adjust(1) # Кнопки в один столбик
    return builder.as_markup()

# Команда /role в чате
@dp.message(Command("role"))
async def cmd_role(message: types.Message):
    await message.answer(
        f"Привет, {message.from_user.first_name}! Выбери свою роль во флуде Indie Space:",
        reply_markup=get_roles_keyboard()
    )

# Команда /profile (проверить текущую роль)
@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    role = user_roles.get(user_id, "Без роли (выбери через /role)")
    await message.answer(f"👤 Профиль {message.from_user.first_name}\n🎭 Роль: {role}", parse_mode="Markdown")

# Обработка нажатий на кнопки
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
    print("Бот Indie Space запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())