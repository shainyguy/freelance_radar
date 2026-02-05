# bot/handlers/categories.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from database.db import Database
from bot.keyboards.keyboards import get_categories_keyboard, get_main_keyboard

router = Router()


@router.message(F.text == "🔍 Мои категории")
async def show_categories(message: Message):
    user = await Database.get_user(message.from_user.id)
    
    await message.answer(
        "Выбери категории, которые тебя интересуют:",
        reply_markup=get_categories_keyboard(user.categories or [])
    )


@router.callback_query(F.data.startswith("toggle_cat:"))
async def toggle_category(callback: CallbackQuery):
    category = callback.data.split(":")[1]
    user = await Database.get_user(callback.from_user.id)
    
    categories = user.categories or []
    
    if category in categories:
        categories.remove(category)
    else:
        categories.append(category)
    
    await Database.update_user_categories(callback.from_user.id, categories)
    
    await callback.message.edit_reply_markup(
        reply_markup=get_categories_keyboard(categories)
    )
    await callback.answer()


@router.callback_query(F.data == "save_categories")
async def save_categories(callback: CallbackQuery):
    user = await Database.get_user(callback.from_user.id)
    
    if not user.categories:
        await callback.answer("Выбери хотя бы одну категорию!", show_alert=True)
        return
    
    cats_text = ", ".join(user.categories)
    
    await callback.message.edit_text(
        f"""
✅ <b>Настройки сохранены!</b>

Твои категории: {cats_text}

Теперь я буду присылать тебе новые заказы по этим категориям.
Используй кнопки меню для управления ботом.
""",
        parse_mode="HTML"
    )
    
    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_keyboard()
    )