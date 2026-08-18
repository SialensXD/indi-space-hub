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

# БАЗОВЫЕ СТАТЫ ПЕРСОНАЖЕЙ (привязаны к role_id из БД)
CHARACTERS = {
    1: {"hp": 100, "max_hp": 100, "atk": 15, "type": "souls"},   
    2: {"hp": 95, "max_hp": 95, "atk": 12, "type": "light"},     
    3: {"hp": 50, "max_hp": 50, "atk": 5, "type": "karma"},      
    4: {"hp": 100, "max_hp": 100, "atk": 15, "type": "vampire"}, 
    5: {"hp": 130, "max_hp": 130, "atk": 15, "type": "enrage"},  
    6: {"hp": 150, "max_hp": 150, "atk": 20, "type": "berserk"},
    # МОЯ АДМИНСКАЯ РОЛЬ
    999: {"hp": 9999, "max_hp": 9999, "atk": 9999, "type": "god"} 
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
            SELECT u.username, u.role_id, u.role_changes, u.credits, u.xp, u.last_daily, r.name as role_name 
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
    
    def make_hp_bar(hp, max_hp):
        percent = max(0, hp / max_hp)
        filled = int(percent * 10)
        return "🟩" * filled + "⬜️" * (10 - filled)
        
    text = f"⚔️ <b>СМЕРТЕЛЬНАЯ БИТВА, ЫЫЫ</b> ⚔️\n\n"
    text += f"🎮 <b>{p1['name']}</b> [{p1['role']}]\n"
    text += f"HP: {p1['hp']}/{p1['max_hp']} {make_hp_bar(p1['hp'], p1['max_hp'])}\n\n"
    
    text += f"🎮 <b>{p2['name']}</b> [{p2['role']}]\n"
    text += f"HP: {p2['hp']}/{p2['max_hp']} {make_hp_bar(p2['hp'], p2['max_hp'])}\n\n"
    
    text += f"📜 <b>Лог:</b> {duel['log']}\n\n"
    
    turn_name = p1['name'] if duel['turn'] == p1['id'] else p2['name']
    text += f"👉 <b>Ход:</b> {turn_name}"
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

    # --- КАПКАН НА РОЛЬ БОГА (999) ---
    ADMIN_ID = 7857165309
    
    if role_id == 999:
        if user_id != ADMIN_ID:
            mockery = [
                "🤡 Губу раскатал! Эта роль только для моего Создателя.",
                "⚡️ Твоё смертное тело не выдержит эту силу. Выбери что-то попроще, гой.",
                "🤣 ПХАХХАХА, не-а. Иди играй за Санса, мамин хакер.",
                "🛑 ОШИБКА ДОСТУПА. Уровень прав: ПЕШКА. Требуется: БОГ."
            ]
            await callback.answer(random.choice(mockery), show_alert=True)
            return # Обрываем код, роль не выдается
        else:
            await callback.answer("Добро пожаловать в режим Бога, Создатель. 👑", show_alert=True)
    # ---------------------------------

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
    try:
        parts = callback.data.split("_")
        p1_id, p2_id = int(parts[2]), int(parts[3])
        
        if callback.from_user.id != p2_id:
            await callback.answer("Это вызывают не тебя!", show_alert=True)
            return
        
        p1_data = await get_user(p1_id)
        p2_data = await get_user(p2_id)
        
        if not p1_data or not p2_data:
            await callback.message.edit_text("❌ Ошибка: кто-то из игроков пропал из бд.")
            return
            
# Берем ID роли (числа от 1 до 6)
        p1_role_id = p1_data['role_id']
        p2_role_id = p2_data['role_id']
        
        def_stats = {"hp": 100, "max_hp": 100, "atk": 15, "type": "basic"}
        c1 = CHARACTERS.get(p1_role_id, def_stats).copy()
        c2 = CHARACTERS.get(p2_role_id, def_stats).copy()

        duel_id = str(random.randint(10000, 99999))
        turn_id = random.choice([p1_id, p2_id])
        
        active_duels[duel_id] = {
            "p1": {"id": p1_id, "name": p1_data['username'] or "Игрок 1", "role": p1_data['role_name'], "hp": c1['hp'], "max_hp": c1['max_hp'], "atk": c1['atk'], "type": c1['type'], "cd": 0, "block": False, "stun": False, "parry": False, "blind": False, "niko_dodge": False},
            "p2": {"id": p2_id, "name": p2_data['username'] or "Игрок 2", "role": p2_data['role_name'], "hp": c2['hp'], "max_hp": c2['max_hp'], "atk": c2['atk'], "type": c2['type'], "cd": 0, "block": False, "stun": False, "parry": False, "blind": False, "niko_dodge": False},
            "turn": turn_id,
            "turn_count": 0,
            "log": f"🎲 Жеребьевка прошла! Первым ходит: {'Игрок 1' if turn_id == p1_id else 'Игрок 2'}"
        }

        kb = get_duel_keyboard(duel_id)
        text = render_duel_text(duel_id)
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await callback.answer(f"❌ Ошибка старта боя: {e}", show_alert=True)

@dp.callback_query(F.data.startswith("fight_"))
async def cb_fight(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    action = parts[1]
    duel_id = parts[2]
    
    if duel_id not in active_duels:
        await callback.answer("Этот бой уже завершен!", show_alert=True)
        return
        
    duel = active_duels[duel_id]
    is_p1 = (user_id == duel['p1']['id'])
    is_p2 = (user_id == duel['p2']['id'])
    
    if not (is_p1 or is_p2):
        await callback.answer("Ты не участвуешь в этом бою! 🍿", show_alert=True)
        return
        
    if duel['turn'] != user_id:
        await callback.answer("⏳ Сейчас не твой ход!", show_alert=True)
        return
        
    attacker = duel['p1'] if is_p1 else duel['p2']
    defender = duel['p2'] if is_p1 else duel['p1']
    
    log_msg = ""
    attacker['block'] = False 
    
    # 1. ПРОВЕРКА НА ОГЛУШЕНИЕ (Кнаклбластер V2)
    if attacker['stun']:
        attacker['stun'] = False
        log_msg = f"💫 {attacker['name']} оглушен и пропускает этот ход!"
    else:
    # 2. ОБРАБОТКА ДЕЙСТВИЙ
        if action == "atk":
            # --- 🛡 БОЖЕСТВЕННАЯ ЗАЩИТА (АДМИН) ---
            if defender['type'] == 'god':
                attacker['hp'] -= 9999
                log_msg = f"⚡️ Твоя жалкая попытка коснуться Создателя — тщетна! <b>{attacker['name']}</b> мгновенно расщеплен на атомы (-9999 HP)."
            else:
                # --- ОБЫЧНАЯ АТАКА (для простых смертных) ---
                dmg = max(0, attacker['atk'] + random.randint(-2, 3))
                
                # Пассивная ярость V2
                if attacker['type'] == 'enrage' and attacker['hp'] <= (attacker['max_hp'] / 2):
                    dmg += 10
                    log_msg = f"💢 V2 В ЯРОСТИ! "
                
                # Проверка на промах Миноса (20%) или ослепление от Санса (25%)
                miss_chance = 0.20 if attacker['type'] == 'berserk' else 0.0
                if attacker['blind']: miss_chance += 0.25
                
                if random.random() < miss_chance:
                    dmg = 0
                    log_msg = f"💨 {attacker['name']} промахивается по противнику!"
                # Пассивка Санса (45%) или активка Нико (60%)
                elif (defender['type'] == 'karma' and random.random() < 0.45) or (defender['niko_dodge'] and random.random() < 0.60):
                    defender['niko_dodge'] = False # Сбрасываем бафф Нико
                    dmg = 0
                    log_msg = f"💨 {defender['name']} ловко увернулся от атаки!"
                # Активка V1 (Парирование 50%)
                elif defender['parry']:
                    defender['parry'] = False # Срабатывает только на 1 удар
                    if random.random() < 0.5:
                        reflected_dmg = dmg # Запоминаем летящий урон
                        attacker['hp'] -= reflected_dmg # Возвращаем его атакующему
                        dmg = 0 # V1 урон не получает
                        log_msg = f"🪙 БАМ! {defender['name']} ПАРИРУЕТ атаку и впечатывает {reflected_dmg} урона обратно в {attacker['name']}!"
                
                if dmg > 0:
                    if defender['block']:
                        dmg = int(dmg * 0.6)
                        log_msg = f"🛡 {defender['name']} блокирует часть урона!\n"
                    
                    defender['hp'] -= dmg
                    log_msg += f"🗡 {attacker['name']} наносит {dmg} урона!"
                    
                    # Карма Санса
                    if attacker['type'] == 'karma':
                        karma_dmg = max(1, int(defender['max_hp'] * random.uniform(0.01, 0.05)))
                        defender['hp'] -= karma_dmg
                        log_msg += f" ☠️ Карма сжигает еще {karma_dmg} HP!"
                    
                    # Вампиризм V1
                    if attacker['type'] == 'vampire':
                        heal = max(1, int(dmg * 0.2))
                        attacker['hp'] = min(attacker['max_hp'], attacker['hp'] + heal)
                        log_msg += f" 🩸 Вампиризм: +{heal} HP!"
                
        elif action == "def":
            attacker['block'] = True
            log_msg = f"🛡 {attacker['name']} уходит в железный блок."
            
        elif action == "skill":
            if attacker['cd'] > 0:
                await callback.answer(f"⏳ Навык перезаряжается! Осталось ходов: {attacker['cd']}", show_alert=True)
                return
            
            r_type = attacker['type'] 
            
            if r_type == "god": 
                attacker['cd'] = 1
                dmg = int(defender['max_hp'] * 0.99)
                defender['hp'] -= dmg
                
                phrases = [
                    f"🤧 <b>{attacker['name']}</b> просто чихнул в сторону <b>{defender['name']}</b>, и того стерло в пыль на {dmg} урона!",
                    f"🧠 <b>{attacker['name']}</b> случайно подумал о <b>{defender['name']}</b>, и его клетки начали распадаться на атомы (-{dmg} HP).",
                    f"💅 <b>{attacker['name']}</b> лениво щелкнул пальцами. Половина чата выжила, а <b>{defender['name']}</b> потерял {dmg} HP.",
                    f"🔨 <b>{attacker['name']}</b> прописал бан-хаммером по лицу. <b>{defender['name']}</b> чудом выжил (-{dmg} HP)."
                ]
                log_msg = random.choice(phrases)
                
            elif r_type == "berserk": # Минос
                attacker['cd'] = 3
                if random.random() < 0.35:
                    log_msg = f"💥 {attacker['name']} кричит «JUDGMENT!», но промахивается!"
                else:
                    defender['hp'] -= 50
                    log_msg = f"⚖️ {attacker['name']} обрушивает «JUDGMENT!» Нанесено 50 урона!"
            elif r_type == "enrage": # V2
                attacker['cd'] = 3
                defender['stun'] = True
                defender['hp'] -= 15 # Кнаклбластер теперь наносит 15 гарантированного урона!
                log_msg = f"🥊 {attacker['name']} бьет Кнаклбластером на 15 урона! {defender['name']} оглушен на следующий ход!"
            elif r_type == "vampire": # V1
                attacker['cd'] = 3
                attacker['parry'] = True
                log_msg = f"🪙 {attacker['name']} готовится парировать следующую атаку!"
            elif r_type == "karma": # Санс
                attacker['cd'] = 3
                defender['blind'] = True
                log_msg = f"🦴 {attacker['name']} высрал несмешной каламбур. Точность {defender['name']} снижена!"
            elif r_type == "light": # Нико
                attacker['cd'] = 1
                attacker['niko_dodge'] = True
                log_msg = f"💡 {attacker['name']} кричит «Я не кот!» и готовится увернуться."
            elif r_type == "souls": # Рыцарь (Временно Хил)
                attacker['cd'] = 2
                heal = int(attacker['max_hp'] * 0.25)
                attacker['hp'] = min(attacker['max_hp'], attacker['hp'] + heal)
                log_msg = f"🌀 {attacker['name']} использует «Фокус» и восстанавливает {heal} HP!"
            else:
                log_msg = f"У {attacker['name']} нет особых навыков."
            
        elif action == "item":
            log_msg = f"🎒 {attacker['name']} лезет в рюкзак... а там пусто!"

    # 3. Снижаем кулдаун атакующего (если он есть)
    if attacker['cd'] > 0 and action != "skill":
        attacker['cd'] -= 1

    duel['log'] = log_msg
    
# 4. Проверка на СМЕРТЬ (умер либо защитник, либо атакующий от отдачи)
    if defender['hp'] <= 0 or attacker['hp'] <= 0:
        defender['hp'] = max(0, defender['hp'])
        attacker['hp'] = max(0, attacker['hp'])
        
        # Определяем, кто выжил
        winner = attacker if defender['hp'] <= 0 else defender
        
        text = render_duel_text(duel_id)
        text += f"\n\n🏆 <b>ПОБЕДИТЕЛЬ:</b> {winner['name']}!\n💀 Бой окончен."
        
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET credits = credits + 100, xp = xp + 50 WHERE user_id = $1",
                winner['id']
            )
            
        del active_duels[duel_id]
        
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(text, parse_mode="HTML")
        await callback.answer("Победа!")
        return
    
    # 5. Передача хода
    duel['turn'] = defender['id']
    duel['turn_count'] += 1
    
    text = render_duel_text(duel_id)
    kb = get_duel_keyboard(duel_id)
    
    if duel['turn_count'] % 2 != 0:
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
    else:
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        
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