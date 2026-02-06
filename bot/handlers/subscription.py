# bot/handlers/subscription.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import Database
from services.yukassa import yukassa_service
from config import Config
from datetime import datetime

router = Router()


def get_subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ PRO — {Config.PRO_PRICE}₽/мес", callback_data="buy_pro")],
        [InlineKeyboardButton(text=f"📦 Базовая — {Config.BASIC_PRICE}₽/мес", callback_data="buy_basic")],
        [InlineKeyboardButton(text="🎁 Попробовать 3 дня бесплатно", callback_data="start_trial")],
    ])


@router.message(F.text == "💳 Подписка")
async def show_subscription(message: Message):
    user = await Database.get_user(message.from_user.id)
    
    if user and user.has_active_subscription():
        days_left = (user.subscription_end - datetime.utcnow()).days
        sub_type = "PRO ⭐" if user.subscription_type == "pro" else "Базовая"
        
        text = f"""
<b>Твоя подписка</b>

📦 Тип: {sub_type}
⏰ Осталось: {days_left} дней
📅 До: {user.subscription_end.strftime('%d.%m.%Y')}

Хочешь продлить или улучшить?
"""
    else:
        text = f"""
<b>💎 Подписки Freelance Radar</b>

<b>⭐ PRO — {Config.PRO_PRICE}₽/мес</b>
• ♾ Безлимит AI-откликов
• 🕵️ Детектор мошенников
• 💰 Калькулятор цен
• 📊 CRM для сделок
• 📈 Аналитика рынка
• 🦁 Режим Хищник

<b>📦 Базовая — {Config.BASIC_PRICE}₽/мес</b>
• 📋 Мониторинг всех бирж
• ✨ 50 AI-откликов/мес
• 🔔 Уведомления

🎁 <b>Первые 3 дня — бесплатно!</b>
"""
    
    await message.answer(text, reply_markup=get_subscription_keyboard())


@router.callback_query(F.data == "start_trial")
async def start_trial(callback: CallbackQuery):
    user = await Database.get_user(callback.from_user.id)
    
    if user and user.trial_used:
        await callback.answer("Пробный период уже использован!", show_alert=True)
        return
    
    success = await Database.start_user_trial(callback.from_user.id, "pro")
    
    if success:
        await callback.message.edit_text(
            """
🎉 <b>Пробный период активирован!</b>

У тебя есть 3 дня PRO-доступа:
• ♾ Безлимит AI-откликов
• 🕵️ Детектор мошенников
• 💰 Калькулятор цен
• 📊 CRM для сделок

Используй на полную! 🚀
""",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Открыть приложение", callback_data="open_webapp")]
            ])
        )
    else:
        await callback.answer("Не удалось активировать пробный период", show_alert=True)


@router.callback_query(F.data.startswith("buy_"))
async def buy_subscription(callback: CallbackQuery):
    sub_type = callback.data.replace("buy_", "")
    user = await Database.get_user(callback.from_user.id)
    
    if not user:
        await callback.answer("Сначала нажми /start", show_alert=True)
        return
    
    try:
        payment_id, payment_url = await yukassa_service.create_payment(user.id, sub_type)
        
        # Сохраняем платёж
        await Database.create_payment(user.id, payment_id, 
            Config.PRO_PRICE if sub_type == "pro" else Config.BASIC_PRICE, 
            sub_type)
        
        price = Config.PRO_PRICE if sub_type == "pro" else Config.BASIC_PRICE
        name = "PRO ⭐" if sub_type == "pro" else "Базовая"
        
        await callback.message.edit_text(
            f"""
💳 <b>Оплата подписки</b>

📦 Тип: {name}
💰 Сумма: {price}₽
⏰ Период: 30 дней

Нажми кнопку для оплаты:
""",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
                [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_payment_{payment_id}")],
                [InlineKeyboardButton(text="← Назад", callback_data="show_subscription")]
            ])
        )
        
    except Exception as e:
        await callback.answer("Ошибка создания платежа. Попробуй позже.", show_alert=True)


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery):
    payment_id = callback.data.replace("check_payment_", "")
    
    payment = await yukassa_service.check_payment(payment_id)
    
    if payment and payment.status == "succeeded":
        user = await Database.confirm_payment(payment_id)
        if user:
            await callback.message.edit_text(
                """
✅ <b>Оплата успешна!</b>

Подписка активирована. Спасибо! 🎉

Теперь тебе доступны все функции.
""",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Открыть приложение", callback_data="open_webapp")]
                ])
            )
        else:
            await callback.answer("Ошибка активации. Напиши в поддержку.", show_alert=True)
    else:
        await callback.answer("Платёж ещё не получен. Подожди минуту.", show_alert=True)


@router.callback_query(F.data == "show_subscription")
async def show_subscription_callback(callback: CallbackQuery):
    await show_subscription(callback.message)
    await callback.answer()
