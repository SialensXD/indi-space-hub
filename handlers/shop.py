"""Shop commands and callbacks."""

import re
from collections.abc import Callable

from aiogram import F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder


def register_shop_handlers(dp, *, db_pool_getter: Callable, shop_data: dict, refresh_shop_if_needed: Callable, user_in_active_duel: Callable):
    async def get_shop_keyboard(category="items", owner_id=None):
        if owner_id is None:
            return None
        async with db_pool_getter().acquire() as conn:
            owned_items = await conn.fetch("SELECT item_id FROM inventory WHERE user_id = $1 AND count > 0", owner_id)
            owned_titles = await conn.fetch("SELECT title_id FROM user_titles WHERE user_id = $1", owner_id)
        owned_item_ids = {row["item_id"] for row in owned_items}
        owned_title_ids = {row["title_id"] for row in owned_titles}
        builder = InlineKeyboardBuilder()
        if category == "items":
            for item in shop_data["items"]:
                if item["id"] in owned_item_ids:
                    continue
                price = item["price"]
                builder.button(
                    text=f"📦 {item['name']} ({price} 💰)",
                    callback_data=f"buy_item_{item['id']}_{owner_id}",
                )
            builder.button(text="➡️ Смотреть Титулы", callback_data=f"shop_tab_titles_{owner_id}")
        else:
            for title in shop_data["titles"]:
                if title["id"] in owned_title_ids:
                    continue
                builder.button(
                    text=f"🏷 {title['name']} ({title['price']} 💰)",
                    callback_data=f"buy_title_{title['id']}_{owner_id}",
                )
            builder.button(text="⬅️ Смотреть Предметы", callback_data=f"shop_tab_items_{owner_id}")
        builder.adjust(1)
        return builder.as_markup()

    @dp.message(Command("shop"))
    async def cmd_shop(message: types.Message):
        if user_in_active_duel(message.from_user.id):
            await message.answer(
                "⚔️ <b>В БОЕ!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Магазин недоступен!",
                parse_mode="HTML"
            )
            return
        await refresh_shop_if_needed()
        text = (
            "🏪 <b>МАГАЗИН</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>Обновляется каждые 4 часа</i>\n\n"
            "<b>🎲 РАЗДЕЛ: ВОПЛОЩЕННЫЕ ПРЕДМЕТЫ</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await message.answer(text, reply_markup=await get_shop_keyboard(owner_id=message.from_user.id), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("shop_tab_"))
    async def cb_shop_tab(callback: types.CallbackQuery):
        parts = callback.data.split("_")
        tab = parts[2]
        owner_id = int(parts[3]) if len(parts) > 3 else None
        if owner_id != callback.from_user.id:
            await callback.answer(
                "❌ Это магазин для другого игрока!",
                show_alert=True
            )
            return
        if user_in_active_duel(callback.from_user.id):
            await callback.answer(
                "⚔️ Магазин недоступен в бое!",
                show_alert=True
            )
            return
        await refresh_shop_if_needed()
        section_name = "🎲 ПРЕДМЕТЫ" if tab == "items" else "🎗 ТИТУЛЫ"
        text = (
            f"🏪 <b>МАГАЗИН</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<i>Обновляется каждые 4 часа</i>\n\n"
            f"<b>РАЗДЕЛ: {section_name}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await callback.message.edit_text(
            text, reply_markup=await get_shop_keyboard(tab, owner_id), parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("buy_"))
    async def cb_buy(callback: types.CallbackQuery):
        parts = callback.data.split("_")
        buy_type = parts[1]
        item_id = int(parts[2])
        owner_id = int(parts[3])
        user_id = callback.from_user.id
        if owner_id != user_id:
            await callback.answer(
                "❌ Эта покупка предназначена другому игроку!",
                show_alert=True
            )
            return
        if user_in_active_duel(user_id):
            await callback.answer(
                "⚔️ Магазин недоступен в бое!",
                show_alert=True
            )
            return

        async with db_pool_getter().acquire() as conn:
            async with conn.transaction():
                table = "items" if buy_type == "item" else "titles"
                product = await conn.fetchrow(f"SELECT id, price FROM {table} WHERE id = $1", item_id)
                if not product or product["id"] not in {entry["id"] for entry in shop_data["items" if buy_type == "item" else "titles"]}:
                    await callback.answer(
                        "🚫 <b>ТОВАР НЕДОступен!</b>\n\nОбнови витрину и попробуй еще раз.",
                        show_alert=True
                    )
                    return
                price = product["price"]
                if buy_type == "item":
                    already_owned = await conn.fetchval(
                        "SELECT 1 FROM inventory WHERE user_id = $1 AND item_id = $2 AND count > 0",
                        user_id,
                        item_id,
                    )
                    if already_owned:
                        await callback.answer(
                            "😴 <b>У тебя уже есть!</b>",
                            show_alert=True
                        )
                        return
                elif buy_type == "title":
                    already_owned = await conn.fetchval(
                        "SELECT 1 FROM user_titles WHERE user_id = $1 AND title_id = $2",
                        user_id,
                        item_id,
                    )
                    if already_owned:
                        await callback.answer(
                            "😴 <b>Отличный титул, но у тебя уже есть!</b>",
                            show_alert=True
                        )
                        return
                charged = await conn.fetchval(
                    """
                    UPDATE users SET credits = credits - $1
                    WHERE user_id = $2 AND credits >= $1
                    RETURNING user_id
                    """,
                    price,
                    user_id,
                )
                if charged is None:
                    await callback.answer(
                        "💸 <b>НИЩЕБРОД!</b>\n\nНе хватает кредитов для покупки.",
                        show_alert=True
                    )
                    return

                if buy_type == "item":
                    await conn.execute(
                        """
                        INSERT INTO inventory (user_id, item_id, count)
                        VALUES ($1, $2, 1)
                        ON CONFLICT (user_id, item_id) DO UPDATE
                        SET count = inventory.count + 1
                        """,
                        user_id,
                        item_id,
                    )
                    await callback.answer(
                        "✅ <b>ПРЕДМЕТ КУПЛЕН!</b>\n\n🎲 Положен в твой рюкзак.",
                        show_alert=True
                    )
                elif buy_type == "title":
                    await conn.execute(
                        "INSERT INTO user_titles (user_id, title_id) VALUES ($1, $2)",
                        user_id,
                        item_id,
                    )
                    await conn.execute(
                        "UPDATE users SET title_id = $1 WHERE user_id = $2", item_id, user_id
                    )
                    await callback.answer(
                        "👑 <b>ТИТУЛ КУПЛЕН!</b>\n\n👑 Титул торжественно надет.",
                        show_alert=True
                    )

        current_html = callback.message.html_text or callback.message.text or ""
        user_name = callback.from_user.first_name
        pattern = rf"<i>{re.escape(user_name)} только что что-то купил(?:\s*×(\d+))?\.\.\.</i>"
        match = re.search(pattern, current_html)
        if match:
            count = int(match.group(1)) if match.group(1) else 1
            new_text = re.sub(
                pattern,
                f"<i>{user_name} только что что-то купил ×{count + 1}...</i>",
                current_html,
            )
        else:
            new_text = current_html + f"\n\n🎲 <i>{user_name} только что что-то купил...</i>"
        await callback.message.edit_text(
            new_text, reply_markup=await get_shop_keyboard("titles" if buy_type == "title" else "items", user_id), parse_mode="HTML"
        )

    return get_shop_keyboard
