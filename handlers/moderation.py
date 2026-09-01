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
    get_admin_level: Callable,
    shop_data: dict,
    refresh_shop_if_needed: Callable,
    trigger_cache: dict,
    parse_time: Callable,
    owner_user_id: int,
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
                    f"❌ {possible_user} не найден в бд.\n"
                    f"<i>(Чтобы картер его «увидел», он должен написать хотя бы одно сообщение в чат)</i>",
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

    async def check_admin_level(message: types.Message, required_level: int) -> bool:
        """Проверяет, что уровень админа соответствует требуемому."""
        admin_level = await get_admin_level(message.from_user.id)
        if admin_level < required_level:
            level_names = {1: "младший", 2: "средний", 3: "старший", 4: "владелец"}
            level_name = level_names.get(required_level, "админ")
            await message.answer(
                f"❌ <b>ДОСТУП ЗАПРЕЩЕН!</b>\n"
                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                f"Эта команда доступна только для\n"
                f"<b>{level_name} админов</b> и выше!",
                parse_mode="HTML"
            )
            return False
        return True

    @dp.message(Command("warn"))
    async def cmd_warn(message: types.Message):
        if not await check_admin_level(message, 1): return

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
            await message.answer(
                f"⛓ <b>АВТОМАТИЧЕСКИЙ МУТ!</b>\n"
                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                f"🚨 <b>{target_name}</b> получил 4-й варн\n\n"
                f"⏱  <b>Длительность:</b> 2 дня\n\n"
                f"📝 <b>Причина:</b> Превышен лимит предупреждений (4/4)\n\n"
                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                f"<i>У игрока есть время на размышление...</i>",
                parse_mode="HTML"
            )
        else:
            # Теперь бот не молчит при выдаче обычного варна
            await message.answer(
                f"⚠️ <b>ВАРН ВЫДАН!</b>\n"
                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                f"👤 <b>{target_name}</b>\n"
                f"⚠️  <b>Варны:</b> {warns}/4\n\n"
                f"📝 <b>Причина:</b> {reason}",
                parse_mode="HTML"
            )

    @dp.message(Command("unwarn"))
    async def cmd_unwarn(message: types.Message):
        if not await check_admin_level(message, 1): return

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
        await message.answer(
            f"🕊 <b>ВАРН СНЯТ!</b>\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"👤 <b>{target_name}</b> прощен!\n\n"
            f"⚠️  <b>Текущие варны:</b> {warns}/4\n\n"
            f"📝 <b>Причина:</b> {reason}",
            parse_mode="HTML"
        )

    @dp.message(Command("mute"))
    async def cmd_mute(message: types.Message):
        if not await check_admin_level(message, 2): return

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
            return await message.answer(
                f"❌ <b>ОШИБКА!</b>\n"
                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                f"Не удалось применить мут: {e}",
                parse_mode="HTML"
            )

        await log_mod_action(target_id, target_name, admin_name, f"MUTE ({time_str})", reason)
        await message.answer(
            f"🤐 <b>МУТ ВЫДАН!</b>\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"👤 <b>{target_name}</b> отправлен в мут\n\n"
            f"⏱  <b>Длительность:</b> {time_str}\n\n"
            f"📝 <b>Причина:</b> {reason}",
            parse_mode="HTML"
        )

        # Дополнительное логирование в модлог
        await log_mod_action(
            target_id=message.from_user.id,
            target_name=message.from_user.username or "Admin",
            admin_name=admin_name,
            action=f"MUTE_CMD ({time_str})",
            reason=f"Мут пользователя {target_name}: {reason}"
        )

    @dp.message(Command("unmute"))
    async def cmd_unmute(message: types.Message):
        if not await check_admin_level(message, 2): return

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
            return await message.answer(
                f"❌ <b>ОШИБКА!</b>\n"
                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                f"Ошибка размута: {e}",
                parse_mode="HTML"
            )

        await log_mod_action(target_id, target_name, admin_name, "UNMUTE", reason)
        await message.answer(
            f"🔊 <b>МУТ СНЯТ!</b>\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"👤 <b>{target_name}</b> снова может говорить!\n\n"
            f"📝 <b>Причина:</b> {reason}",
            parse_mode="HTML"
        )

        # Дополнительное логирование в модлог
        await log_mod_action(
            target_id=message.from_user.id,
            target_name=message.from_user.username or "Admin",
            admin_name=admin_name,
            action="UNMUTE_CMD",
            reason=f"Размут пользователя {target_name}: {reason}"
        )

    @dp.message(Command("ban"))
    async def cmd_ban(message: types.Message):
        if not await check_admin_level(message, 3): return

        target_id, target_name, rem_args = await get_target_and_args(message)
        if not target_id: return

        reason = " ".join(rem_args) if rem_args else "Не указана"
        admin_name = message.from_user.username or "Admin"

        try:
            await message.chat.ban(target_id)
        except Exception as e:
            return await message.answer(
                f"❌ <b>ОШИБКА!</b>\n"
                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                f"Ошибка бана: {e}",
                parse_mode="HTML"
            )

        await log_mod_action(target_id, target_name, admin_name, "BAN", reason)
        await message.answer(
            f"🔨 <b>БАН ВЫДАН!</b>\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"👤 <b>{target_name}</b> забанен из чата\n\n"
            f"📝 <b>Причина:</b> {reason}",
            parse_mode="HTML"
        )

        # Дополнительное логирование в модлог
        await log_mod_action(
            target_id=message.from_user.id,
            target_name=message.from_user.username or "Admin",
            admin_name=admin_name,
            action="BAN_CMD",
            reason=f"Бан пользователя {target_name}: {reason}"
        )

    @dp.message(Command("unban"))
    async def cmd_unban(message: types.Message):
        if not await check_admin_level(message, 3): return

        target_id, target_name, rem_args = await get_target_and_args(message)
        if not target_id: return

        reason = " ".join(rem_args) if rem_args else "Амнистия"
        admin_name = message.from_user.username or "Admin"
        try:
            await message.chat.unban(target_id, only_if_banned=True)
        except Exception as e:
            return await message.answer(
                f"❌ <b>ОШИБКА!</b>\n"
                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                f"Ошибка разбана: {e}",
                parse_mode="HTML"
            )

        await log_mod_action(target_id, target_name, admin_name, "UNBAN", reason)
        await message.answer(
            f"🔓 <b>БАН СНЯТ!</b>\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"👤 <b>{target_name}</b> разбанен!\n\n"
            f"📝 <b>Причина:</b> {reason}",
            parse_mode="HTML"
        )

        # Дополнительное логирование в модлог
        await log_mod_action(
            target_id=message.from_user.id,
            target_name=message.from_user.username or "Admin",
            admin_name=admin_name,
            action="UNBAN_CMD",
            reason=f"Разбан пользователя {target_name}: {reason}"
        )

    @dp.message(Command("diary", "logs"))
    async def cmd_diary(message: types.Message):
        if not await check_admin_level(message, 3): return

        target_id, target_name, _ = await get_target_and_args(message)
        if not target_id: return

        async with db_pool_getter().acquire() as conn:
            logs = await conn.fetch(
                "SELECT action, admin_username, reason, created_at FROM mod_logs WHERE target_id = $1 ORDER BY created_at DESC LIMIT 5",
                target_id
            )
            warns = await conn.fetchval("SELECT warns FROM users WHERE user_id = $1", target_id)

        warns = warns or 0
        text = (
            f"📖 <b>ДОСЬЕ НА {target_name.upper()}</b>\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"⚠️  <b>Текущие варны:</b> {warns}/4\n\n"
        )

        if not logs:
            text += "<i>Абсолютно чист. Неужто ангел?</i>\n\n"
        else:
            text += "<b>Последние действия:</b>\n\n"
            for log in logs:
                dt = log['created_at'].strftime("%d.%m %H:%M")
                text += f"[{dt}] <b>{log['action']}</b>\n"
                text += f"  👤 От: @{log['admin_username']}\n"
                text += f"  📝 {log['reason']}\n\n"

        text += f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        await message.answer(text, parse_mode="HTML")

    @dp.message(Command("addtrigger"))
    async def cmd_add_trigger(message: types.Message):
        if not await check_admin_level(message, 3):
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

            # Логируем действие
            await log_mod_action(
                target_id=message.from_user.id,
                target_name=message.from_user.username or "Admin",
                admin_name=message.from_user.username or "Admin",
                action="ADD_TRIGGER",
                reason=f"Триггер: {phrase_clean}"
            )

        trigger_cache[phrase_clean] = reply # Сразу обновляем память
        await message.answer(f"✅ Триггер создан!\n<b>Ключ:</b> <code>{phrase_clean}</code>\n<b>Ответ:</b> {reply}", parse_mode="HTML")

    @dp.message(Command("deltrigger"))
    async def cmd_del_trigger(message: types.Message):
        if not await check_admin_level(message, 3):
            return

        phrase_clean = message.text.replace("/deltrigger", "").strip().lower()
        if not phrase_clean:
            await message.answer("⚠️ Использование: <code>/deltrigger ключевое слово</code>", parse_mode="HTML")
            return

        async with db_pool_getter().acquire() as conn:
            res = await conn.execute("DELETE FROM triggers WHERE phrase = $1", phrase_clean)

            # Логируем действие
            if res == "DELETE 1":
                await log_mod_action(
                    target_id=message.from_user.id,
                    target_name=message.from_user.username or "Admin",
                    admin_name=message.from_user.username or "Admin",
                    action="DEL_TRIGGER",
                    reason=f"Триггер: {phrase_clean}"
                )

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
        if not await check_admin_level(message, 4):
            return
        args = message.text.split()
        if len(args) != 2:
            await message.answer("⚠️ Использование: /reset @username", parse_mode="Markdown")
            return
        target = args[1].replace("@", "")
        async with db_pool_getter().acquire() as conn:
            res = await conn.execute("UPDATE users SET role_changes = 0 WHERE username = $1", target)

            # Логируем действие
            if res == "UPDATE 1":
                await log_mod_action(
                    target_id=message.from_user.id,
                    target_name=message.from_user.username or "Admin",
                    admin_name=message.from_user.username or "Admin",
                    action="RESET_ROLE_CHANGES",
                    reason=f"Сброс лимита смен ролей для @{target}"
                )

        await message.answer(f"✅ Лимит для @{target} сброшен!" if res == "UPDATE 1" else "❌ Пользователь не найден.")

    @dp.message(Command("send"))
    async def cmd_broadcast(message: types.Message):
        if not await check_admin_level(message, 4):
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
        # Защита: работает только для владельца
        if not await check_admin_level(message, 4):
            return

        # Откидываем время последнего обновления в самый минимум
        shop_data['last_update'] = datetime.min.replace(tzinfo=timezone.utc)

        # Вызываем обычную функцию обновления (она увидит, что время вышло, и сменит товар)
        await refresh_shop_if_needed()

        # Логируем действие
        await log_mod_action(
            target_id=message.from_user.id,
            target_name=message.from_user.username or "Admin",
            admin_name=message.from_user.username or "Admin",
            action="REROLL_SHOP",
            reason="Принудительное обновление магазина"
        )

        await message.answer("🔄 Витрина Магазина принудительно обновлена! (Админ абьюз).")

    # --- Команды управления админами ---

    @dp.message(Command("addadmin"))
    async def cmd_add_admin(message: types.Message):
        if not await check_admin_level(message, 4):
            return

        args = message.text.split()[1:]
        if len(args) < 2:
            await message.answer(
                "⚠️ Использование: <code>/addadmin @username [1-3]</code>\n"
                "1 = младший админ (варны)\n"
                "2 = средний админ (+ муты)\n"
                "3 = старший админ (+ баны, триггеры)",
                parse_mode="HTML"
            )
            return

        username = args[0].lstrip("@").lower()
        try:
            level = int(args[1])
            if level not in [1, 2, 3]:
                await message.answer("❌ Уровень должен быть 1, 2 или 3!")
                return
        except ValueError:
            await message.answer("❌ Уровень должен быть числом (1, 2 или 3)!")
            return

        async with db_pool_getter().acquire() as conn:
            # Проверяем существование пользователя
            user = await conn.fetchrow(
                "SELECT user_id, username FROM users WHERE LOWER(username) = $1",
                username
            )
            if not user:
                await message.answer(f"❌ Пользователь @{username} не найден в бд!")
                return

            user_id = user['user_id']
            real_username = user['username'] or username

            # Проверяем, не является ли он владельцем
            if user_id == owner_user_id:
                await message.answer("❌ Он уже владелец!")
                return

            # Проверяем, не является ли он уже админом
            existing_level = await conn.fetchval(
                "SELECT level FROM admin_levels WHERE user_id = $1",
                user_id
            )
            if existing_level:
                await message.answer(
                    f"❌ @{real_username} уже админ уровня {existing_level}! "
                    f"Сначала используй /removeadmin."
                )
                return

            # Добавляем админа
            await conn.execute(
                """
                INSERT INTO admin_levels (user_id, level, username, promoted_by, promoted_at)
                VALUES ($1, $2, $3, $4, NOW())
                """,
                user_id, level, real_username, message.from_user.id
            )

            # Обновляем admin_level в users
            await conn.execute(
                "UPDATE users SET admin_level = $1 WHERE user_id = $2",
                level, user_id
            )

        level_names = {1: "младший", 2: "средний", 3: "старший"}
        await message.answer(
            f"✅ @{real_username} назначен как {level_names[level]} админ!",
            parse_mode="HTML"
        )

        # Логируем действие
        await log_mod_action(
            target_id=message.from_user.id,
            target_name=message.from_user.username or "Admin",
            admin_name=message.from_user.username or "Admin",
            action=f"ADD_ADMIN_LEVEL_{level}",
            reason=f"Назначен админом уровня {level} для @{real_username}"
        )

    @dp.message(Command("removeadmin"))
    async def cmd_remove_admin(message: types.Message):
        if not await check_admin_level(message, 4):
            return

        args = message.text.split()[1:]
        if not args:
            await message.answer("⚠️ Использование: <code>/removeadmin @username</code>", parse_mode="HTML")
            return

        username = args[0].lstrip("@").lower()

        async with db_pool_getter().acquire() as conn:
            # Проверяем существование пользователя
            user = await conn.fetchrow(
                "SELECT user_id, username, admin_level FROM users WHERE LOWER(username) = $1",
                username
            )
            if not user:
                await message.answer(f"❌ Пользователь @{username} не найден в бд!")
                return

            user_id = user['user_id']
            real_username = user['username'] or username
            current_level = user['admin_level'] or 0

            # Проверяем, не является ли он владельцем
            if user_id == owner_user_id:
                await message.answer("❌ не ахуевай.")
                return

            # Проверяем, является ли он админом
            if current_level == 0:
                await message.answer(f"❌ @{real_username} не является админом!")
                return

            # Удаляем из admin_levels
            result = await conn.execute(
                "DELETE FROM admin_levels WHERE user_id = $1",
                user_id
            )

            if result == "DELETE 0":
                await message.answer(f"❌ @{real_username} не найден в таблице админов!")
                return

            # Обнуляем admin_level в users
            await conn.execute(
                "UPDATE users SET admin_level = 0 WHERE user_id = $1",
                user_id
            )

        await message.answer(f"✅ @{real_username} удален из админов!", parse_mode="HTML")

        # Логируем действие
        await log_mod_action(
            target_id=message.from_user.id,
            target_name=message.from_user.username or "Admin",
            admin_name=message.from_user.username or "Admin",
            action="REMOVE_ADMIN",
            reason=f"Удален админ уровня {current_level} (@{real_username})"
        )

    @dp.message(Command("admins"))
    async def cmd_list_admins(message: types.Message):
        admin_level = await get_admin_level(message.from_user.id)
        if admin_level == 0:
            await message.answer("❌ Эта команда только для админов!")
            return

        async with db_pool_getter().acquire() as conn:
            admins = await conn.fetch(
                """
                SELECT al.user_id, al.level, al.username, al.promoted_by, al.promoted_at,
                       u.username as current_username
                FROM admin_levels al
                LEFT JOIN users u ON al.user_id = u.user_id
                ORDER BY al.level DESC, al.promoted_at ASC
                """
            )

        if not admins:
            await message.answer("❌ Админов нет в системе.")
            return

        level_names = {
            1: "🔹 Младший админ",
            2: "🔸 Средний админ",
            3: "🔶 Старший админ",
            4: "👑 Главнейший и Всемилюбимый"
        }

        text = "📋 <b>Список админов:</b>\n\n"

        for admin in admins:
            level = admin['level']
            username = admin['current_username'] or admin['username']
            promoted_at = admin['promoted_at'].strftime("%d.%m.%Y %H:%M")

            if level == 4:
                text += f"{level_names[level]}: @{username}\n"
            else:
                promoter = await get_admin_level(admin['promoted_by'] or 0)
                promoter_name = "Система" if promoter == 4 else f"ID {admin['promoted_by']}"
                text += f"{level_names[level]}: @{username} (назначен: {promoted_at}, от: {promoter_name})\n"

        await message.answer(text, parse_mode="HTML")

    @dp.message(Command("myadminlevel"))
    async def cmd_my_admin_level(message: types.Message):
        user_id = message.from_user.id
        admin_level = await get_admin_level(user_id)

        if admin_level == 0:
            await message.answer(
                f"❌ <b>НЕ АДМИН!</b>\n"
                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                f"Ты не админ.",
                parse_mode="HTML"
            )
            return

        level_names = {
            1: "🔹 Младший админ",
            2: "🔸 Средний админ",
            3: "🔶 Старший админ",
            4: "👑 Главнейший и Всемилюбимый"
        }

        permissions = {
            1: "/warn, /unwarn",
            2: "/warn, /unwarn, /mute, /unmute",
            3: "/warn, /unwarn, /mute, /unmute, /ban, /unban, /diary, /addtrigger, /deltrigger",
            4: "Все команды + управление всем"
        }

        text = (
            f"🎛  <b>ТВОЙ АДМИНСКИЙ УРОВЕНЬ</b>\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
            f"<b>{level_names[admin_level]}</b>\n\n"
            f"📋 <b>Доступные команды:</b>\n"
            f"{permissions[admin_level]}\n\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        )

        await message.answer(text, parse_mode="HTML")
