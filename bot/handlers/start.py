# bot/handlers/start.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from database.db import Database
from bot.keyboards.keyboards import get_main_keyboard, get_trial_keyboard, get_categories_keyboard
from config import Config

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await Database.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name
    )
    
    welcome_text = f"""
👋 Привет, {message.from_user.first_name}!

🎯 <b>Freelance Radar</b> — твой персональный охотник за заказами!

Я мониторю 10+ бирж фриланса и мгновенно присылаю новые заказы по твоим категориям.

⚡️ <b>Что умею:</b>
• Отслеживаю Kwork, FL.ru, Habr Freelance, HH и Telegram-каналы
• Уведомляю о новых заказах за секунды
• Генерирую идеальные отклики с помощью ИИ

🎁 <b>Первые {Config.TRIAL_DAYS} дня — бесплатно!</b>
"""
    
    if user.has_active_subscription():
        await message.answer(
            welcome_text + "\n\n✅ У тебя активная подписка!",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            welcome_text,
            parse_mode="HTML",
            reply_markup=get_trial_keyboard()
        )


@router.callback_query(F.data == "start_trial")
async def start_trial(callback: CallbackQuery):
    user = await Database.get_user(callback.from_user.id)
    
    if user.trial_used:
        await callback.answer("Пробный период уже использован!", show_alert=True)
        return
    
    await Database.start_user_trial(callback.from_user.id)
    
    await callback.message.edit_text(
        """
🎉 <b>Пробный период активирован!</b>

Теперь выбери категории заказов, которые тебя интересуют:
""",
        parse_mode="HTML",
        reply_markup=get_categories_keyboard()
    )