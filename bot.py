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
from aiogram.types import BotCommand

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

TOKEN = "8883956292:AAF0wZaZJVdw6JSQ3UaPk6E4TMOE86FUqCs"
WEBHOOK_PATH = "/webhook"
ADMIN_USERNAMES = ["sialens_xd"]
DATABASE_URL = os.environ.get("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
db_pool = None

START_TIME = datetime.now(timezone.utc)

import random

import math

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

def parse_time(time_str: str) -> timedelta:
    """Парсит строки типа '10m', '2h', '1d' в timedelta"""
    unit = time_str[-1].lower()
    value = int(time_str[:-1])
    if unit == 'м': return timedelta(minutes=value)
    elif unit == 'ч': return timedelta(hours=value)
    elif unit == 'д': return timedelta(days=value)
    else: return timedelta(minutes=value) # По умолчанию минуты

def get_level(xp):
    """Высчитывает текущий уровень по квадратичной формуле"""
    if xp < 5:
        return 0
    return int(math.sqrt(xp / 5))

def get_next_level_xp(level):
    return 5 * ((level + 1) ** 2)

def get_rank_title(xp):
    lvl = get_level(xp)
    if lvl < 5:
        return f"Новичок"
    elif lvl < 15:
        return f"Пережил Вьетнам"
    elif lvl < 30:
        return f"Без личной жизни"
    elif lvl < 50:
        return f"Оптимус Прайм"
    elif lvl < 100:
        return f"ПОТУЖНЫЙ"
    elif lvl < 200:
        return f"сигма-скибиди228"
    else:
        return f"I REGRET NOTHING"

# СЛОВАРИ ДЛЯ БОЕВКИ
active_duels = {}
duel_invites = {}

# БАЗОВЫЕ СТАТЫ ПЕРСОНАЖЕЙ (привязаны к role_id из БД)
CHARACTERS = {
    1: {"hp": 100, "max_hp": 100, "atk": 15, "type": "souls"},   
    2: {"hp": 95, "max_hp": 95, "atk": 12, "type": "light"},     
    3: {"hp": 50, "max_hp": 50, "atk": 5, "type": "karma"},      
    4: {"hp": 100, "max_hp": 100, "atk": 15, "type": "vampire"}, 
    5: {"hp": 125, "max_hp": 125, "atk": 15, "type": "enrage"},  
    6: {"hp": 140, "max_hp": 140, "atk": 19, "type": "berserk"},
    # МОЯ АДМИНСКАЯ РОЛЬ
    999: {"hp": 9999, "max_hp": 9999, "atk": 9999, "type": "god"} 
}

# Гифки для спец-атак
SKILL_GIFS = {
    "god": "CgACAgIAAyEFAATuFYO6AAIBFGqDDUvNeyrykVmC0FV6nUlidfHbAALSpgACh5HoS43Z8PpZnYurPQQ",
    "berserk": "CgACAgIAAxkBAAOBaoTqBA5NC1-tj3E4kfpmln15A28AAgmqAAKU3yFI3isVHX0Wp6g9BA",
    "enrage": "CgACAgIAAxkBAAOGaoTqtU_-i746Ps8je2RcBBQ4VlQAAgyqAAKU3yFIC7s2LleYvjM9BA",
    "vampire": "CgACAgIAAxkBAAOIaoTq1KHEeqRI6UISOtOq-8QJWFIAAg2qAAKU3yFInZVWVcf-7Jo9BA",
    "karma": "CgACAgIAAxkBAAOKaoTrno_MtK1bhhlRDzzAqadPMcUAAg6qAAKU3yFIeGnOjHQrPe09BA",
    "light": "CgACAgIAAxkBAAONaoTr07Wre4FlnhDNQTqAxiGeHCUAAg-qAAKU3yFIq1sILGVxN1k9BA",
    "souls": "CgACAgIAAxkBAAOEaoTqcQ6ZdM6aAAEcAWN07ZQFOy6jAAILqgAClN8hSEhkcIg6sjqEPQQ"
}

# --- МАГАЗИН ---
shop_data = {"items": [], "titles": [], "last_update": datetime.now(timezone.utc)}

from aiogram import BaseMiddleware
from aiogram.types import Message

# ID моего чата (или нескольких чатов)
ALLOWED_GROUPS = [-1003994387386]

def generate_progress_bar(current, target, length=10):
    if target <= 0:
        return "█" * length
    # Защита от переполнения бара
    progress = min(1.0, current / target)
    filled_blocks = int(length * progress)
    empty_blocks = length - filled_blocks
    # Используем символы ASCII-графики
    return f"[{'█' * filled_blocks}{'░' * empty_blocks}]"

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
    if not DATABASE_URL:
        logging.error("❌ DATABASE_URL не найден!")
        return
    
    dsn = DATABASE_URL.replace("postgres://", "postgresql://")
    try:
        db_pool = await asyncpg.create_pool(
            dsn=dsn,
            statement_cache_size=0
        )
        async with db_pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM users a USING users b 
                WHERE a.ctid < b.ctid AND a.user_id = b.user_id;
                
                CREATE UNIQUE INDEX IF NOT EXISTS users_user_id_unique ON users (user_id);

                CREATE TABLE IF NOT EXISTS triggers (
                    id SERIAL PRIMARY KEY,
                    phrase TEXT UNIQUE NOT NULL,
                    reply_text TEXT NOT NULL
                );
                
                -- НОВЫЕ ПОЛЯ
                ALTER TABLE users ADD COLUMN IF NOT EXISTS msg_count INTEGER DEFAULT 0;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS notifications_enabled BOOLEAN DEFAULT TRUE;
            """)
        logging.info("✅ Подключение к БД успешно!")
    except Exception as e:
        logging.error(f"❌ Ошибка БД: {e}")

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

# --- ГЕНЕРАТОР ВКЛАДОК МАГАЗИНА ---
def get_shop_keyboard(category="items"):
    builder = InlineKeyboardBuilder()
    
    if category == "items":
        # Кнопки для предметов
        for i in shop_data['items']:
            price = i.get('price', 50)
            builder.button(text=f"📦 {i['name']} ({price} 💰)", callback_data=f"buy_item_{i['id']}_{price}")
        # Кнопка переключения вкладки
        builder.button(text="➡️ Смотреть Титулы", callback_data="shop_tab_titles")
    else:
        # Кнопки для титулов
        for t in shop_data['titles']:
            builder.button(text=f"🏷 {t['name']} ({t['price']} 💰)", callback_data=f"buy_title_{t['id']}_{t['price']}")
        # Кнопка переключения вкладки
        builder.button(text="⬅️ Смотреть Предметы", callback_data="shop_tab_items")
        
    builder.adjust(1) # Все кнопки друг под другом
    return builder.as_markup()

# --- ВХОД В МАГАЗИН ---
@dp.message(Command("shop"))
async def cmd_shop(message: types.Message):
    await refresh_shop_if_needed()
    
    text = "🏪<b>Магазин (обновка каждые 4ч):</b>\n\n<i>Раздел: 🎒 Предметы</i>"
    # При первом входе всегда открываем предметы
    await message.answer(text, reply_markup=get_shop_keyboard("items"), parse_mode="HTML")

# --- ПЕРЕКЛЮЧЕНИЕ ВКЛАДОК ---
@dp.callback_query(F.data.startswith("shop_tab_"))
async def cb_shop_tab(callback: types.CallbackQuery):
    tab = callback.data.split("_")[2] # 'items' или 'titles'
    
    # Заодно проверяем, не истекли ли 4 часа, пока игрок листал вкладки
    await refresh_shop_if_needed() 
    
    section_name = "🎒 Предметы" if tab == "items" else "🏷 Титулы"
    text = f"🏪 <b>Магазин (обновка каждые 4ч):</b>\n\n<i>Раздел: {section_name}</i>"
    
    # Меняем текст и подменяем кнопки (без отправки нового сообщения)
    await callback.message.edit_text(text, reply_markup=get_shop_keyboard(tab), parse_mode="HTML")
    await callback.answer() # Убираем "часики" загрузки на кнопке
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
            
# Обновляем текст в магазине с группировкой сообщений
    current_html = callback.message.html_text or callback.message.text
    user_name = callback.from_user.first_name
    
    # Ищем, покупал ли уже этот юзер что-то (с учетом возможного множителя ×N)
    pattern = rf"<i>{re.escape(user_name)} только что что-то купил(?:\s*×(\d+))?\.\.\.<\/i>"
    match = re.search(pattern, current_html)
    
    if match:
        # Если находим, вытаскиваем цифру, плюсуем 1 и заменяем старую строчку
        count = int(match.group(1)) if match.group(1) else 1
        new_text = re.sub(pattern, f"<i>{user_name} только что что-то купил ×{count + 1}...</i>", current_html)
    else:
        # Если не нашли, просто добавляем новую
        new_text = current_html + f"\n\n<i>{user_name} только что что-то купил...</i>"
        
    await callback.message.edit_text(new_text, reply_markup=callback.message.reply_markup, parse_mode="HTML")
    
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
        if user_data.get('title_id'):
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
    
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""

    # Авто-регистрация в базе
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (user_id, username, credits, xp, role_changes) 
            VALUES ($1, $2, 100, 0, 0) 
            ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
            """,
            user_id, username
        )

    if message.chat.type == "private":
        text = (
            f"👋 <b>Здрасьте, {message.from_user.first_name}!</b>\n\n"
            f"Я Картер, бот-ассистент. Вот с чего тебе стоит начать:\n\n"
            f"🎭 <b>/role</b> — выбрать персонажа для боев\n"
            f"🎁 <b>/daily</b> — забрать ежедневную награду\n"
            f"🏪 <b>/shop</b> — заглянуть в магазин товаров и титулов, там обнова каждые 4 часа\n"
            f"👤 <b>/profile</b> — посмотреть свою статистику\n"
            f"📊 <b>/top</b> — глянуть лидеров чата по разным штукам\n\n"
            f"А в чате ответь командой <code>/duel</code> на сообщение соперника, чтобы вызвать его на бой"
        )
    else:
        text = f" Приветствую, {message.from_user.first_name}! Картер в строю. Если нужна помощь, напиши мне в ЛС команду <code>/start</code>."

    await message.answer(text, parse_mode="HTML")
    
@dp.message(Command("status", "ping"))
async def cmd_status(message: types.Message):
    # Высчитываем аптайм и убираем микросекунды для красоты
    uptime = datetime.now(timezone.utc) - START_TIME
    uptime = uptime - timedelta(microseconds=uptime.microseconds) 
    
    # Пинг высчитываем как разницу между временем отправки сообщения и текущим временем бота
    ping_ms = (datetime.now(timezone.utc) - message.date).total_seconds() * 1000
    
    text = (
        f"🤖 <b>Статус Картера:</b>\n\n"
        f"🟢 <b>Состояние:</b> Онлайн\n"
        f"⏱ <b>Аптайм:</b> {uptime}\n"
        f"🏓 <b>Задержка:</b> ~{int(ping_ms)} мс\n"
        f"🧠 <b>Триггеров в памяти:</b> {len(TRIGGERS_CACHE)} шт.\n"
        f"⚔️ <b>Активных дуэлей:</b> {len(active_duels)}"
    )
    await message.answer(text, parse_mode="HTML")
    
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


# --- СИСТЕМА МОДЕРАЦИИ ---

async def log_mod_action(target_id: int, target_name: str, admin_name: str, action: str, reason: str):
    """Записывает действие в дневник"""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO mod_logs (target_id, target_username, admin_username, action, reason) VALUES ($1, $2, $3, $4, $5)",
            target_id, target_name, admin_name, action, reason
        )

async def get_target_and_args(message: types.Message):
    """
    Универсально достает target_id, target_name и оставшиеся аргументы.
    Исправлен порядок: сначала проверяется @username, а потом Reply.
    """
    args = message.text.split()[1:]
    
    # 1. Если первым аргументом передан @username
    if args and args[0].startswith("@"):
        possible_user = args[0]
        clean_username = possible_user.lstrip("@").lower()
        
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id, username FROM users WHERE LOWER(username) = $1",
                clean_username
            )
        
        if row:
            return row['user_id'], f"@{row['username']}", args[1:]
        else:
            await message.answer(
                f"❌ Пользователь {possible_user} не найден в базе данных бота.\n"
                f"<i>(Чтобы бот его «увидел», он должен написать хотя бы одно сообщение в чат)</i>",
                parse_mode="HTML"
            )
            return None, None, None

    # 2. Если команда отправлена ответом на сообщение (Reply)
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        name = f"@{target.username}" if target.username else target.first_name
        return target.id, name, args

    await message.answer("⚠️ Ответь на сообщение или укажи @username!")
    return None, None, None

@dp.message(Command("warn"))
async def cmd_warn(message: types.Message):
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]: return
    
    target_id, target_name, rem_args = await get_target_and_args(message)
    if not target_id: return

    reason = " ".join(rem_args) if rem_args else "Причина не указана"
    admin_name = message.from_user.username or "Admin"

    async with db_pool.acquire() as conn:
        warns = await conn.fetchval(
            "UPDATE users SET warns = COALESCE(warns, 0) + 1 WHERE user_id = $1 RETURNING warns",
            target_id
        )
    
    if warns is None:
        await message.answer("❌ Пользователя нет в бд.")
        return

    await log_mod_action(target_id, target_name, admin_name, "WARN", reason)

    if warns >= 4:
        # АВТОМУТ НА 2 ДНЯ
        until_date = datetime.now(timezone.utc) + timedelta(days=2)
        try:
            await message.chat.restrict(
                target_id,
                until_date=until_date,
                permissions=types.ChatPermissions(can_send_messages=False)
            )
        except Exception as e:
            logging.error(f"Ошибка применения мута у Телеграма: {e}")
            
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET warns = 0 WHERE user_id = $1", target_id)
            
        await log_mod_action(target_id, target_name, "SYSTEM", "MUTE (2д)", "Достигнут лимит варнов (4/4)")
        await message.answer(f"⛓ <b>{target_name}</b> получил 4-й варн и отправляется в мут на 2 дня! У тебя есть время обдумать свое поведение.😘", parse_mode="HTML")
    else:
        # Теперь бот не молчит при выдаче обычного варна
        await message.answer(f"⚠️ <b>{target_name}</b> получил предупреждение ({warns}/4)!\n📝 Причина: {reason}", parse_mode="HTML")

@dp.message(Command("unwarn"))
async def cmd_unwarn(message: types.Message):
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]: return
    
    target_id, target_name, rem_args = await get_target_and_args(message)
    if not target_id: return

    admin_name = message.from_user.username or "Admin"
    reason = " ".join(rem_args) if rem_args else "Амнистия"
    async with db_pool.acquire() as conn:
        warns = await conn.fetchval(
            "UPDATE users SET warns = GREATEST(COALESCE(warns, 0) - 1, 0) WHERE user_id = $1 RETURNING warns",
            target_id
        )
        
    if warns is None:
        return await message.answer("❌ Пользователя нет в бд.")

    await log_mod_action(target_id, target_name, admin_name, "UNWARN", reason)
    await message.answer(f"🕊 <b>{target_name}</b> прощен админом. Один варн снят!\nТекущие варны: {warns}/4\n📝 Причина: {reason}", parse_mode="HTML")

@dp.message(Command("mute"))
async def cmd_mute(message: types.Message):
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]: return
    
    target_id, target_name, rem_args = await get_target_and_args(message)
    if not target_id: return

    if not rem_args:
        return await message.answer("⚠️ Укажи время! Формат: /mute @user 1ч причина (или ответом: /mute 1ч причина)")

    time_str = rem_args[0]
    reason = " ".join(rem_args[1:]) if len(rem_args) > 1 else "Не указана"
    admin_name = message.from_user.username or "Admin"

    try:
        delta = parse_time(time_str)
        until_date = datetime.now(timezone.utc) + delta
    except ValueError:
        return await message.answer("❌ Кривой формат времени. Используй числа + м,ч,д (10м, 2ч, 1д).")

    try:
        await message.chat.restrict(
            target_id,
            until_date=until_date,
            permissions=types.ChatPermissions(can_send_messages=False)
        )
    except Exception as e:
        return await message.answer(f"❌ Не удалось выдаче мута: {e}")
    
    await log_mod_action(target_id, target_name, admin_name, f"MUTE ({time_str})", reason)
    await message.answer(f"🤐 <b>{target_name}</b> отправлен в мут на {time_str}.\n📝 Причина: {reason}", parse_mode="HTML")

@dp.message(Command("unmute"))
async def cmd_unmute(message: types.Message):
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]: return
    
    target_id, target_name, rem_args = await get_target_and_args(message)
    if not target_id: return

    reason = " ".join(rem_args) if rem_args else "Амнистия"
    admin_name = message.from_user.username or "Admin"

    try:
        await message.chat.restrict(
            target_id,
            permissions=types.ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
    except Exception as e:
        return await message.answer(f"❌ Ошибка размута: {e}")

    await log_mod_action(target_id, target_name, admin_name, "UNMUTE", reason)
    await message.answer(f"🔊 <b>{target_name}</b> снова может говорить!\n📝 Причина: {reason}", parse_mode="HTML")

@dp.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]: return
    
    target_id, target_name, rem_args = await get_target_and_args(message)
    if not target_id: return

    reason = " ".join(rem_args) if rem_args else "Не указана"
    admin_name = message.from_user.username or "Admin"

    try:
        await message.chat.ban(target_id)
    except Exception as e:
        return await message.answer(f"❌ Ошибка бана: {e}")

    await log_mod_action(target_id, target_name, admin_name, "BAN", reason)
    await message.answer(f"🔨 <b>{target_name}</b> забанен админом.\n📝 Причина: {reason}", parse_mode="HTML")

@dp.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]: return
    
    target_id, target_name, rem_args = await get_target_and_args(message)
    if not target_id: return

    reason = " ".join(rem_args) if rem_args else "Амнистия"
    admin_name = message.from_user.username or "Admin"
    try:
        await message.chat.unban(target_id, only_if_banned=True)
    except Exception as e:
        return await message.answer(f"❌ Ошибка разбана: {e}")

    await log_mod_action(target_id, target_name, admin_name, "UNBAN", reason)
    await message.answer(f"🔓 <b>{target_name}</b> разбанен!\n📝 Причина: {reason}", parse_mode="HTML")

@dp.message(Command("diary", "logs"))
async def cmd_diary(message: types.Message):
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]: return
    
    target_id, target_name, _ = await get_target_and_args(message)
    if not target_id: return

    async with db_pool.acquire() as conn:
        logs = await conn.fetch(
            "SELECT action, admin_username, reason, created_at FROM mod_logs WHERE target_id = $1 ORDER BY created_at DESC LIMIT 5",
            target_id
        )
        warns = await conn.fetchval("SELECT warns FROM users WHERE user_id = $1", target_id)

    warns = warns or 0
    text = f"📖 <b>Досье на {target_name}</b>\nТекущие варны: {warns}/4\n\n"

    if not logs:
        text += "<i>Абсолютно чист. Это же ангел во плоти. 👼</i>"
    else:
        for log in logs:
            dt = log['created_at'].strftime("%m-%d %H:%M")
            text += f"[{dt}] <b>{log['action']}</b> от @{log['admin_username']}\n└ <i>{log['reason']}</i>\n\n"

    await message.answer(text, parse_mode="HTML")

@dp.message(Command("addtrigger"))
async def cmd_add_trigger(message: types.Message):
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]:
        return

    raw_text = message.text.replace("/addtrigger", "").strip()
    if "|" not in raw_text:
        await message.answer("⚠️ Использование: <code>/addtrigger ключевое слово | ответ картера</code>", parse_mode="HTML")
        return

    phrase, reply = map(str.strip, raw_text.split("|", 1))
    phrase_clean = phrase.lower()

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO triggers (phrase, reply_text) 
            VALUES ($1, $2) 
            ON CONFLICT (phrase) DO UPDATE SET reply_text = EXCLUDED.reply_text
            """,
            phrase_clean, reply
        )

    TRIGGERS_CACHE[phrase_clean] = reply # Сразу обновляем память
    await message.answer(f"✅ Триггер создан!\n<b>Ключ:</b> <code>{phrase_clean}</code>\n<b>Ответ:</b> {reply}", parse_mode="HTML")

@dp.message(Command("deltrigger"))
async def cmd_del_trigger(message: types.Message):
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]:
        return

    phrase_clean = message.text.replace("/deltrigger", "").strip().lower()
    if not phrase_clean:
        await message.answer("⚠️ Использование: <code>/deltrigger ключевое слово</code>", parse_mode="HTML")
        return

    async with db_pool.acquire() as conn:
        res = await conn.execute("DELETE FROM triggers WHERE phrase = $1", phrase_clean)

    if res == "DELETE 1":
        TRIGGERS_CACHE.pop(phrase_clean, None) # Удаляем из памяти
        await message.answer(f"🗑 Триггер <code>{phrase_clean}</code> удален!", parse_mode="HTML")
    else:
        await message.answer("❌ Такой триггер не найден.")

@dp.message(Command("triggers"))
async def cmd_list_triggers(message: types.Message):
    if not TRIGGERS_CACHE:
        await message.answer("Список триггеров пуст.")
        return

    text = "🗣 <b>Активные триггеры чата:</b>\n\n"
    for phrase, reply in TRIGGERS_CACHE.items():
        text += f"• <code>{phrase}</code> ➔ <i>{reply}</i>\n"

    await message.answer(text, parse_mode="HTML")

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
@dp.message(Command("reroll"))
async def cmd_reroll_shop(message: types.Message):
    # Защита: работает только для админов
    if (message.from_user.username or "").lower() not in [a.lower() for a in ADMIN_USERNAMES]:
        return
        
    global shop_data
    # Откидываем время последнего обновления в самый минимум
    shop_data['last_update'] = datetime.min.replace(tzinfo=timezone.utc)
    
    # Вызываем обычную функцию обновления (она увидит, что время вышло, и сменит товар)
    await refresh_shop_if_needed()
    
    await message.answer("🔄 Витрина Магазина принудительно обновлена! (Админ абьюз).")

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

# --- КАЗИНО И КОСТИ ---

SLOT_SYMBOLS = {
    "7️⃣": {"mult": 50, "weight": 2},
    "💎": {"mult": 15, "weight": 10},
    "💰": {"mult": 7,  "weight": 18},
    "🍒": {"mult": 4,  "weight": 30},
    "🍋": {"mult": 2,  "weight": 40}
}

@dp.message(Command("slots", "casino"))
async def cmd_slots(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()[1:]

    if not args:
        await message.answer("🎰 Использование: <code>/slots [ставка]</code> или <code>/slots вабанк</code>", parse_mode="HTML")
        return

    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", user_id)
        if not user or user['credits'] <= 0:
            await message.answer("❌ У тебя нет кредитов для игры!")
            return

        # Обработка ставки и Вабанка
        if args[0].lower() in ["вабанк", "vabank", "allin", "все"]:
            bet = user['credits']
        else:
            try:
                bet = int(args[0])
                if bet <= 0: raise ValueError
            except ValueError:
                await message.answer("❌ Укажи корректную сумму ставки!")
                return

        if bet > user['credits']:
            await message.answer(f"❌ Не хватает кредитов! Твой баланс: {user['credits']} 💰")
            return

        # Списываем ставку перед круткой
        await conn.execute("UPDATE users SET credits = credits - $1 WHERE user_id = $2", bet, user_id)

    # 1. Отправляем анимацию ожидания
    anim_msg = await message.answer("🎰 <b>Крутим барабаны...</b>\n\n[ ⏳ | ⏳ | ⏳ ]", parse_mode="HTML")
    await asyncio.sleep(1.5)

    # 2. Логика генерации комбинации
    roll_type = random.choices(["3inRow", "2inRow", "0inRow"], weights=[7, 23, 70])[0]

    symbols_list = list(SLOT_SYMBOLS.keys())
    weights_list = [SLOT_SYMBOLS[s]["weight"] for s in symbols_list]

    if roll_type == "3inRow":
        chosen_symbol = random.choices(symbols_list, weights=weights_list)[0]
        reels = [chosen_symbol, chosen_symbol, chosen_symbol]
        multiplier = SLOT_SYMBOLS[chosen_symbol]["mult"]
    elif roll_type == "2inRow":
        pair_symbol = random.choice(symbols_list)
        other_symbol = random.choice([s for s in symbols_list if s != pair_symbol])
        reels = [pair_symbol, pair_symbol, other_symbol]
        random.shuffle(reels)
        multiplier = 1  # Возврат ставки
    else:
        reels = random.sample(symbols_list, 3) # Все 3 разные
        multiplier = 0

    payout = int(bet * multiplier)

    # 3. Начисление выигрыша и формирование результата
    async with db_pool.acquire() as conn:
        if payout > 0:
            await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", payout, user_id)
        new_balance = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", user_id)

    reels_str = f"[ {reels[0]} | {reels[1]} | {reels[2]} ]"

    if multiplier > 1:
        res_text = f"🎉 <b>ЙООО, ДЖЕКПОТТТТ</b> Три в ряд!\nВыигрыш: <b>+{payout} 💰</b> (x{multiplier})"
    elif multiplier == 1:
        res_text = f"♻️ <b>Две одинаковые!</b> Возврат ставки: <b>+{payout} 💰</b>"
    else:
        res_text = f"💀 <b>ХАХА, МИМО!</b> Потеряно: <b>-{bet} 💰</b>"

    final_text = (
        f"🎰 <b>СЛОТЫ</b> | Игрок: {message.from_user.first_name}\n\n"
        f"<b>{reels_str}</b>\n\n"
        f"{res_text}\n"
        f"💳 Баланс: <b>{new_balance} 💰</b>"
    )

    await anim_msg.edit_text(final_text, parse_mode="HTML")


# --- ПВП КУБИКИ (PVP DICE) ---

@dp.message(Command("dice"))
async def cmd_dice(message: types.Message):
    user_id = message.from_user.id
    
    if not message.reply_to_message or message.reply_to_message.from_user.is_bot:
        await message.answer("⚠️ Чтобы сыграть в кубики, ответь командой <code>/dice [ставка|вабанк]</code> на сообщение соперника!", parse_mode="HTML")
        return

    target = message.reply_to_message.from_user
    if target.id == user_id:
        await message.answer("Нельзя играть в кубики с самим собой!")
        return
    args = message.text.split()[1:]
    if not args:
        await message.answer("⚠️ Укажи сумму ставки или <code>вабанк</code>!", parse_mode="HTML")
        return

    async with db_pool.acquire() as conn:
        p1 = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", user_id)
        p2 = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", target.id)

        if not p1 or not p2:
            await message.answer("❌ Один из участников не найден в бд!")
            return

        # Расчет ставки для ПВП
        if args[0].lower() in ["вабанк", "vabank", "allin", "все"]:
            bet = min(p1['credits'], p2['credits']) # Вабанк ограничем меньшим балансом
        else:
            try:
                bet = int(args[0])
                if bet <= 0: raise ValueError
            except ValueError:
                await message.answer("❌ Некорректная ставка!")
                return

        if p1['credits'] < bet:
            await message.answer("❌ У тебя недостаточно средств для такой ставки!")
            return
        if p2['credits'] < bet:
            await message.answer(f"❌ У @{target.username or target.first_name} недостаточно средств!")
            return

    # Создаем кнопку вызова
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🎲 Принять дуэль ({bet} 💰)", callback_data=f"dice_accept_{user_id}_{target.id}_{bet}")
    builder.button(text="🤡 Струсить", callback_data=f"duel_decline_{target.id}")
    builder.adjust(1)

    await message.answer(
        f"🎲 <b>БРОСОК КОСТЕЙ!</b>\n\n"
        f"{message.from_user.first_name} вызывает <b>{target.first_name}</b> на дуэль на кубиках!\n"
        f"💰 Ставка: <b>{bet} 💰</b> с каждого.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("dice_accept_"))
async def cb_dice_accept(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    p1_id, p2_id, bet = int(parts[2]), int(parts[3]), int(parts[4])

    if callback.from_user.id != p2_id:
        await callback.answer("Это вызов не для тебя!", show_alert=True)
        return

    async with db_pool.acquire() as conn:
        # Повторная проверка балансов
        c1 = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", p1_id)
        c2 = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", p2_id)

        if c1 < bet or c2 < bet:
            await callback.message.edit_text("❌ У одного из игроков изменился баланс. Игра отменена.")
            return

        # Списываем банк
        await conn.execute("UPDATE users SET credits = credits - $1 WHERE user_id = $2", bet, p1_id)
        await conn.execute("UPDATE users SET credits = credits - $1 WHERE user_id = $2", bet, p2_id)

    # Удаляем сообщение с кнопкой, чтобы чат не засорялся
    await callback.message.delete()

    p1_user = await get_user(p1_id)
    p2_user = await get_user(p2_id)
    name1 = p1_user['username'] or "Игрок 1"
    name2 = p2_user['username'] or "Игрок 2"

    # --- КИДАЕМ АНИМИРОВАННЫЕ КУБИКИ TELEGRAM ---
    
    await callback.message.answer(f"👤 <b>{name1}</b> бросает кубик...", parse_mode="HTML")
    dice1 = await callback.message.answer_dice(emoji="🎲")
    await asyncio.sleep(3.5) # Ждем, пока проиграется анимация

    await callback.message.answer(f"👤 <b>{name2}</b> бросает кубик...", parse_mode="HTML")
    dice2 = await callback.message.answer_dice(emoji="🎲")
    await asyncio.sleep(3.5) # Ждем, пока проиграется анимация

    # Telegram сам генерирует результат внутри объекта dice
    r1 = dice1.dice.value
    r2 = dice2.dice.value

    # --- ПОДВОДИМ ИТОГИ ---
    
    text = f"📊 <b>ИТОГИ ДУЭЛИ:</b>\n\n"

    async with db_pool.acquire() as conn:
        if r1 > r2:
            win_pot = bet * 2
            await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", win_pot, p1_id)
            text += f"🏆 Победитель: <b>{name1}</b>! Забирает банк <b>+{win_pot} 💰</b>"
        elif r2 > r1:
            win_pot = bet * 2
            await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", win_pot, p2_id)
            text += f"🏆 Победитель: <b>{name2}</b>! Забирает банк <b>+{win_pot} 💰</b>"
        else:
            # Ничья — возврат
            await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", bet, p1_id)
            await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", bet, p2_id)
            text += f"🤝 <b>Ничья!</b> Ставки возвращены игрокам."

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

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
    ADMIN_ID = 7857165309
    
    if role_id == 999:
        if user_id != ADMIN_ID:
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
                dmg = max(0, attacker['atk'] + random.randint(-1, 1))
                
                if attacker['type'] == 'enrage' and attacker['hp'] <= (attacker['max_hp'] / 3):
                    dmg += 12
                    log_msg = f"💢 V2 В ЯРОСТИ! "
                
                miss_chance = 0.20 if attacker['type'] == 'berserk' else 0.0
                if attacker['blind']: miss_chance += 0.25
                
                if random.random() < miss_chance:
                    dmg = 0
                    log_msg = f"💨 {attacker['name']} промахивается по противнику!"
                elif (defender['type'] == 'karma' and random.random() < 0.45) or (defender['niko_dodge'] and random.random() < 0.60):
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
                        dmg = int(dmg * 0.6)
                        log_msg = f"🛡 {defender['name']} блокирует часть урона!\n"
                    
                    defender['hp'] -= dmg
                    log_msg += f"🗡 {attacker['name']} наносит {dmg} урона!"
                    
                    if attacker['type'] == 'karma':
                        karma_dmg = max(1, int(defender['max_hp'] * random.uniform(0.01, 0.05)))
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
            
            if r_type == "god": 
                attacker['cd'] = 1
                dmg = int(defender['max_hp'] * 0.99)
                defender['hp'] -= dmg
                log_msg = f"🤧 <b>{attacker['name']}</b> чихнул и стер <b>{defender['name']}</b> в пыль на {dmg} урона!"
            elif r_type == "berserk":
                attacker['cd'] = 3
                if random.random() < 0.35:
                    log_msg = f"💥 {attacker['name']} кричит «JUDGMENT!», но промахивается!"
                else:
                    defender['hp'] -= 40
                    log_msg = f"⚖️ {attacker['name']} обрушивает «JUDGMENT!» Нанесено 40 урона!"
            elif r_type == "enrage": 
                attacker['cd'] = 3
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
    base_url = os.environ.get("RENDER_EXTERNAL_URL")
    if base_url:
        await bot.set_webhook(f"{base_url}{WEBHOOK_PATH}", drop_pending_updates=True)

def main():
    dp.startup.register(on_startup)
    dp.message.middleware(AntiTheftMiddleware())
    app = web.Application()
    app.router.add_get('/', health_check)
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

main()