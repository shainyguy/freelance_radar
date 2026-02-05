# bot/handlers/subscription.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from database.db import Database
from services.yukassa import yukassa_service
from bot.keyboards.keyboards import get_subscription_keyboard, get_main_keyboard
from config import Config
from datetime import datetime

router = Router()


@router.message(F.text == "💳 Подписка")
async def show_subscription(message: Message):
    user = await Database.get_user(message.from_user.id)
    
    if user.has_active_subscription():
        days_left = (user.subscription_end - datetime.utcnow()).days
        status = "✅ Активна"
        if user.is_in_trial():
            status = "🎁 Пробный период"
        
        text = f"""
<b>Твоя подписка</b>

Статус: {status}
Осталось дней: {days_left}
Дата окончания: {user.subscription_end.strftime('%d.%m.%Y')}
"""
    else:
        text = f"""
<b>Подписка не активна</b>

💰 Стоимость: {Config.SUBSCRIPTION_PRICE}₽/месяц

Что даёт подписка:
• Мониторинг 10+ бирж в реальном времени
• Мгновенные уведомления о заказах
• Генерация откликов с помощью ИИ
• Фильтры по бюджету
"""
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_subscription_keyboard()
    )


@router.callback_query(F.data == "buy_subscription")
async def buy_subscription(callback: CallbackQuery):
    try:
        user = await Database.get_user(callback.from_user.id)
        
        # Создаём платёж
        payment_id, payment_url = await yukassa_service.create_payment(user.id)
        
        # Сохраняем платёж в БД
        await Database.create_payment(user.id, payment_id, Config.SUBSCRIPTION_PRICE)
        
        await callback.message.edit_text(
            f"""
💳 <b>Оплата подписки</b>

Сумма: {Config.SUBSCRIPTION_PRICE}₽
Период: 30 дней

Нажми кнопку ниже для оплаты:
""",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(payment_url)
        )
        
    except Exception as e:
        await callback.answer("Ошибка создания платежа. Попробуйте позже.", show_alert=True)


@router.callback_query(F.data == "check_payment")
async def check_payment(callback: CallbackQuery):
    # В реальности тут нужно проверить последний платёж пользователя
    # Лучше использовать webhook от ЮKassa
    
    await callback.answer(
        "Обрабатываем платёж... Это может занять до минуты.",
        show_alert=True
    )