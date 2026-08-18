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

RANK_TITLES = {
    0: "Новичок",
    5: "Прошедший Вьетнам",
    10: "SSSУПЕР ХОРОШ",
    25: "Отказавшийся от личной жизни",
    50: "Оптимус Прайм",
    75: "ПОТУЖНЫЙ",
    100: "Зачем @ Прайм сделал все это?",
    125: "сигма-скибиди228",
    150: "I REGRET NOTHING",
    200: "DEMIGOD"
}

def get_rank_title(xp):
    # Берем самый высокий подходящий титул
    current_rank = "Новичок"
    for threshold in sorted(RANK_TITLES.keys()):
        if xp >= threshold:
            current_rank = RANK_TITLES[threshold]
    return current_rank

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

# --- МАГАЗИН ---
shop_data = {"items": [], "titles": [], "last_update": datetime.now(timezone.utc)}

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

async def refresh_shop_if_needed():
    global shop_data
    # Обновляем, если прошло больше 4 часов или если магазин пуст
    if not shop_data['items'] or (datetime.now(timezone.utc) - shop_data['last_update']) >= timedelta(hours=4):
        async with db_pool.acquire() as conn:
            shop_data['items'] = await conn.fetch("SELECT * FROM items ORDER BY RANDOM() LIMIT 3")
            shop_data['titles'] = await conn.fetch("SELECT * FROM titles WHERE is_admin_only = FALSE ORDER BY RANDOM() LIMIT 2")
        shop_data['last_update'] = datetime.now(timezone.utc)
        logging.info("🏪 Ассортимент магазина обновлен!")

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
            SELECT u.username, u.role_id, u.role_changes, u.credits, u.xp, u.last_daily, u.title_id, r.name as role_name 
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


@dp.message(Command("shop"))
async def cmd_shop(message: types.Message):
    await refresh_shop_if_needed()
    
    items = shop_data['items']
    titles = shop_data['titles']
    
    text = "🏪 <b>Теневой Магазин (завоз каждые 4ч):</b>\n\nВыбирай с умом!\n"
    builder = InlineKeyboardBuilder()
    
    # Кнопки для предметов
    for i in items:
        price = i.get('price', 50)
        builder.button(text=f"📦 {i['name']} ({price} 💰)", callback_data=f"buy_item_{i['id']}_{price}")
        
    # Кнопки для титулов
    for t in titles:
        builder.button(text=f"🏷 {t['name']} ({t['price']} 💰)", callback_data=f"buy_title_{t['id']}_{t['price']}")
        
    builder.adjust(1) # Кнопки идут в столбик
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    buy_type = parts[1] # 'item' или 'title'
    item_id = int(parts[2])
    price = int(parts[3])
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        # Проверяем баланс
        user = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", user_id)
        if not user or user['credits'] < price:
            await callback.answer("❌ Нищеброд! Не хватает кредитов.", show_alert=True)
            return
            
        # Списываем бабки
        await conn.execute("UPDATE users SET credits = credits - $1 WHERE user_id = $2", price, user_id)
        
        if buy_type == "item":
            # Кидаем в рюкзак (если предмет есть - увеличиваем количество)
            await conn.execute("""
                INSERT INTO inventory (user_id, item_id, count) 
                VALUES ($1, $2, 1) 
                ON CONFLICT (user_id, item_id) DO UPDATE 
                SET count = inventory.count + 1
            """, user_id, item_id)
            await callback.answer("✅ Предмет куплен и брошен в рюкзак!", show_alert=True)
            
        elif buy_type == "title":
            # Проверяем, не куплен ли он уже
            exists = await conn.fetchval("SELECT 1 FROM user_titles WHERE user_id = $1 AND title_id = $2", user_id, item_id)
            if exists:
                # Если уже есть, возвращаем деньги
                await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", price, user_id)
                await callback.answer("⚠️ У тебя уже есть этот титул!", show_alert=True)
                return
                
            # Добавляем в коллекцию и сразу надеваем
            await conn.execute("INSERT INTO user_titles (user_id, title_id) VALUES ($1, $2)", user_id, item_id)
            await conn.execute("UPDATE users SET title_id = $1 WHERE user_id = $2", item_id, user_id)
            await callback.answer("👑 Титул куплен и торжественно надет!", show_alert=True)
            
    # Обновляем текст в самом магазине, чтобы игрок видел, что кнопки работают
    await callback.message.edit_text(callback.message.text + f"\n\n<i>{callback.from_user.first_name} только что что-то купил...</i>", reply_markup=callback.message.reply_markup, parse_mode="HTML")
@dp.message(Command("role"))
async def cmd_role(message: types.Message):
    kb = await get_roles_keyboard(message.from_user.id)
    await message.answer("Выбирай себе персонажа:", reply_markup=kb)
@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    try:
        user_id = message.from_user.id
        
        # Шаг 1: Проверяем юзера
        user_data = await get_user(user_id)
        if not user_data:
            await message.answer("🎭 Персонаж: Не выбран (выбери через /role)")
            return
            
        role_str = user_data['role_name'] or "Без роли"
        credits_val = user_data['credits'] or 0
        xp_val = user_data['xp'] or 0
        left_changes = max(0, 1 - (user_data['role_changes'] or 0))
        
        current_title = f"[{get_rank_title(xp_val)}]" 
        
        async with db_pool.acquire() as conn:
            # Шаг 2: Проверяем титул
            if user_data.get('title_id'):
                title_row = await conn.fetchrow("SELECT name FROM titles WHERE id = $1", user_data['title_id'])
                if title_row:
                    current_title = f"[{title_row['name']}] 👑"
                    
            # Шаг 3: Проверяем инвентарь
            inv_items = await conn.fetch("""
                SELECT items.name, count as total_count 
                FROM inventory 
                JOIN items ON inventory.item_id = items.id 
                WHERE user_id = $1 AND count > 0
            """, user_id)
        
        inv_text = "\n".join([f"🎒 {item['name']}: {item['total_count']} шт." for item in inv_items]) or "🎒 Пусто"
        
        status = (
            f"🏆 Титул: <b>{current_title}</b>\n"
            f"🎭 Персонаж: {role_str}\n"
            f"💳 Кредиты: {credits_val} 💰\n"
            f"⭐️ Опыт: {xp_val} XP\n"
            f"🔄 Смен роли: {left_changes}/1\n\n"
            f"<b>Твой рюкзак:</b>\n{inv_text}"
        )
        
        await message.answer(f"👤 <b>Профиль {message.from_user.first_name}</b>\n\n{status}", parse_mode="HTML")

    except Exception as e:
        import traceback
        err_trace = traceback.format_exc()
        await message.answer(f"❌ ОШИБКА В ПРОФИЛЕ:\n<code>{err_trace[-1000:]}</code>", parse_mode="HTML")
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

@dp.message(Command("title"))
async def cmd_title(message: types.Message):
    user_id = message.from_user.id
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT xp, title_id FROM users WHERE user_id = $1", user_id)
        if not user:
            return
        
        # Достаем все титулы, которые купил игрок
        bought_titles = await conn.fetch("""
            SELECT t.id, t.name 
            FROM user_titles ut 
            JOIN titles t ON ut.title_id = t.id 
            WHERE ut.user_id = $1
        """, user_id)
        
    xp = user['xp'] or 0
    builder = InlineKeyboardBuilder()
    
    # 1. Кнопка сброса на обычный ранговый титул (бесплатный)
    current_rank = get_rank_title(xp)
    builder.button(text=f"🔰 Вернуть ранговый: [{current_rank}]", callback_data="equip_title_0")
    
    # 2. Кнопки с купленными титулами
    for t in bought_titles:
        mark = "✅ " if user['title_id'] == t['id'] else "👑 "
        builder.button(text=f"{mark}{t['name']}", callback_data=f"equip_title_{t['id']}")
        
    builder.adjust(1)
    await message.answer("<b>Выбери титул, который хочешь носить:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

# Хендлер переодевания титула
@dp.callback_query(F.data.startswith("equip_title_"))
async def cb_equip_title(callback: types.CallbackQuery):
    title_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        if title_id == 0:
            await conn.execute("UPDATE users SET title_id = NULL WHERE user_id = $1", user_id)
            await callback.answer("🔰 Установлен ранговый титул по умолчанию!", show_alert=True)
        else:
            await conn.execute("UPDATE users SET title_id = $1 WHERE user_id = $2", title_id, user_id)
            await callback.answer("👑 Кастомный титул надет!", show_alert=True)
            
    # Удаляем сообщение с кнопками, чтобы не засорять чат
    await callback.message.delete()

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
            # Ищем предметы в БД
            async with db_pool.acquire() as conn:
                inv = await conn.fetch("""
                    SELECT i.id, i.name, inv.count 
                    FROM inventory inv 
                    JOIN items i ON inv.item_id = i.id 
                    WHERE inv.user_id = $1 AND inv.count > 0
                """, attacker['id'])
            
            if not inv:
                await callback.answer("🎒 Твой рюкзак абсолютно пуст!", show_alert=True)
                return
            
            # Строим клавиатуру с инвентарем (вместо кнопок боя)
            builder = InlineKeyboardBuilder()
            for item in inv:
                builder.button(
                    text=f"🧪 {item['name']} ({item['count']} шт)", 
                    callback_data=f"useitem_{duel_id}_{item['id']}"
                )
            builder.button(text="🔙 Отмена", callback_data=f"fight_back_{duel_id}")
            builder.adjust(1)
            
            await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
            return # Прерываем cb_fight, ждем пока игрок выберет предмет

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
    
@dp.callback_query(F.data.startswith("fight_back_"))
async def cb_fight_back(callback: types.CallbackQuery):
    duel_id = callback.data.split("_")[2]
    if duel_id not in active_duels:
        return
    kb = get_duel_keyboard(duel_id)
    await callback.message.edit_reply_markup(reply_markup=kb)

@dp.callback_query(F.data.startswith("useitem_"))
async def cb_use_item(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    duel_id, item_id = parts[1], int(parts[2])
    user_id = callback.from_user.id
    
    if duel_id not in active_duels:
        await callback.answer("Бой уже окончен!", show_alert=True)
        return
        
    duel = active_duels[duel_id]
    if duel['turn'] != user_id:
        await callback.answer("⏳ Не твой ход!", show_alert=True)
        return
        
    is_p1 = (user_id == duel['p1']['id'])
    attacker = duel['p1'] if is_p1 else duel['p2']
    defender = duel['p2'] if is_p1 else duel['p1']
    
    async with db_pool.acquire() as conn:
        has_item = await conn.fetchrow("SELECT count FROM inventory WHERE user_id = $1 AND item_id = $2", user_id, item_id)
        if not has_item or has_item['count'] <= 0:
            await callback.answer("Этот предмет закончился!", show_alert=True)
            return
        
        # Достаем статы предмета и списываем его
        item = await conn.fetchrow("SELECT name, effect_type, effect_value FROM items WHERE id = $1", item_id)
        await conn.execute("UPDATE inventory SET count = count - 1 WHERE user_id = $1 AND item_id = $2", user_id, item_id)
        await conn.execute("DELETE FROM inventory WHERE count <= 0") # Убираем мусор
        
    # --- 1. ПРИМЕНЯЕМ ЭФФЕКТ ---
    e_type, e_val = item['effect_type'], item['effect_value']
    
    if e_type == 'heal':
        attacker['hp'] = min(attacker['max_hp'], attacker['hp'] + e_val)
        duel['log'] = f"🧪 {attacker['name']} выпивает {item['name']}! Восстановлено {e_val} HP."
    elif e_type == 'dmg':
        defender['hp'] -= e_val
        duel['log'] = f"💣 {attacker['name']} швыряет {item['name']} в лицо противнику на {e_val} урона!"
    elif e_type == 'buff':
        attacker['atk'] += e_val
        duel['log'] = f"💉 {attacker['name']} вкалывает {item['name']}. Атака повышена на {e_val}!"
        
    if attacker['cd'] > 0:
        attacker['cd'] -= 1

    # --- 2. ПРОВЕРКА НА СМЕРТЬ (КОПИЯ ИЗ cb_fight) ---
    if defender['hp'] <= 0 or attacker['hp'] <= 0:
        defender['hp'], attacker['hp'] = max(0, defender['hp']), max(0, attacker['hp'])
        winner = attacker if defender['hp'] <= 0 else defender
        
        text = render_duel_text(duel_id)
        text += f"\n\n🏆 <b>ПОБЕДИТЕЛЬ:</b> {winner['name']}!\n💀 Бой окончен."
        
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET credits = credits + 100, xp = xp + 50 WHERE user_id = $1", winner['id'])
            
        del active_duels[duel_id]
        try:
            await callback.message.delete()
        except: pass
        await callback.message.answer(text, parse_mode="HTML")
        await callback.answer("Победа!")
        return

    # --- 3. ПЕРЕДАЧА ХОДА ---
    duel['turn'] = defender['id']
    duel['turn_count'] += 1
    
    text = render_duel_text(duel_id)
    kb = get_duel_keyboard(duel_id)
    
    if duel['turn_count'] % 2 != 0:
        try: await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except: pass
    else:
        try: await callback.message.delete()
        except: pass
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        
    await callback.answer("Предмет использован!")

# --- СЕРВЕР ---
async def health_check(request):
    return web.Response(text="Bot is alive!", status=200)

async def on_startup(bot: Bot):
    await init_db()
    await refresh_shop_if_needed() # <--- ДОБАВЬ ЭТО
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