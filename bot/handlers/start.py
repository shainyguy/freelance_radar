# bot/handlers/start.py
import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from database.db import Database
from bot.keyboards.keyboards import get_categories_keyboard
from config import Config

router = Router()


def get_webapp_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с Mini App"""
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '')
    
    buttons = []
    
    if domain:
        webapp_url = f"https://{domain}/webapp"
        buttons.append([InlineKeyboardButton(
            text="🚀 Открыть Freelance Radar",
            web_app=WebAppInfo(url=webapp_url)
        )])
    
    buttons.extend([
        [InlineKeyboardButton(text="⚡ Турбо-парсинг", callback_data="turbo_parse")],
        [
            InlineKeyboardButton(text="🔍 Категории", callback_data="show_categories"),
            InlineKeyboardButton(text="💳 Подписка", callback_data="show_subscription")
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await Database.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name
    )
    
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '')
    
    welcome_text = f"""
👋 Привет, {message.from_user.first_name}!

🎯 <b>Freelance Radar</b> — охотник за жирными заказами!

⚡️ <b>Возможности:</b>
• Мониторинг 10+ бирж в реальном времени
• AI-генератор идеальных откликов
• Режим «Хищник» для заказов от 50K₽
• Турбо-парсинг по кнопке

🎁 <b>Первые {Config.TRIAL_DAYS} дня — бесплатно!</b>
"""
    
    if user.has_active_subscription():
        welcome_text += "\n\n✅ У тебя активная подписка!"
    
    await message.answer(
        welcome_text,
        reply_markup=get_webapp_keyboard()
    )


@router.callback_query(F.data == "turbo_parse")
async def turbo_parse_handler(callback: CallbackQuery):
    """Принудительный парсинг"""
    user = await Database.get_user(callback.from_user.id)
    
    await callback.answer("⚡ Запускаю турбо-парсинг...")
    msg = await callback.message.answer("🔍 Сканирую биржи...")
    
    try:
        from parsers import ALL_PARSERS
        
        new_count = 0
        categories = (user.categories if user else None) or ['design', 'python', 'copywriting', 'marketing']
        
        for parser in ALL_PARSERS:
            for category in categories:
                try:
                    orders = await parser.parse_orders(category)
                    for order_data in orders:
                        order = await Database.save_order(order_data)
                        if order:
                            new_count += 1
                except Exception as e:
                    pass
            await parser.close()
        
        await msg.edit_text(f"✅ Найдено <b>{new_count}</b> новых заказов!")
        
    except Exception as e:
        await msg.edit_text("⚠️ Ошибка при парсинге")


@router.callback_query(F.data == "show_categories")
async def show_categories_handler(callback: CallbackQuery):
    user = await Database.get_user(callback.from_user.id)
    await callback.message.answer(
        "🎯 Выбери категории:",
        reply_markup=get_categories_keyboard(user.categories if user else [])
    )
    await callback.answer()


@router.callback_query(F.data == "show_subscription")
async def show_subscription_handler(callback: CallbackQuery):
    user = await Database.get_user(callback.from_user.id)
    
    if user and user.has_active_subscription():
        from datetime import datetime
        days_left = (user.subscription_end - datetime.utcnow()).days
        text = f"✅ Подписка активна!\nОсталось: {days_left} дней"
    else:
        text = f"""
💳 <b>Подписка Freelance Radar</b>

Стоимость: {Config.SUBSCRIPTION_PRICE}₽/месяц

🎁 Первые 3 дня бесплатно!
"""
    
    await callback.message.answer(text)
    await callback.answer()
