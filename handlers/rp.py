"""Roleplay actions system."""

from html import escape

from aiogram import types, F
from aiogram.filters import Command


# RP команды: действие -> (глагол в прошедшем времени, смайлик)
RP_ACTIONS = {
    "обнять": ("обнял", "🫂"),
    "поцеловать": ("поцеловал", "💋"),
    "ударить": ("ударил", "👊"),
    "пнуть": ("пнул", "🦵"),
    "погладить": ("погладил", "🤚"),
    "щипнуть": ("больно щипнул", "🤏"),
    "подразнить": ("подразнил", "😝"),
    "пожать руку": ("пожал руку", "🤝"),
    "высмеять": ("насмехается над", "😂"),
}


def register_rp_handlers(dp, *, db_pool_getter=None, **kwargs):
    """Регистрирует обработчики RP команд."""
    
    @dp.message(Command("rp_list", "rp"))
    async def cmd_rp_list(message: types.Message):
        """Показывает список доступных RP действий."""
        actions_list = "\n".join([f"  • <code>{action}</code> — {verb[1]} {verb[0]}" for action, verb in RP_ACTIONS.items()])
        
        text = (
            "<b>🎭 ДОСТУПНЫЕ RP ДЕЙСТВИЯ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{actions_list}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>📝 КАК ИСПОЛЬЗОВАТЬ:</b>\n\n"
            "1️⃣ <b>с упоминанием:</b>\n"
            "   <code>обнять @username</code>\n\n"
            "2️⃣ <b>реплай на сообщение:</b>\n"
            "   ответь на сообщение словом <code>обнять</code>"
        )
        
        await message.answer(text, parse_mode="HTML")
    
    @dp.message(F.text)
    async def handle_rp_action(message: types.Message):
        """Обработчик RP действий через reply или упоминание."""
        
        # Игнорируем команды (они начинаются с /)
        if message.text.startswith("/"):
            return
        
        # Парсим текст
        text = message.text.strip()
        if not text:
            return
        
        # Ищем, может ли это быть RP командой
        action_name = text.split()[0].lower()
        
        # Проверяем, есть ли такая команда
        if action_name not in RP_ACTIONS:
            return
        
        action_verb, emoji = RP_ACTIONS[action_name]
        author_name = escape(message.from_user.first_name)
        author_id = message.from_user.id
        
        # Случай 1: ответ на чье-то сообщение
        if message.reply_to_message:
            if message.reply_to_message.from_user.is_bot:
                return
            
            target_name = escape(message.reply_to_message.from_user.first_name)
            target_id = message.reply_to_message.from_user.id
            
            # Формируем HTML с кликабельными ссылками
            response = (
                f"{emoji} <a href=\"tg://user?id={author_id}\">{author_name}</a> "
                f"{action_verb} "
                f"<a href=\"tg://user?id={target_id}\">{target_name}</a>"
            )
            await message.reply(response, parse_mode="HTML")
            return
        
        # Случай 2: упоминание в тексте
        parts = text.split()
        if len(parts) < 2:
            return
        
        target_mention_input = parts[1]
        
        # Проверяем, что это похоже на username (содержит @ или буквы)
        if not (target_mention_input.startswith("@") or target_mention_input[0].isalnum()):
            return
        
        target_username = target_mention_input.lstrip("@").lower()
        target_name = None
        target_id = None
        
        # Ищем пользователя в БД по username
        if db_pool_getter:
            try:
                db_pool = db_pool_getter()
                async with db_pool.acquire() as conn:
                    # Сначала ищем с точным совпадением (username уже должен быть в нижнем регистре)
                    user = await conn.fetchrow(
                        "SELECT user_id, first_name, username FROM users WHERE username = $1 AND username IS NOT NULL AND username != ''",
                        target_username
                    )
                    
                    # Если не нашли, ищем игнорируя регистр
                    if not user:
                        user = await conn.fetchrow(
                            "SELECT user_id, first_name, username FROM users WHERE LOWER(COALESCE(username, '')) = $1 AND username IS NOT NULL AND username != ''",
                            target_username
                        )
                    
                    if user:
                        target_id = user['user_id']
                        target_name = escape(user['first_name'] or user['username'] or target_username)
            except Exception as e:
                # Логируем ошибку но не прерываем выполнение
                pass
        
        # Если не нашли в БД, используем переданное имя
        if not target_name:
            target_name = target_username
        
        # Формируем ответ
        if target_id:
            # Если нашли в БД, делаем обе ссылки кликабельными
            response = (
                f"{emoji} <a href=\"tg://user?id={author_id}\">{author_name}</a> "
                f"{action_verb} "
                f"<a href=\"tg://user?id={target_id}\">{target_name}</a>"
            )
        else:
            # Если не нашли, показываем просто имя с болдом
            response = (
                f"{emoji} <a href=\"tg://user?id={author_id}\">{author_name}</a> "
                f"{action_verb} "
                f"<b>@{target_name}</b>"
            )
        
        await message.answer(response, parse_mode="HTML")


