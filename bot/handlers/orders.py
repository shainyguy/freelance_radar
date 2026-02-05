# bot/handlers/orders.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import Database
from bot.keyboards.keyboards import get_main_keyboard
import logging

logger = logging.getLogger(__name__)
router = Router()


class BudgetState(StatesGroup):
    waiting_for_budget = State()


@router.callback_query(F.data == "set_min_budget")
async def set_min_budget_start(callback: CallbackQuery, state: FSMContext):
    """Начало установки минимального бюджета"""
    await callback.message.answer(
        "💰 Введи минимальный бюджет заказов (в рублях):\n\n"
        "Например: <code>5000</code>\n\n"
        "Отправь <code>0</code> чтобы отключить фильтр.",
        parse_mode="HTML"
    )
    await state.set_state(BudgetState.waiting_for_budget)
    await callback.answer()


@router.message(BudgetState.waiting_for_budget)
async def set_min_budget_finish(message: Message, state: FSMContext):
    """Сохранение минимального бюджета"""
    try:
        budget = int(message.text.replace(" ", "").replace("₽", ""))
        
        if budget < 0:
            await message.answer("❌ Бюджет не может быть отрицательным!")
            return
        
        await Database.update_user_min_budget(message.from_user.id, budget)
        await state.clear()
        
        if budget > 0:
            await message.answer(
                f"✅ Минимальный бюджет установлен: {budget:,}₽\n\n"
                "Теперь я буду присылать только заказы с бюджетом от этой суммы.",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer(
                "✅ Фильтр по бюджету отключён.\n\n"
                "Буду присылать все заказы.",
                reply_markup=get_main_keyboard()
            )
            
    except ValueError:
        await message.answer(
            "❌ Введи число!\n\nНапример: <code>5000</code>",
            parse_mode="HTML"
        )


@router.callback_query(F.data == "toggle_active")
async def toggle_notifications(callback: CallbackQuery):
    """Включение/выключение уведомлений"""
    user = await Database.get_user(callback.from_user.id)
    new_status = not user.is_active
    
    await Database.update_user_active(callback.from_user.id, new_status)
    
    if new_status:
        await callback.answer("✅ Уведомления включены!", show_alert=True)
    else:
        await callback.answer("⏸ Уведомления приостановлены", show_alert=True)
    
    # Обновляем клавиатуру
    from bot.keyboards.keyboards import get_settings_keyboard
    user = await Database.get_user(callback.from_user.id)
    await callback.message.edit_reply_markup(
        reply_markup=get_settings_keyboard(user)
    )