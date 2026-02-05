# bot/handlers/start.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from database.db import Database
from bot.keyboards.keyboards import get_main_keyboard, get_trial_keyboard
from config import Config

router = Router()


def get_webapp_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с Mini App"""
    webapp_url = f"{Config.WEBHOOK_URL}/webapp" if Config.WEBHOOK_URL else "https://your-app.railway.app/webapp"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🚀 Открыть Freelance Radar",
            web_app=WebAppInfo(url=webapp_url)
        )],
        [InlineKeyboardButton(
            text="⚡ Турбо-парсинг",
            callback_data="turbo_parse"
        )],
        [InlineKeyboardButton(
            text="🦁 Режим Хищник",
            callback_data="predator_mode"
        )]
    ])


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await Database.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name
    )
    
    welcome_text = f"""
👋 Привет, {message.from_user.first_name}!

🎯 <b>Freelance Radar</b> — охотник за жирными заказами!

⚡️ <b>Уникальные фишки:</b>
• 🦁 Режим «Хищник» — мгновенные пуши для заказов от 50K
• 🎯 AI Match Score — насколько заказ подходит тебе
• ✨ AI-генератор идеальных откликов
• 📊 Трекинг заработка и аналитика
• 🏆 Leaderboard топ-фрилансеров

🎁 <b>Первые {Config.TRIAL_DAYS} дня — бесплатно!</b>
"""
    
    if user.has_active_subscription():
        welcome_text += "\n\n✅ У тебя активная подписка!"
    
    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_webapp_keyboard()
    )


@router.callback_query(F.data == "turbo_parse")
async def turbo_parse_handler(callback: CallbackQuery):
    """Принудительный парсинг"""
    user = await Database.get_user(callback.from_user.id)
    
    if not user or not user.has_active_subscription():
        await callback.answer("Нужна активная подписка!", show_alert=True)
        return
    
    await callback.answer("⚡ Запускаю турбо-парсинг...")
    
    msg = await callback.message.answer("🔍 Сканирую биржи...")
    
    from parsers import ALL_PARSERS
    
    new_count = 0
    categories = user.categories or ['design', 'python', 'copywriting', 'marketing']
    
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


@router.callback_query(F.data == "predator_mode")
async def predator_mode_handler(callback: CallbackQuery):
    """Переключение режима Хищник"""
    user = await Database.get_user(callback.from_user.id)
    
    if not user or not user.has_active_subscription():
        await callback.answer("Нужна активная подписка!", show_alert=True)
        return
    
    new_state = not user.predator_mode
    await Database.update_predator_mode(callback.from_user.id, new_state)
    
    if new_state:
        await callback.answer("🦁 Режим Хищник АКТИВИРОВАН!", show_alert=True)
    else:
        await callback.answer("Режим Хищник отключён", show_alert=True)
