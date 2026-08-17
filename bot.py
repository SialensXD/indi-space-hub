print("=== СТАРТ БОТА ===", flush=True)
import os
import sys
import logging
import asyncio
import asyncpg
from datetime import datetime, timezone, timedelta

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

import random

# СЛОВАРИ ДЛЯ БОЕВКИ
active_duels = {}
duel_invites = {}

# БАЗОВЫЕ СТАТЫ ПЕРСОНАЖЕЙ (памятка: ключи - названия ролей из базы в нижнем регистре)
CHARACTERS = {
    "v1": {"hp": 100, "max_hp": 100, "atk": 15, "type": "vampire"},
    "v2": {"hp": 130, "max_hp": 130, "atk": 15, "type": "enrage"},
    "санс": {"hp": 50, "max_hp": 50, "atk": 0, "type": "karma"},
    "нико": {"hp": 95, "max_hp": 95, "atk": 12, "type": "light"},
    "минос прайм": {"hp": 150, "max_hp": 150, "atk": 20, "type": "berserk"},
    "полый рыцарь": {"hp": 100, "max_hp": 100, "atk": 15, "type": "souls"}
}

# --- БАЗА ДАННЫХ (POSTGRESQL) ---
async def init_db():
    global db_pool
    if not DATABASE_URL:
        logging.error("❌ DATABASE_URL не найден!")
        return
    
    dsn = DATABASE_URL.replace("postgres://", "postgresql://")
    try:
        # Добавили statement_cache_size=0 для работы с PgBouncer на Render
        db_pool = await asyncpg.create_pool(
            dsn=dsn,
            statement_cache_size=0
        )
        async with db_pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM users a USING users b 
                WHERE a.ctid < b.ctid AND a.user_id = b.user_id;
                
                CREATE UNIQUE INDEX IF NOT EXISTS users_user_id_unique ON users (user_id);
            """)
        logging.info("✅ Подключение к БД успешно!")
    except Exception as e:
        logging.error(f"❌ Ошибка БД: {e}")

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
                """
                INSERT INTO users (user_id, username, role_id, role_changes, credits, xp) 
                VALUES ($1, $2, $3, 0, 100, 0)
                ON CONFLICT (user_id) DO UPDATE 
                SET role_id = EXCLUDED.role_id, username = EXCLUDED.username
                """,
                user_id, username, role_id
            )
        elif user['role_id'] is None:
            await conn.execute(
                "UPDATE users SET role_id = $1, username = $2 WHERE user_id = $3",
                role_id, username, user_id
            )
        else:
            await conn.execute(
                "UPDATE users SET role_id = $1, role_changes = COALESCE(role_changes, 0) + 1, username = $2 WHERE user_id = $3",
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

# --- ДВИЖОК БОЕВКИ ---
def render_duel_text(duel_id: str):
    duel = active_duels[duel_id]
    p1, p2 = duel['p1'], duel['p2']
    
    # Генератор HP бара (10 квадратиков)
    def make_hp_bar(hp, max_hp):
        percent = max(0, hp / max_hp)
        filled = int(percent * 10)
        return "🟩" * filled + "⬜️" * (10 - filled)
        
    text = f"⚔️ СМЕРТЕЛЬНАЯ БИТВА ⚔️\n\n"
    text += f"🎮 {p1['name']} [{p1['role']}]\n"
    text += f"HP: {p1['hp']}/{p1['max_hp']} {make_hp_bar(p1['hp'], p1['max_hp'])}\n\n"
    
    text += f"🎮 {p2['name']} [{p2['role']}]\n"
    text += f"HP: {p2['hp']}/{p2['max_hp']} {make_hp_bar(p2['hp'], p2['max_hp'])}\n\n"
    
    text += f"📜 Лог: {duel['log']}\n\n"
    
    turn_name = p1['name'] if duel['turn'] == p1['id'] else p2['name']
    text += f"👉 Ход: {turn_name}"
    return text

def get_duel_keyboard(duel_id: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="⚔️ Атака", callback_data=f"fight_atk_{duel_id}")
    builder.button(text="🛡 Блок", callback_data=f"fight_def_{duel_id}")
    builder.button(text="✨ Навык", callback_data=f"fight_skill_{duel_id}")
    builder.button(text="🎒 Предмет", callback_data=f"fight_item_{duel_id}")
    builder.adjust(2, 2)
    return builder.as_markup()

@dp.message(Command("role"))
async def cmd_role(message: types.Message):
    kb = await get_roles_keyboard(message.from_user.id)
    await message.answer("Выбирай себе персонажа:", reply_markup=kb)
@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_data = await get_user(message.from_user.id)
    if user_data:
        role_str = user_data['role_name'] or "Без роли"
        credits_val = user_data['credits'] if user_data['credits'] is not None else 100
        xp_val = user_data['xp'] if user_data['xp'] is not None else 0
        left_changes = max(0, 1 - (user_data['role_changes'] or 0))
        
        status = (
            f"🎭 Персонаж: {role_str}\n"
            f"💳 Кредиты: {credits_val} 💰\n"
            f"⭐️ Опыт: {xp_val} XP\n"
            f"🔄 Смен роли осталось: {left_changes}/1"
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
            await conn.execute("INSERT INTO users (user_id, username, credits, xp, role_changes) VALUES ($1, $2, 100, 0, 0) ON CONFLICT DO NOTHING", user_id, username)
        user_data = await get_user(user_id)

    now = datetime.now(timezone.utc)
    last_daily = user_data['last_daily']

    if last_daily and (now - last_daily) < timedelta(hours=24):
        remaining = timedelta(hours=24) - (now - last_daily)
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        await message.answer(f"⏳ Заходи через {hours} ч. {minutes} мин.")
        return

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET credits = COALESCE(credits, 0) + 250, xp = COALESCE(xp, 0) + 50, last_daily = $1 WHERE user_id = $2",
            now, user_id
        )
    await message.answer("🎁 Бонус получен!\n\n+250 💰\n+50 XP ⭐️")

# Словарь для активных боев в памяти: { duel_id: { "p1": id, "p2": id, "turn": id, ... } }
active_duels = {}
duel_invites = {} # Для хранения непринятых вызовов

@dp.message(Command("duel"))
async def cmd_duel(message: types.Message):
    try:
        user_id = message.from_user.id
        
        # Проверяем, есть ли у инициатора персонаж
        user_data = await get_user(user_id)
        if not user_data or not user_data['role_id']:
            await message.answer("❌ Сначала выбери персонажа через /role!")
            return

        # Проверяем, ответил ли игрок реплаем на сообщение соперника
        if not message.reply_to_message or message.reply_to_message.from_user.is_bot:
            await message.answer("⚠️ Чтобы вызвать на дуэль, ответь командой /duel на сообщение противника в чате!")
            return

        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.first_name

        if target_id == user_id:
            await message.answer("Ты не можешь вызвать сам себя на дуэль, шизофреник!")
            return

        # Проверяем персонажа противника
        target_data = await get_user(target_id)
        if not target_data or not target_data['role_id']:
            await message.answer(f"❌ У {target_name} не выбран персонаж! Пусть сначала выберет через /role.")
            return

        # Создаем инлайн-кнопки принятия вызова
        builder = InlineKeyboardBuilder()
        builder.button(text="⚔️ Принять вызов", callback_data=f"duel_accept_{user_id}_{target_id}")
        builder.button(text="❌ Отказаться", callback_data=f"duel_decline_{target_id}")
        builder.button(text="🛑 Отозвать", callback_data=f"duel_cancel_{user_id}")
        builder.adjust(2, 1)

        await message.answer(
            f"⚔️ <b>Вызов на дуэль!</b>\n\n"
            f"@{message.from_user.username or message.from_user.first_name} вызывает {target_name} на мортал комбат!\n"
            f"Примешь вызов?",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except Exception as e:
        # Если код снова упадет, бот не промолчит, а выведет причину краша прямо в чат
        await message.answer(f"🔧 Ого, тута системная ошибка: {e}, зовите Сиаленса!")

# --- АДМИН КОМАНДЫ ---
@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]:
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("⚠️ Использование: /reset @username", parse_mode="Markdown")
        return
    target = args[1].replace("@", "")
    async with db_pool.acquire() as conn:
        res = await conn.execute("UPDATE users SET role_changes = 0 WHERE username = $1", target)
    await message.answer(f"✅ Лимит для @{target} сброшен!" if res == "UPDATE 1" else "❌ Пользователь не найден.")

@dp.message(Command("send"))
async def cmd_broadcast(message: types.Message):
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]:
        return
    text = message.text.replace("/send", "").strip()
    if not text:
        await message.answer("⚠️ Использование: /send Текст", parse_mode="Markdown")
        return
    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users")
    
    ok, err = 0, 0
    for u in users:
        try:
            await bot.send_message(u['user_id'], text)
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            err += 1
    await message.answer(f"🚀 Рассылка завершена!\nУспешно: {ok}\nОшибок: {err}")

@dp.message(Command("clear_db"))
async def cmd_clear_db(message: types.Message):
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]:
        return
    async with db_pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE users;")
    await message.answer("🧹 База пользователей очищена!")
@dp.callback_query(F.data.startswith("role_"))
async def callbacks_num(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    role_id = int(callback.data.split("_")[1])
    is_admin = username.lower() in [a.lower() for a in ADMIN_USERNAMES]

    user_data = await get_user(user_id)

    if user_data and user_data['role_id'] == role_id:
        await callback.answer("Ты уже выбрал этого персонажа! 👺", show_alert=True)
        return

    if user_data and user_data['role_id'] is not None:
        if (user_data['role_changes'] or 0) >= 1 and not is_admin:
            await callback.answer("❌ Лимит смен исчерпан!", show_alert=True)
            return

    async with db_pool.acquire() as conn:
        if await conn.fetchval("SELECT user_id FROM users WHERE role_id = $1 AND user_id != $2", role_id, user_id):
            await callback.answer("🔒 Персонаж уже занят!", show_alert=True)
            kb = await get_roles_keyboard(user_id)
            await callback.message.edit_reply_markup(reply_markup=kb)
            return

    await save_user_role(user_id, username, role_id)
    updated = await get_user(user_id)
    await callback.message.edit_text(f"Забронирован персонаж: {updated['role_name']}", parse_mode="Markdown")
    await callback.answer("Готово!")

@dp.callback_query(F.data.startswith("duel_decline_"))
async def cb_duel_decline(callback: types.CallbackQuery):
    target_id = int(callback.data.split("_")[2])
    
    if callback.from_user.id != target_id:
        await callback.answer("Это вызывают не тебя!", show_alert=True)
        return
        
    await callback.message.edit_text("🏃‍♂️ Вызов на дуэль был трусливо отклонен, кто-то пропитушился.")

@dp.callback_query(F.data.startswith("duel_cancel_"))
async def cb_duel_cancel(callback: types.CallbackQuery):
    initiator_id = int(callback.data.split("_")[2])
    
    if callback.from_user.id != initiator_id:
        await callback.answer("Только тот, кто бросил вызов, может его отозвать!", show_alert=True)
        return
        
    await callback.message.edit_text("🛑 Вызов на дуэль был отозван.")

@dp.callback_query(F.data.startswith("duel_accept_"))
async def cb_duel_accept(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    p1_id, p2_id = int(parts[2]), int(parts[3])
    
    if callback.from_user.id != p2_id:
        await callback.answer("Это вызывают не тебя!", show_alert=True)
        return
    
    # Грузим статы из базы
    p1_data = await get_user(p1_id)
    p2_data = await get_user(p2_id)
    
    if not p1_data or not p2_data:
        await callback.message.edit_text("❌ Ошибка: кто-то из игроков пропал из базы.")
        return
        
    p1_role = p1_data['role_name'].lower() if p1_data['role_name'] else ""
    p2_role = p2_data['role_name'].lower() if p2_data['role_name'] else ""
    
    # Дефолтные статы, если имя роли не совпало со словарем CHARACTERS
    def_stats = {"hp": 100, "max_hp": 100, "atk": 15, "type": "basic"}
    c1 = CHARACTERS.get(p1_role, def_stats).copy()
    c2 = CHARACTERS.get(p2_role, def_stats).copy()
    
    duel_id = str(random.randint(10000, 99999))
    turn_id = random.choice([p1_id, p2_id]) # Жеребьевка хода
    
    active_duels[duel_id] = {
        "p1": {"id": p1_id, "name": p1_data['username'] or "Игрок 1", "role": p1_data['role_name'], "hp": c1['hp'], "max_hp": c1['max_hp'], "atk": c1['atk'], "type": c1['type'], "cd": 0, "block": False},
        "p2": {"id": p2_id, "name": p2_data['username'] or "Игрок 2", "role": p2_data['role_name'], "hp": c2['hp'], "max_hp": c2['max_hp'], "atk": c2['atk'], "type": c2['type'], "cd": 0, "block": False},
        "turn": turn_id,
        "log": f"🎲 Жеребьевка прошла! Первым ходит: {'Игрок 1' if turn_id == p1_id else 'Игрок 2'}"
    }
    
    # Рисуем поле боя
    kb = get_duel_keyboard(duel_id)
    text = render_duel_text(duel_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("fight_"))
async def cb_fight(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    action = parts[1] # atk, def, skill, item
    duel_id = parts[2]
    
    # 1. Проверки на дурака
    if duel_id not in active_duels:
        await callback.answer("Этот бой уже завершен или не существует.", show_alert=True)
        return
        
    duel = active_duels[duel_id]
    
    is_p1 = (user_id == duel['p1']['id'])
    is_p2 = (user_id == duel['p2']['id'])
    
    if not (is_p1 or is_p2):
        await callback.answer("Ты не участвуешь в этом бою, осел.", show_alert=True)
        return
        
    if duel['turn'] != user_id:
        await callback.answer("⏳ Сейчас не твой ход!", show_alert=True)
        return
        
    # 2. Определяем, кто бьет, а кто получает
    attacker = duel['p1'] if is_p1 else duel['p2']
    defender = duel['p2'] if is_p1 else duel['p1']
    
    log_msg = ""
    
    # Сбрасываем блок атакующего (если он ставил его в свой прошлый ход)
    attacker['block'] = False 
    
    # 3. Обработка действий
    if action == "atk":
        # Базовый урон + легкий рандом (-2..+3 урона) для живости
        dmg = attacker['atk'] + random.randint(-2, 3)
        
        # Пассивка Санса: 45% шанс увернуться
        if defender['type'] == 'karma' and random.random() < 0.45:
            dmg = 0
            log_msg = f"💨 {defender['name']} увернулся от атаки!"
        else:
            # Проверка блока (снижает урон на 40%)
            if defender['block']:
                dmg = int(dmg * 0.6)
                log_msg = f"🛡 {defender['name']} заблокировал часть урона!\n"
            
            defender['hp'] -= dmg
            log_msg += f"🗡 {attacker['name']} наносит {dmg} урона!"
            
            # Пассивка V1: Вампиризм (хил 20% от урона)
            if attacker['type'] == 'vampire' and dmg > 0:
                heal = int(dmg * 0.2)
                if heal < 1: heal = 1 # Минимум 1 хп хила
                attacker['hp'] = min(attacker['max_hp'], attacker['hp'] + heal)
                log_msg += f" 🩸 Восстановил {heal} HP!"
            
    elif action == "def":
        attacker['block'] = True
        log_msg = f"🛡 {attacker['name']} уходит в глухую оборону."
        
    elif action == "skill":
        log_msg = f"✨ {attacker['name']} пытается кастануть магию, но навыки еще в разработке!"
        
    elif action == "item":
        log_msg = f"🎒 {attacker['name']} лезет в рюкзак... а там пусто!"

    # 4. Обновляем лог боя
    duel['log'] = log_msg
    
    # 5. Проверка на СМЕРТЬ (конец боя)
    if defender['hp'] <= 0:
        defender['hp'] = 0
        text = render_duel_text(duel_id)
        text += f"\n\n🏆 ПОБЕДИТЕЛЬ: {attacker['name']}!\n💀 Бой окончен."
        
        # Награда победителю (начислим в базу)
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET credits = credits + 100, xp = xp + 50 WHERE user_id = $1",
                attacker['id']
            )
            
        del active_duels[duel_id] # Удаляем бой из памяти
        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer("Победа!")
        return
        
    # 6. Передача хода, если никто не умер
    duel['turn'] = defender['id']
    
    # Перерисовываем интерфейс
    text = render_duel_text(duel_id)
    kb = get_duel_keyboard(duel_id)
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

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