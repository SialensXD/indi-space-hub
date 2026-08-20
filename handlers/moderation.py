"""Moderation commands and callbacks."""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone, timedelta

from aiogram import types
from aiogram.filters import Command


def register_moderation_handlers(
    dp,
    *,
    db_pool_getter: Callable,
    bot,
    admin_usernames,
    shop_data: dict,
    refresh_shop_if_needed: Callable,
    trigger_cache: dict,
    parse_time: Callable,
):
    async def log_mod_action(target_id: int, target_name: str, admin_name: str, action: str, reason: str):
        """Записывает действие в дневник"""
        async with db_pool_getter().acquire() as conn:
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

            async with db_pool_getter().acquire() as conn:
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

    def is_admin(message: types.Message):
        return (message.from_user.username or "").lower() in [a.lower() for a in admin_usernames]

    @dp.message(Command("warn"))
    async def cmd_warn(message: types.Message):
        if not is_admin(message): return

        target_id, target_name, rem_args = await get_target_and_args(message)
        if not target_id: return

        reason = " ".join(rem_args) if rem_args else "Причина не указана"
        admin_name = message.from_user.username or "Admin"

        async with db_pool_getter().acquire() as conn:
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

            async with db_pool_getter().acquire() as conn:
                await conn.execute("UPDATE users SET warns = 0 WHERE user_id = $1", target_id)

            await log_mod_action(target_id, target_name, "SYSTEM", "MUTE (2д)", "Достигнут лимит варнов (4/4)")
            await message.answer(f"⛓ <b>{target_name}</b> получил 4-й варн и отправляется в мут на 2 дня! У тебя есть время обдумать свое поведение.😘", parse_mode="HTML")
        else:
            # Теперь бот не молчит при выдаче обычного варна
            await message.answer(f"⚠️ <b>{target_name}</b> получил предупреждение ({warns}/4)!\n📝 Причина: {reason}", parse_mode="HTML")

    @dp.message(Command("unwarn"))
    async def cmd_unwarn(message: types.Message):
        if not is_admin(message): return

        target_id, target_name, rem_args = await get_target_and_args(message)
        if not target_id: return

        admin_name = message.from_user.username or "Admin"
        reason = " ".join(rem_args) if rem_args else "Амнистия"
        async with db_pool_getter().acquire() as conn:
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
        if not is_admin(message): return

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
        if not is_admin(message): return

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
        if not is_admin(message): return

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
        if not is_admin(message): return

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
        if not is_admin(message): return

        target_id, target_name, _ = await get_target_and_args(message)
        if not target_id: return

        async with db_pool_getter().acquire() as conn:
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
        if not is_admin(message):
            return

        raw_text = message.text.replace("/addtrigger", "").strip()
        if "|" not in raw_text:
            await message.answer("⚠️ Использование: <code>/addtrigger ключевое слово | ответ картера</code>", parse_mode="HTML")
            return

        phrase, reply = map(str.strip, raw_text.split("|", 1))
        phrase_clean = phrase.lower()

        async with db_pool_getter().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO triggers (phrase, reply_text)
                VALUES ($1, $2)
                ON CONFLICT (phrase) DO UPDATE SET reply_text = EXCLUDED.reply_text
                """,
                phrase_clean, reply
            )

        trigger_cache[phrase_clean] = reply # Сразу обновляем память
        await message.answer(f"✅ Триггер создан!\n<b>Ключ:</b> <code>{phrase_clean}</code>\n<b>Ответ:</b> {reply}", parse_mode="HTML")

    @dp.message(Command("deltrigger"))
    async def cmd_del_trigger(message: types.Message):
        if not is_admin(message):
            return

        phrase_clean = message.text.replace("/deltrigger", "").strip().lower()
        if not phrase_clean:
            await message.answer("⚠️ Использование: <code>/deltrigger ключевое слово</code>", parse_mode="HTML")
            return

        async with db_pool_getter().acquire() as conn:
            res = await conn.execute("DELETE FROM triggers WHERE phrase = $1", phrase_clean)

        if res == "DELETE 1":
            trigger_cache.pop(phrase_clean, None) # Удаляем из памяти
            await message.answer(f"🗑 Триггер <code>{phrase_clean}</code> удален!", parse_mode="HTML")
        else:
            await message.answer("❌ Такой триггер не найден.")

    @dp.message(Command("triggers"))
    async def cmd_list_triggers(message: types.Message):
        if not trigger_cache:
            await message.answer("Список триггеров пуст.")
            return

        text = "🗣 <b>Активные триггеры чата:</b>\n\n"
        for phrase, reply in trigger_cache.items():
            text += f"• <code>{phrase}</code> ➔ <i>{reply}</i>\n"

        await message.answer(text, parse_mode="HTML")

    @dp.message(Command("reset"))
    async def cmd_reset(message: types.Message):
        if not is_admin(message):
            return
        args = message.text.split()
        if len(args) != 2:
            await message.answer("⚠️ Использование: /reset @username", parse_mode="Markdown")
            return
        target = args[1].replace("@", "")
        async with db_pool_getter().acquire() as conn:
            res = await conn.execute("UPDATE users SET role_changes = 0 WHERE username = $1", target)
        await message.answer(f"✅ Лимит для @{target} сброшен!" if res == "UPDATE 1" else "❌ Пользователь не найден.")

    @dp.message(Command("send"))
    async def cmd_broadcast(message: types.Message):
        if not is_admin(message):
            return
        text = message.text.replace("/send", "").strip()
        if not text:
            await message.answer("⚠️ Использование: /send Текст", parse_mode="Markdown")
            return
        async with db_pool_getter().acquire() as conn:
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

    @dp.message(Command("reroll"))
    async def cmd_reroll_shop(message: types.Message):
        # Защита: работает только для админов
        if not is_admin(message):
            return

        # Откидываем время последнего обновления в самый минимум
        shop_data['last_update'] = datetime.min.replace(tzinfo=timezone.utc)

        # Вызываем обычную функцию обновления (она увидит, что время вышло, и сменит товар)
        await refresh_shop_if_needed()

        await message.answer("🔄 Витрина Магазина принудительно обновлена! (Админ абьюз).")
