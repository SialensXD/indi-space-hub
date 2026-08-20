print("=== СТАРТ БОТА ===", flush=True)
import os
import sys
import logging
import asyncio
import asyncpg
from datetime import datetime, timezone, timedelta

from config import (
    ADMIN_USER_ID,
    ADMIN_USERNAMES,
    ALLOWED_GROUPS,
    BOT_TOKEN,
    DATABASE_URL,
    PORT,
    WEBHOOK_SECRET,
    WEBHOOK_PATH,
    webhook_url,
)
from domain import (
    generate_progress_bar,
    get_level,
    get_next_level_xp,
    get_rank_title,
    parse_time,
)
from game_data import CHARACTERS, SKILL_GIFS, SLOT_SYMBOLS
from handlers.shop import register_shop_handlers
from handlers.moderation import register_moderation_handlers
from handlers.user import register_user_handlers
from handlers.casino import register_casino_handlers

from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.types import BotCommand

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db_pool = None

START_TIME = datetime.now(timezone.utc)

import random

import re

import uuid

active_chests = set() 

# Кэш триггеров в ОЗУ
TRIGGERS_CACHE = {}

async def load_triggers_cache():
    global TRIGGERS_CACHE
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT phrase, reply_text FROM triggers")
        TRIGGERS_CACHE = {r['phrase']: r['reply_text'] for r in rows}
    logging.info(f"Кэш триггеров загружен: {len(TRIGGERS_CACHE)} шт.")

# СЛОВАРИ ДЛЯ БОЕВКИ
active_duels = {}
duel_invites = {}

# --- МАГАЗИН ---
shop_data = {"items": [], "titles": [], "last_update": datetime.now(timezone.utc)}

from aiogram import BaseMiddleware
from aiogram.types import Message

# ID моего чата (или нескольких чатов)
class AntiTheftMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # Проверяем только входящие сообщения
        if isinstance(event, Message):
            chat = event.chat
            
            # 1. Если это ЛС - пускаем
            if chat.type == 'private':
                return await handler(event, data)
            
            # 2. Если это группа, проверяем, есть ли она в белом списке
            if chat.id in ALLOWED_GROUPS:
                return await handler(event, data)
                
            # 3. Если группа чужая — караем
            try:
                logging.warning(f"🚨 Опа, у нас тут попытка угона! Чат: {chat.title} ({chat.id})")
                await event.answer("🧿Попытка угона? Я предусмотрел и такое. \nБот в чужих чатах не работает. \nС любовью, Ваш Сиаленс😘")
                await event.bot.leave_chat(chat.id) # Бот сам выходит из группы
            except Exception:
                pass
            return # Прерываем цепочку, команды не выполнятся
            
        # Для callback-кнопок и прочего просто пропускаем дальше
        return await handler(event, data)

# --- БАЗА ДАННЫХ (POSTGRESQL) ---
async def init_db():
    global db_pool
    dsn = DATABASE_URL.replace("postgres://", "postgresql://")
    try:
        db_pool = await asyncpg.create_pool(
            dsn=dsn,
            statement_cache_size=0,
            min_size=1,
            max_size=5,
        )
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    role_id INTEGER,
                    role_changes INTEGER NOT NULL DEFAULT 0,
                    credits INTEGER NOT NULL DEFAULT 100,
                    xp INTEGER NOT NULL DEFAULT 0,
                    last_daily TIMESTAMPTZ,
                    title_id INTEGER,
                    msg_count INTEGER NOT NULL DEFAULT 0,
                    notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    wins INTEGER NOT NULL DEFAULT 0,
                    warns INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS roles (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    price INTEGER NOT NULL DEFAULT 50,
                    effect_type TEXT NOT NULL,
                    effect_value INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS titles (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    price INTEGER NOT NULL DEFAULT 0,
                    is_admin_only BOOLEAN NOT NULL DEFAULT FALSE
                );
                CREATE TABLE IF NOT EXISTS inventory (
                    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                    item_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, item_id)
                );
                CREATE TABLE IF NOT EXISTS user_titles (
                    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                    title_id INTEGER REFERENCES titles(id) ON DELETE CASCADE,
                    PRIMARY KEY (user_id, title_id)
                );
                CREATE TABLE IF NOT EXISTS triggers (
                    id SERIAL PRIMARY KEY,
                    phrase TEXT UNIQUE NOT NULL,
                    reply_text TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mod_logs (
                    id BIGSERIAL PRIMARY KEY,
                    target_id BIGINT NOT NULL,
                    target_username TEXT NOT NULL,
                    admin_username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            await conn.execute("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS role_id INTEGER;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS role_changes INTEGER DEFAULT 0;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS credits INTEGER DEFAULT 100;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS xp INTEGER DEFAULT 0;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily TIMESTAMPTZ;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS title_id INTEGER;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS msg_count INTEGER DEFAULT 0;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS notifications_enabled BOOLEAN DEFAULT TRUE;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS wins INTEGER DEFAULT 0;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS warns INTEGER DEFAULT 0;

                ALTER TABLE roles ADD COLUMN IF NOT EXISTS name TEXT;
                ALTER TABLE items ADD COLUMN IF NOT EXISTS name TEXT;
                ALTER TABLE items ADD COLUMN IF NOT EXISTS price INTEGER DEFAULT 50;
                ALTER TABLE items ADD COLUMN IF NOT EXISTS effect_type TEXT DEFAULT 'heal';
                ALTER TABLE items ADD COLUMN IF NOT EXISTS effect_value INTEGER DEFAULT 0;
                ALTER TABLE titles ADD COLUMN IF NOT EXISTS name TEXT;
                ALTER TABLE titles ADD COLUMN IF NOT EXISTS price INTEGER DEFAULT 0;
                ALTER TABLE titles ADD COLUMN IF NOT EXISTS is_admin_only BOOLEAN DEFAULT FALSE;
                ALTER TABLE inventory ADD COLUMN IF NOT EXISTS user_id BIGINT;
                ALTER TABLE inventory ADD COLUMN IF NOT EXISTS item_id INTEGER;
                ALTER TABLE inventory ADD COLUMN IF NOT EXISTS count INTEGER DEFAULT 0;
                ALTER TABLE user_titles ADD COLUMN IF NOT EXISTS user_id BIGINT;
                ALTER TABLE user_titles ADD COLUMN IF NOT EXISTS title_id INTEGER;
                ALTER TABLE mod_logs ADD COLUMN IF NOT EXISTS target_id BIGINT;
                ALTER TABLE mod_logs ADD COLUMN IF NOT EXISTS target_username TEXT;
                ALTER TABLE mod_logs ADD COLUMN IF NOT EXISTS admin_username TEXT;
                ALTER TABLE mod_logs ADD COLUMN IF NOT EXISTS action TEXT;
                ALTER TABLE mod_logs ADD COLUMN IF NOT EXISTS reason TEXT;
                ALTER TABLE mod_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

                CREATE UNIQUE INDEX IF NOT EXISTS users_user_id_unique ON users (user_id);
            """)
        logging.info("✅ Подключение к БД успешно!")
    except Exception as e:
        logging.exception("❌ Ошибка БД")
        if db_pool is not None:
            await db_pool.close()
            db_pool = None
        raise RuntimeError("Database initialization failed") from e

async def refresh_shop_if_needed():
    global shop_data
    if not shop_data['items'] or (datetime.now(timezone.utc) - shop_data['last_update']) >= timedelta(hours=4):
        async with db_pool.acquire() as conn:
            shop_data['items'] = await conn.fetch("SELECT * FROM items ORDER BY RANDOM() LIMIT 4")
            shop_data['titles'] = await conn.fetch("SELECT * FROM titles WHERE is_admin_only = FALSE ORDER BY RANDOM() LIMIT 4")
            
            # --- НОВЫЙ БЛОК: РАССЫЛКА ---
            if shop_data['last_update'] != datetime.min.replace(tzinfo=timezone.utc): # Не спамим при самом первом запуске
                users_to_notify = await conn.fetch("SELECT user_id FROM users WHERE notifications_enabled = TRUE")
                for u in users_to_notify:
                    try:
                        await bot.send_message(
                            u['user_id'], 
                            "🏪 <b>В магазине обновился ассортимент!</b>", 
                            parse_mode="HTML"
                        )
                        await asyncio.sleep(0.05) # Лимиты Telegram
                    except Exception:
                        pass # Юзер мог заблокировать бота
            # -----------------------------

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
            SELECT u.username, u.role_id, u.role_changes, u.credits, u.xp, u.last_daily, u.title_id, 
                   u.msg_count, u.notifications_enabled, r.name as role_name 
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


def get_db_pool():
    if db_pool is None:
        raise RuntimeError("Database pool is not initialized")
    return db_pool

register_casino_handlers(
    dp,
    db_pool_getter=get_db_pool,
    bot=bot,
    slot_symbols=SLOT_SYMBOLS,
)

async def setup_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="🚀 Проверка/список (ЛС онли)"),
        BotCommand(command="role", description="🎭 Выбрать/сменить персонажа"),
        BotCommand(command="profile", description="👤 Профиль, статы и рюкзак"),
        BotCommand(command="daily", description="🎁 Забрать ежедневную награду"),
        BotCommand(command="shop", description="🏪 Магазин предметов и титулов"),
        BotCommand(command="slots", description="🎰 Казино (слоты)"),
        BotCommand(command="dice", description="🎲 Кости (пвп)"),
        BotCommand(command="duel", description="⚔️ Вызвать на дуэль (ответь на сообщение)"),
        BotCommand(command="top", description="📊 Топ игроков чата"),
        BotCommand(command="title", description="👑 Управление титулами"),
    ]
    await bot.set_my_commands(commands)

get_shop_keyboard = register_shop_handlers(
    dp,
    db_pool_getter=get_db_pool,
    shop_data=shop_data,
    refresh_shop_if_needed=refresh_shop_if_needed,
)

@dp.message(Command("role"))
async def cmd_role(message: types.Message):
    kb = await get_roles_keyboard(message.from_user.id)
    await message.answer("Выбирай себе персонажа:", reply_markup=kb)

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    user_data = await get_user(user_id)
    
    if not user_data:
        await message.answer("🎭 Персонаж: Не выбран (выбери через /role)")
        return
        
    role_str = user_data['role_name'] or "Без роли"
    credits_val = user_data['credits'] or 0
    xp_val = user_data['xp'] or 0
    msg_count = user_data['msg_count'] or 0
    left_changes = max(0, 1 - (user_data['role_changes'] or 0))
    notif_enabled = user_data['notifications_enabled']
    
    lvl = get_level(xp_val)
    next_xp = get_next_level_xp(lvl)
    left_xp = next_xp - xp_val
    current_title = f"[{get_rank_title(xp_val)} | Lvl {lvl}]" 
    
    async with db_pool.acquire() as conn:
        if user_data['title_id']:
            title_row = await conn.fetchrow("SELECT name FROM titles WHERE id = $1", user_data['title_id'])
            if title_row:
                current_title = f"[{title_row['name']}] 👑 [Lvl {lvl}]"

        inv_items = await conn.fetch("""
            SELECT items.name, count as total_count 
            FROM inventory 
            JOIN items ON inventory.item_id = items.id 
            WHERE user_id = $1 AND count > 0
        """, user_id)

    # Красивый вывод инвентаря
    if inv_items:
        inv_text = "\n".join([f"🔸 <b>{item['name']}</b>: <code>{item['total_count']} шт.</code>" for item in inv_items])
    else:
        inv_text = "<i>Пусто...</i>"
        
    # Генерируем полоску опыта
    xp_bar = generate_progress_bar(xp_val, next_xp, length=12)
    
    # Собираем красивую "карточку"
    status = (
        f"🪪 <b>КАРТОЧКА ИГРОКА: {message.from_user.first_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎭 <b>Роль:</b> {role_str}\n"
        f"👑 <b>Титул:</b> {current_title}\n\n"
        f"📊 <b>СТАТИСТИКА</b>\n"
        f"├ 💬 Сообщений: <code>{msg_count}</code>\n"
        f"├ 💳 Баланс: <code>{credits_val}</code> 💰\n"
        f"└ 🔄 Смен роли: <code>{left_changes}/1</code>\n\n"
        f"✨ <b>УРОВЕНЬ {lvl}</b>\n"
        f"<code>{xp_bar}</code>\n"
        f"<i>{xp_val} / {next_xp} XP (до апгрейда: {left_xp})</i>\n\n"
        f"🎒 <b>ИНВЕНТАРЬ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{inv_text}"
    )
    
    # Кнопка для настройки уведомлений
    builder = InlineKeyboardBuilder()
    notif_text = "🔕 Выключить рассылку" if notif_enabled else "🔔 Включить рассылку"
    builder.button(text=notif_text, callback_data="toggle_notif")
    
    # Отправляем обновленный профиль
    await message.answer(status, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "toggle_notif")
async def cb_toggle_notif(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        # Узнаем текущий статус и меняем на противоположный
        current_status = await conn.fetchval("SELECT notifications_enabled FROM users WHERE user_id = $1", user_id)
        new_status = not current_status
        await conn.execute("UPDATE users SET notifications_enabled = $1 WHERE user_id = $2", new_status, user_id)
    
    # Показываем всплывающее уведомление
    status_msg = "включены ✅" if new_status else "выключены ❌"
    await callback.answer(f"Рассылка {status_msg}!", show_alert=True)
    
    # Формируем новую кнопку
    builder = InlineKeyboardBuilder()
    notif_text = "🔕 Выключить рассылку" if new_status else "🔔 Включить рассылку"
    builder.button(text=notif_text, callback_data="toggle_notif")
    
    # Элегантно обновляем только клавиатуру под сообщением
    try:
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    except Exception:
        pass # Игнорируем ошибку, если вдруг API телеграма ругнется на то, что клавиатура не изменилась
    
# Словарь для активных боев в памяти: { duel_id: { "p1": id, "p2": id, "turn": id, ... } }
active_duels = {}
duel_invites = {} # Для хранения непринятых вызовов

register_user_handlers(
    dp,
    db_pool_getter=get_db_pool,
    get_user=get_user,
    start_time=START_TIME,
    trigger_cache=TRIGGERS_CACHE,
    active_duels=active_duels,
)

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

register_moderation_handlers(
    dp,
    db_pool_getter=get_db_pool,
    bot=bot,
    admin_usernames=ADMIN_USERNAMES,
    shop_data=shop_data,
    refresh_shop_if_needed=refresh_shop_if_needed,
    trigger_cache=TRIGGERS_CACHE,
    parse_time=parse_time,
)

# --- ГЕНЕРАТОР ВКЛАДОК ТОПА ---
def get_top_keyboard(current_tab="xp"):
    builder = InlineKeyboardBuilder()
    # Подсвечиваем активную вкладку галочкой
    builder.button(text="✅ ⭐️ Опыт" if current_tab == "xp" else "⭐️ Опыт", callback_data="top_xp")
    builder.button(text="✅ 🏆 Победы" if current_tab == "wins" else "🏆 Победы", callback_data="top_wins")
    builder.button(text="✅ 💬 Актив" if current_tab == "msg" else "💬 Актив", callback_data="top_msg")
    builder.adjust(3)
    return builder.as_markup()

# Универсальная функция отрисовки топа
async def render_top(event, tab, is_edit=False):
    queries = {
        "xp": ("xp", "⭐️ ОПЫТУ", "XP"),
        "wins": ("wins", "🏆 ПОБЕДАМ НА АРЕНЕ", "побед"),
        "msg": ("msg_count", "💬 АКТИВНОСТИ В ЧАТЕ", "сообщений")
    }
    col, title, suffix = queries[tab]
    
    async with db_pool.acquire() as conn:
        # Вытаскиваем топ-10, у кого значение больше нуля
        users = await conn.fetch(f"""
            SELECT username, COALESCE({col}, 0) as val 
            FROM users 
            WHERE {col} IS NOT NULL AND {col} > 0 
            ORDER BY {col} DESC LIMIT 10
        """)
    
    text = f"📊 <b>ТОП-10 ИГРОКОВ ПО {title}</b>\n\n"
    if not users:
        text += "<i>Пока что тут пусто...</i>"
    else:
        for i, u in enumerate(users, 1):
            # Медали для первой тройки
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name = u['username'] or "Аноним"
            text += f"{medal} <b>{name}</b> — {u['val']} {suffix}\n"
    
    kb = get_top_keyboard(tab)
    
    if is_edit:
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.message(Command("top"))
async def cmd_top(message: types.Message):
    # По умолчанию открываем топ по опыту
    await render_top(message, "xp", is_edit=False)

@dp.message(F.new_chat_members)
async def welcome_new_members(message: types.Message):
    for member in message.new_chat_members:
        if member.is_bot:
            continue

        # Вносим новичка в БД
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (user_id, username, credits, xp, role_changes) 
                VALUES ($1, $2, 100, 0, 0) 
                ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
                """,
                member.id, member.username or ""
            )

        text = (
            f"🙌 <b>Велком, {member.first_name}!</b>\n\n"
            f"Я Картер (Мейби ты уже меня знаешь). *тут вся инфа и поздравления, потом вставлю*\n\n"
            f"Для начала тебе начислен стартовый баланс <b>100 💰</b>. Веселись! 😉\n"
            
        )
        await message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data.startswith("top_"))
async def cb_top_tab(callback: types.CallbackQuery):
    tab = callback.data.split("_")[1]
    await render_top(callback, tab, is_edit=True)

@dp.callback_query(F.data.startswith("role_"))
async def callbacks_num(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    role_id = int(callback.data.split("_")[1])
    is_admin = username.lower() in [a.lower() for a in ADMIN_USERNAMES]

    # --- КАПКАН НА РОЛЬ БОГА (999) ---
    if role_id == 999:
        if user_id != ADMIN_USER_ID:
            mockery = [
                "🤡 Губу раскатал! Эта роль только для всемилюбимого Создателя.",
                "⚡️ Твоё смертное тело не выдержит эту силу. Выбери что-то попроще, гой.",
                "🤣 ПХАХХАХА, не-а. Иди играй за Санса, упырь.",
                "🛑 ОШИБКА ДОСТУПА. Уровень прав: ОСЕЛ. Требуется: БОГ."
            ]
            await callback.answer(random.choice(mockery), show_alert=True)
            return 
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
        await callback.answer("Ты не участвуешь в этом бою! 👺", show_alert=True)
        return
        
    if duel['turn'] != user_id:
        await callback.answer("⏳ Сейчас не твой ход!", show_alert=True)
        return
        
    attacker = duel['p1'] if is_p1 else duel['p2']
    defender = duel['p2'] if is_p1 else duel['p1']
    
    log_msg = ""
    attacker['block'] = False 
    turn_gif = None # <--- Переменная для хранения гифки на этот ход
    
    # 1. ПРОВЕРКА НА ОГЛУШЕНИЕ (Кнаклбластер V2)
    if attacker['stun']:
        attacker['stun'] = False
        log_msg = f"💫 {attacker['name']} оглушен и пропускает этот ход!"
    else:
    # 2. ОБРАБОТКА ДЕЙСТВИЙ
        if action == "atk":
            if defender['type'] == 'god':
                attacker['hp'] -= 9999
                log_msg = f"⚡️ Твоя жалкая попытка коснуться Создателя — тщетна! <b>{attacker['name']}</b> расщеплен на атомы (-9999 HP)."
            else:
                dmg = max(0, attacker['atk'] + random.randint(0, 0))
                
                if attacker['type'] == 'enrage' and attacker['hp'] <= (attacker['max_hp'] / 3):
                    dmg += 12
                    log_msg = f"💢 V2 В ЯРОСТИ! "
                
                miss_chance = 0.20 if attacker['type'] == 'berserk' else 0.0
                if attacker['blind']: miss_chance += 0.25
                
                if random.random() < miss_chance:
                    dmg = 0
                    log_msg = f"💨 {attacker['name']} промахивается по противнику!"
                elif (defender['type'] == 'karma' and random.random() < 0.95) or (defender['niko_dodge'] and random.random() < 0.60):
                    defender['niko_dodge'] = False 
                    dmg = 0
                    log_msg = f"💨 {defender['name']} ловко увернулся от атаки!"
                
                # --- ЛОГИКА ПАРИРОВАНИЯ И ГИФКИ V1 ---
                elif defender['parry']:
                    defender['parry'] = False 
                    if random.random() < 1.0:
                        reflected_dmg = dmg 
                        attacker['hp'] -= reflected_dmg 
                        dmg = 0 
                        log_msg = f"🪙 БАМ! {defender['name']} ПАРИРУЕТ атаку и впечатывает {reflected_dmg} урона обратно!"
                        turn_gif = SKILL_GIFS.get("vampire") # Гифка парирования вылетает ТОЛЬКО сейчас!
                
                if dmg > 0:
                    if defender['block']:
                        dmg = int(dmg * 0.5)
                        log_msg = f"🛡 {defender['name']} блокирует часть урона!\n"
                    
                    defender['hp'] -= dmg
                    log_msg += f"🗡 {attacker['name']} наносит {dmg} урона!"
                    
                    if attacker['type'] == 'karma':
                        
                        karma_dmg = max(1, int(defender['max_hp'] * 0.07))
                        defender['hp'] -= karma_dmg
                        log_msg += f" ☠️ Карма сжигает еще {karma_dmg} HP!"
                    
                    if attacker['type'] == 'vampire':
                        heal = max(1, int(dmg * 0.4))
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
            
            # --- ПРИВЯЗЫВАЕМ ГИФКИ КО ВСЕМ НАВЫКАМ, КРОМЕ V1 ---
            if r_type != "vampire":
                turn_gif = SKILL_GIFS.get(r_type)
            
            is_karma_dodge = (defender['type'] == 'karma' and random.random() < 0.93)

            if r_type == "god": 
                attacker['cd'] = 0
                dmg = int(defender['max_hp'] * 0.99)
                defender['hp'] -= dmg
                log_msg = f"🤧 <b>{attacker['name']}</b> чихнул и стер <b>{defender['name']}</b> в пыль на {dmg} урона!"
                    
            elif r_type == "berserk":
                attacker['cd'] = 3
                if random.random() < 0.35:
                    log_msg = f"💥 {attacker['name']} кричит «JUDGMENT!», но промахивается!"
                elif is_karma_dodge:
                    log_msg = f"💨 {defender['name']} ловко увернулся от Жажмента"
                else:
                    defender['hp'] -= 40
                    log_msg = f"⚖️ {attacker['name']} обрушивает «JUDGMENT!» Нанесено 40 урона!"
                    
            elif r_type == "enrage": 
                attacker['cd'] = 3
                if is_karma_dodge:
                    log_msg = f"💨 {defender['name']} ловко увернулся от Кнаклбластера!"
                else:
                    defender['stun'] = True
                    defender['hp'] -= 15 
                    log_msg = f"🥊 {attacker['name']} бьет Кнаклбластером на 15 урона! {defender['name']} оглушен!"
                    
            elif r_type == "vampire": 
                attacker['cd'] = 3
                attacker['parry'] = True
                log_msg = f"🪙 {attacker['name']} готовится парировать следующую атаку!"
                
            elif r_type == "karma": 
                attacker['cd'] = 3
                defender['blind'] = True
                log_msg = f"🦴 {attacker['name']} снижает точность {defender['name']}!"
                    
            elif r_type == "light": 
                attacker['cd'] = 1
                attacker['niko_dodge'] = True
                log_msg = f"💡 {attacker['name']} готовится увернуться."
                
            elif r_type == "souls": 
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
        defender['hp'], attacker['hp'] = max(0, defender['hp']), max(0, attacker['hp'])
        winner = attacker if defender['hp'] <= 0 else defender
        
        # Настраиваем размер награды
        win_xp = 50
        win_credits = 25
        
        text = render_duel_text(duel_id)
        text += (
            f"\n\n🏆 <b>ПОБЕДИТЕЛЬ:</b> {winner['name']}!\n"
            f"🎁 <b>Награда:</b> +{win_xp} XP и +{win_credits} 💰\n"
            f"💀 Бой окончен."
        )
        
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET credits = credits + $1, xp = xp + $2, wins = COALESCE(wins, 0) + 1 WHERE user_id = $3", win_credits, win_xp, winner['id'])
            
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
    
# Если на этом ходу сработала гифка - кидаем медиа-сообщение
    if turn_gif and not turn_gif.startswith("тут_"):
        try: await callback.message.delete()
        except: pass
        
        # Текст боя становится подписью (caption) к гифке, а кнопки крепятся снизу
        await callback.message.answer_animation(
            animation=turn_gif, 
            caption=text, 
            reply_markup=kb, 
            parse_mode="HTML"
        )
    else:
        # Обычный текстовый ход
        if duel['turn_count'] % 2 != 0:
            try: 
                await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            except Exception: 
                # Сработает, если на прошлом ходу была гифка, и мы пытаемся edit_text на медиа-файле
                try: await callback.message.delete()
                except: pass
                await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        else:
            try: await callback.message.delete()
            except: pass
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
        
        # Настраиваем размер награды
        win_xp = 50
        win_credits = 25
        
        text = render_duel_text(duel_id)
        text += (
            f"\n\n🏆 <b>ПОБЕДИТЕЛЬ:</b> {winner['name']}!\n"
            f"🎁 <b>Награда:</b> +{win_xp} XP и +{win_credits} 💰\n"
            f"💀 Бой окончен."
        )
        
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET credits = credits + $1, xp = xp + $2, wins = COALESCE(wins, 0) + 1 WHERE user_id = $3", win_credits, win_xp, winner['id'])
            
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

@dp.message(F.text & ~F.text.startswith('/'))
async def track_messages(message: types.Message):
    user_id = message.from_user.id
    msg_text = message.text.lower()
    chat_id = message.chat.id

    async with db_pool.acquire() as conn:
        try:
            await conn.execute("UPDATE users SET msg_count = COALESCE(msg_count, 0) + 1 WHERE user_id = $1", user_id)
        except Exception:
            pass

    # --- СИСТЕМА СУНДУКОВ ---
    # Сундуки падают только в группах с шансом, например, 3% на каждое сообщение
    if message.chat.type in ['group', 'supergroup'] and random.random() < 0.0025:
        chest_id = str(uuid.uuid4())[:8]
        active_chests.add(chest_id)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🎁 Забрать", callback_data=f"chest_claim_{chest_id}")
        
        await message.answer(
            "🔔 <b>Внезапный дроп!</b>\nКто-то обронил сундук с кредитами. Кто первый нажмет — того и лут!", 
            reply_markup=builder.as_markup(), 
            parse_mode="HTML"
        )

    # Мгновенная проверка триггеров
    for phrase, reply_text in TRIGGERS_CACHE.items():
        pattern = rf'(?<!\w){re.escape(phrase)}(?!\w)'
        if re.search(pattern, msg_text):
            await message.reply(reply_text, parse_mode="HTML")
            break

# Хендлер нажатия на сундук
@dp.callback_query(F.data.startswith("chest_claim_"))
async def cb_chest_claim(callback: types.CallbackQuery):
    chest_id = callback.data.split("_")[2]
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name
    
    if chest_id not in active_chests:
        await callback.answer("Увы и ах, сундук уже кто-то обчистил или он испарился!", show_alert=True)
        return
        
    # Удаляем сундук, чтобы никто больше не забрал
    active_chests.remove(chest_id)
    reward = random.randint(200, 700) # Рандомная награда
    
    async with db_pool.acquire() as conn:
        # Проверяем, есть ли юзер в базе
        user_exists = await conn.fetchval("SELECT 1 FROM users WHERE user_id = $1", user_id)
        if not user_exists:
            await conn.execute("INSERT INTO users (user_id, username, credits, xp, role_changes) VALUES ($1, $2, $3, 0, 0)", user_id, callback.from_user.username or "", reward)
        else:
            await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", reward, user_id)
            
    await callback.message.edit_text(
        f"🎁 <b>{user_name}</b> оказался самым быстрым и забрал из сундука <b>{reward} 💰</b>!",
        parse_mode="HTML"
    )
    await callback.answer(f"Ты получил {reward} кредитов!")

# --- СЕРВЕР ---
async def health_check(request):
    return web.Response(text="Bot is alive!", status=200)

async def on_startup(bot: Bot):
    await init_db()
    await refresh_shop_if_needed()
    await load_triggers_cache()
    await setup_bot_commands(bot) # Регистр меню команд
    url = webhook_url()
    if url:
        await bot.set_webhook(url, drop_pending_updates=True)

async def on_shutdown(bot: Bot):
    if db_pool is not None:
        await db_pool.close()
    await bot.session.close()

def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    dp.message.middleware(AntiTheftMiddleware())
    app = web.Application()
    app.router.add_get('/', health_check)
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()