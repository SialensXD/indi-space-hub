"""Roleplay actions system."""

from html import escape

from aiogram import types, F
from aiogram.filters import Command


# RP команды: действие -> глагол в прошедшем времени
RP_ACTIONS = {
    "обнять": "обнял",
    "поцеловать": "поцеловал",
    "ударить": "ударил",
    "пнуть": "пнул",
    "погладить": "погладил",
    "щипнуть": "щипнул",
    "подразнить": "подразнил",
    "помочь": "помог",
    "пожать руку": "пожал руку",
    "высмеять": "высмеял",
}


def register_rp_handlers(dp, **kwargs):
    """Регистрирует обработчики RP команд."""
    
    @dp.message(Command("rp_list", "rp"))
    async def cmd_rp_list(message: types.Message):
        """Показывает список доступных RP действий."""
        actions_list = "\n".join([f"  • <code>{action}</code> — {verb}" for action, verb in RP_ACTIONS.items()])
        
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
        
        action_verb = RP_ACTIONS[action_name]
        author_name = escape(message.from_user.first_name)
        author_mention = f"@{message.from_user.username}" if message.from_user.username else f"#{message.from_user.id}"
        
        # Случай 1: ответ на чье-то сообщение
        if message.reply_to_message:
            if message.reply_to_message.from_user.is_bot:
                return
            
            target_name = escape(message.reply_to_message.from_user.first_name)
            target_mention = f"@{message.reply_to_message.from_user.username}" if message.reply_to_message.from_user.username else f"#{message.reply_to_message.from_user.id}"
            
            response = f"{author_mention} {action_verb} {target_mention}"
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
        
        response = f"{author_mention} {action_verb} {target_mention_input}"
        await message.answer(response, parse_mode="HTML")

