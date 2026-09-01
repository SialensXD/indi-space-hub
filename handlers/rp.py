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


def register_rp_handlers(dp, **kwargs):
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
        
        # Если это username, показываем его как есть
        # (без кликабельной ссылки, так как не знаем ID)
        target_display = target_mention_input.lstrip("@")
        
        response = (
            f"{emoji} <a href=\"tg://user?id={author_id}\">{author_name}</a> "
            f"{action_verb} "
            f"<b>@{target_display}</b>"
        )
        await message.answer(response, parse_mode="HTML")


