"""Shop commands and callbacks."""

import re
from collections.abc import Callable

from aiogram import F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder


def register_shop_handlers(dp, *, db_pool_getter: Callable, shop_data: dict, refresh_shop_if_needed: Callable):
    def get_shop_keyboard(category="items"):
        builder = InlineKeyboardBuilder()
        if category == "items":
            for item in shop_data["items"]:
                price = item["price"]
                builder.button(
                    text=f"📦 {item['name']} ({price} 💰)",
                    callback_data=f"buy_item_{item['id']}_{price}",
                )
            builder.button(text="➡️ Смотреть Титулы", callback_data="shop_tab_titles")
        else:
            for title in shop_data["titles"]:
                builder.button(
                    text=f"🏷 {title['name']} ({title['price']} 💰)",
                    callback_data=f"buy_title_{title['id']}_{title['price']}",
                )
            builder.button(text="⬅️ Смотреть Предметы", callback_data="shop_tab_items")
        builder.adjust(1)
        return builder.as_markup()

    @dp.message(Command("shop"))
    async def cmd_shop(message: types.Message):
        await refresh_shop_if_needed()
        text = "🏪<b>Магазин (обновка каждые 4ч):</b>\n\n<i>Раздел: 🎒 Предметы</i>"
        await message.answer(text, reply_markup=get_shop_keyboard(), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("shop_tab_"))
    async def cb_shop_tab(callback: types.CallbackQuery):
        tab = callback.data.split("_")[2]
        await refresh_shop_if_needed()
        section_name = "🎒 Предметы" if tab == "items" else "🏷 Титулы"
        text = f"🏪 <b>Магазин (обновка каждые 4ч):</b>\n\n<i>Раздел: {section_name}</i>"
        await callback.message.edit_text(
            text, reply_markup=get_shop_keyboard(tab), parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("buy_"))
    async def cb_buy(callback: types.CallbackQuery):
        parts = callback.data.split("_")
        buy_type = parts[1]
        item_id = int(parts[2])
        price = int(parts[3])
        user_id = callback.from_user.id

        async with db_pool_getter().acquire() as conn:
            async with conn.transaction():
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
                    await callback.answer("❌ Нищеброд! Не хватает кредитов.", show_alert=True)
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
                    await callback.answer("✅ Предмет куплен и брошен в рюкзак!", show_alert=True)
                elif buy_type == "title":
                    exists = await conn.fetchval(
                        "SELECT 1 FROM user_titles WHERE user_id = $1 AND title_id = $2",
                        user_id,
                        item_id,
                    )
                    if exists:
                        await callback.answer("⚠️ У тебя уже есть этот титул!", show_alert=True)
                        return
                    await conn.execute(
                        "INSERT INTO user_titles (user_id, title_id) VALUES ($1, $2)",
                        user_id,
                        item_id,
                    )
                    await conn.execute(
                        "UPDATE users SET title_id = $1 WHERE user_id = $2", item_id, user_id
                    )
                    await callback.answer("👑 Титул куплен и торжественно надет!", show_alert=True)

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
            new_text = current_html + f"\n\n<i>{user_name} только что что-то купил...</i>"
        await callback.message.edit_text(
            new_text, reply_markup=callback.message.reply_markup, parse_mode="HTML"
        )

    return get_shop_keyboard
