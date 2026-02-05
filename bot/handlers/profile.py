# bot/handlers/profile.py
from aiogram import Router, F
from aiogram.types import Message
from database.db import Database
from bot.keyboards.keyboards import get_settings_keyboard
from datetime import datetime

router = Router()


@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user = await Database.get_user(message.from_user.id)
    
    # Статус подписки
    if user.has_active_subscription():
        days_left = (user.subscription_end - datetime.utcnow()).days
        sub_status = f"✅ Активна ({days_left} дн.)"
    else:
        sub_status = "❌ Не активна"
    
    # Категории
    cats = ", ".join(user.categories) if user.categories else "Не выбраны"
    
    # Минимальный бюджет
    min_budget = f"{user.min_budget:,}₽" if user.min_budget else "Не установлен"
    
    text = f"""
👤 <b>Твой профиль</b>

🆔 ID: {user.telegram_id}
👤 Username: @{user.username or 'не указан'}

📊 <b>Статистика:</b>
• Подписка: {sub_status}
• Категории: {cats}
• Мин. бюджет: {min_budget}
• Уведомления: {'✅ Вкл' if user.is_active else '⏸ Выкл'}

📅 Дата регистрации: {user.created_at.strftime('%d.%m.%Y')}
"""
    
    await message.answer(text, parse_mode="HTML", reply_markup=get_settings_keyboard(user))


@router.message(F.text == "⚙️ Настройки")
async def show_settings(message: Message):
    user = await Database.get_user(message.from_user.id)
    
    await message.answer(
        "⚙️ <b>Настройки</b>\n\nВыбери, что хочешь изменить:",
        parse_mode="HTML",
        reply_markup=get_settings_keyboard(user)
    )