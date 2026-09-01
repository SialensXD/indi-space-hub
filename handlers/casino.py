"""Casino commands and PvP dice callbacks."""

import asyncio
import random
from collections.abc import Callable

from aiogram import F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder


def register_casino_handlers(dp, *, db_pool_getter: Callable, bot, slot_symbols):
    @dp.message(Command("slots", "casino"))
    async def cmd_slots(message: types.Message):
        user_id = message.from_user.id
        args = message.text.split()[1:]

        if not args:
            await message.answer(
                "🎰 <b>СЛОТЫ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "<b>Использование:</b>\n"
                "<code>/slots [ставка]</code> - обычная ставка\n"
                "<code>/slots вабанк</code> - все фишки\n\n"
                "💡 <b>Примеры:</b>\n"
                "/slots 100\n"
                "/slots вабанк",
                parse_mode="HTML"
            )
            return

        async with db_pool_getter().acquire() as conn:
            user = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", user_id)
            if not user or user['credits'] <= 0:
                await message.answer(
                    "💸 <b>БЕЗ КРЕДИТОВ!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "Фууу, бомж🤮\n\n"
                    "У тебя нет кредитов для игры!",
                    parse_mode="HTML"
                )
                return

            # Обработка ставки и Вабанка
            if args[0].lower() in ["вабанк", "vabank", "allin", "все"]:
                bet = user['credits']
            else:
                try:
                    bet = int(args[0])
                    if bet <= 0: raise ValueError
                except ValueError:
                    await message.answer("🙄 Укажи корректную сумму ставки!")
                    return

            if bet > user['credits']:
                await message.answer(
                    "💸 <b>НЕДОСТАТОЧНО СРЕДСТВ!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Главный бомж района?\n\n"
                    f"Твой баланс: <b>{user['credits']} 💰</b>\n"
                    f"Ставка: <b>{bet} 💰</b>",
                    parse_mode="HTML"
                )
                return

            # Списываем ставку только если баланс все еще достаточен.
            charged = await conn.fetchval(
                """
                UPDATE users SET credits = credits - $1
                WHERE user_id = $2 AND credits >= $1
                RETURNING user_id
                """,
                bet,
                user_id,
            )
            if charged is None:
                await message.answer(
                    "⚠️ <b>ОШИБКА!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "Баланс изменился во время игры.\n"
                    "Попробуй еще раз!",
                    parse_mode="HTML"
                )
                return

        # 1. Отправляем анимацию ожидания
        anim_msg = await message.answer(
            "🎰 <b>КРУТИМ БАРАБАНЫ...</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "[ ⏳ | ⏳ | ⏳ ]\n\n"
            "<i>Удача на твоей стороне?</i>",
            parse_mode="HTML"
        )
        await asyncio.sleep(1.5)

        # 2. Логика генерации комбинации
        roll_type = random.choices(["3inRow", "2inRow", "0inRow"], weights=[7, 23, 70])[0]

        symbols_list = list(slot_symbols.keys())
        weights_list = [slot_symbols[s]["weight"] for s in symbols_list]

        if roll_type == "3inRow":
            chosen_symbol = random.choices(symbols_list, weights=weights_list)[0]
            reels = [chosen_symbol, chosen_symbol, chosen_symbol]
            multiplier = slot_symbols[chosen_symbol]["mult"]
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
        async with db_pool_getter().acquire() as conn:
            if payout > 0:
                await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", payout, user_id)
            new_balance = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", user_id)

        reels_str = f"[ {reels[0]} | {reels[1]} | {reels[2]} ]"

        if multiplier > 1:
            res_text = (
                f"🤑 <b>ДЖЕКПОТТ!!!!!</b>\n\n"
                f"Три в ряд! 🎊\n\n"
                f"Выигрыш: <b>+{payout} 💰</b> (x{multiplier})"
            )
        elif multiplier == 1:
            res_text = (
                f"♻️ <b>ВОЗВРАТ СТАВКИ!</b>\n\n"
                f"Две одинаковые... Повезло!\n\n"
                f"Возврат: <b>+{payout} 💰</b>"
            )
        else:
            res_text = (
                f"💀 <b>НИЧЕГО НЕ СОВПАЛО!</b>\n\n"
                f"Хахахаха, лоох!\n\n"
                f"Потеряно: <b>-{bet} 💰</b>"
            )

        final_text = (
            f"🎰 <b>РЕЗУЛЬТАТЫ СЛОТОВ</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Игрок: <b>{message.from_user.first_name}</b>\n"
            f"💰 Ставка: <b>{bet}</b>\n\n"
            f"<b>{reels_str}</b>\n\n"
            f"{res_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💳 <b>Баланс:</b> {new_balance} 💰"
        )

        await anim_msg.edit_text(final_text, parse_mode="HTML")

    @dp.message(Command("dice"))
    async def cmd_dice(message: types.Message):
        user_id = message.from_user.id

        if not message.reply_to_message or message.reply_to_message.from_user.is_bot:
            await message.answer(
                "🎲 <b>БРОСОК КОСТЕЙ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "<b>Как играть:</b>\n"
                "1️⃣ Ответь на сообщение соперника\n"
                "2️⃣ Напиши: <code>/dice [ставка]</code>\n"
                "3️⃣ Ждешь ответа!\n\n"
                "💡 Примеры: <code>/dice 100</code> или <code>/dice вабанк</code>",
                parse_mode="HTML"
            )
            return

        target = message.reply_to_message.from_user
        if target.id == user_id:
            await message.answer(
                "😑 <b>ХЕЙ!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Нельзя играть в кубики с самим собой!\n"
                "Найди соперника!",
                parse_mode="HTML"
            )
            return
        args = message.text.split()[1:]
        if not args:
            await message.answer(
                "⚠️ <b>УКАЖИ СТАВКУ!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Примеры:\n"
                "<code>/dice 100</code>\n"
                "<code>/dice вабанк</code>",
                parse_mode="HTML"
            )
            return

        async with db_pool_getter().acquire() as conn:
            p1 = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", user_id)
            p2 = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", target.id)

            if not p1 or not p2:
                await message.answer(
                    "❌ <b>ОШИБКА!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "Один из участников не найден в БД!",
                    parse_mode="HTML"
                )
                return

            # Расчет ставки для ПВП
            if args[0].lower() in ["вабанк", "vabank", "allin", "все"]:
                bet = min(p1['credits'], p2['credits']) # Вабанк ограничем меньшим балансом
            else:
                try:
                    bet = int(args[0])
                    if bet <= 0: raise ValueError
                except ValueError:
                    await message.answer(
                        "🙄 <b>НЕВЕРНАЯ СТАВКА!</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "Укажи положительное число!",
                        parse_mode="HTML"
                    )
                    return

            if p1['credits'] < bet:
                await message.answer(
                    "😂 <b>НИЩЕБРОД!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "У тебя недостаточно средств!\n\n"
                    f"Твой баланс: <b>{p1['credits']}</b>\n"
                    f"Ставка: <b>{bet}</b>",
                    parse_mode="HTML"
                )
                return
            if p2['credits'] < bet:
                await message.answer(
                    f"🥶 <b>БЕД, СОВПАЛ!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"У @{target.username or target.first_name} недостаточно средств!\n\n"
                    f"Баланс соперника: <b>{p2['credits']}</b>\n"
                    f"Ставка: <b>{bet}</b>",
                    parse_mode="HTML"
                )
                return

        # Создаем кнопку вызова
        builder = InlineKeyboardBuilder()
        builder.button(text=f"🎲 Принять дуэль ({bet} 💰)", callback_data=f"dice_accept_{user_id}_{target.id}_{bet}")
        builder.button(text="🤡 Струсить", callback_data=f"duel_decline_{target.id}")
        builder.adjust(1)

        await message.answer(
            f"🎲 <b>ВЫЗОВ НА ДУЭЛЬ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 <b>Инициатор:</b> {message.from_user.first_name}\n"
            f"🎯 <b>Соперник:</b> {target.first_name}\n\n"
            f"<b>Игра: Бросок костей</b>\n"
            f"💰 <b>Ставка:</b> {bet} 💰 с каждого\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<i>Выше рейка - выше риск!</i>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

    @dp.callback_query(F.data.startswith("dice_accept_"))
    async def cb_dice_accept(callback: types.CallbackQuery):
        parts = callback.data.split("_")
        p1_id, p2_id, bet = int(parts[2]), int(parts[3]), int(parts[4])

        if callback.from_user.id != p2_id:
            await callback.answer(
                "❌ Это вызов не для тебя!",
                show_alert=True
            )
            return

        async with db_pool_getter().acquire() as conn:
            async with conn.transaction():
                charged_1 = await conn.fetchval(
                    """
                    UPDATE users SET credits = credits - $1
                    WHERE user_id = $2 AND credits >= $1
                    RETURNING user_id
                    """,
                    bet,
                    p1_id,
                )
                charged_2 = await conn.fetchval(
                    """
                    UPDATE users SET credits = credits - $1
                    WHERE user_id = $2 AND credits >= $1
                    RETURNING user_id
                    """,
                    bet,
                    p2_id,
                )
                if charged_1 is None or charged_2 is None:
                    await callback.message.edit_text(
                        "❌ <b>ОШИБКА!</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "Баланс одного из игроков изменился.\n"
                        "Игра отменена!",
                        parse_mode="HTML"
                    )
                    return

        # Удаляем сообщение с кнопкой, чтобы чат не засорялся
        await callback.message.delete()

        async with db_pool_getter().acquire() as conn:
            p1_user = await conn.fetchrow("SELECT username FROM users WHERE user_id = $1", p1_id)
            p2_user = await conn.fetchrow("SELECT username FROM users WHERE user_id = $1", p2_id)
        name1 = p1_user['username'] or "Игрок 1"
        name2 = p2_user['username'] or "Игрок 2"

        # --- КИДАЕМ АНИМИРОВАННЫЕ КУБИКИ TELEGRAM ---

        await callback.message.answer(f"👤 <b>{name1}</b> бросает кубик...", parse_mode="HTML")
        dice1 = await callback.message.answer_dice(emoji="🎲")
        await asyncio.sleep(3.5) 

        await callback.message.answer(f"👤 <b>{name2}</b> бросает кубик...", parse_mode="HTML")
        dice2 = await callback.message.answer_dice(emoji="🎲")
        await asyncio.sleep(3.5) 

        #генерирует результат внутри объекта dice
        r1 = dice1.dice.value
        r2 = dice2.dice.value

        text = (
            f"🎲 <b>РЕЗУЛЬТАТЫ ДУЭЛИ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎲 <b>{name1}:</b> <b>{r1}</b> точек\n"
            f"🎲 <b>{name2}:</b> <b>{r2}</b> точек\n\n"
        )

        async with db_pool_getter().acquire() as conn:
            if r1 > r2:
                win_pot = bet * 2
                await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", win_pot, p1_id)
                text += (
                    f"🏆 <b>ПОБЕДИТЕЛЬ!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🎊 <b>{name1}</b>\n\n"
                    f"💰 Забирает: <b>+{win_pot} 💰</b>"
                )
            elif r2 > r1:
                win_pot = bet * 2
                await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", win_pot, p2_id)
                text += (
                    f"🏆 <b>ПОБЕДИТЕЛЬ!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🎊 <b>{name2}</b>\n\n"
                    f"💰 Забирает: <b>+{win_pot} 💰</b>"
                )
            else:
                # ничья — возврат
                await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", bet, p1_id)
                await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", bet, p2_id)
                text += (
                    f"🤝 <b>НИЧЬЯ!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Вам повезло...\n\n"
                    f"💰 Ставки возвращены обоим!"
                )

        await callback.message.answer(text, parse_mode="HTML")
        await callback.answer()
