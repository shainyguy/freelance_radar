# bot/middlewares/subscription.py
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from database.db import Database
import logging

logger = logging.getLogger(__name__)


class SubscriptionMiddleware(BaseMiddleware):
    """
    Middleware для проверки подписки пользователя.
    Пропускает только пользователей с активной подпиской.
    """
    
    # Команды/действия, доступные без подписки
    FREE_COMMANDS = {'/start', '/help', 'start_trial', 'buy_subscription', 'check_payment'}
    FREE_TEXTS = {'💳 Подписка', '👤 Профиль'}
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        # Определяем user_id и проверяем тип события
        user_id = None
        is_free_action = False
        
        if isinstance(event, Message):
            user_id = event.from_user.id
            
            # Проверяем, свободная ли это команда
            if event.text:
                if event.text.startswith('/'):
                    cmd = event.text.split()[0]
                    is_free_action = cmd in self.FREE_COMMANDS
                else:
                    is_free_action = event.text in self.FREE_TEXTS
                    
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            
            # Проверяем callback data
            if event.data:
                is_free_action = any(
                    event.data.startswith(free) 
                    for free in self.FREE_COMMANDS
                )
        
        if not user_id:
            return await handler(event, data)
        
        # Если это свободное действие - пропускаем
        if is_free_action:
            return await handler(event, data)
        
        # Проверяем подписку
        user = await Database.get_user(user_id)
        
        if not user:
            # Новый пользователь - пропускаем (start создаст его)
            return await handler(event, data)
        
        if user.has_active_subscription():
            # Подписка активна - пропускаем
            return await handler(event, data)
        
        # Подписки нет - блокируем и уведомляем
        no_sub_text = (
            "⚠️ <b>Подписка не активна</b>\n\n"
            "Для использования бота нужна подписка.\n"
            "Нажми 💳 Подписка чтобы оформить."
        )
        
        if isinstance(event, Message):
            await event.answer(no_sub_text, parse_mode="HTML")
        elif isinstance(event, CallbackQuery):
            await event.answer(
                "Подписка не активна! Оформите подписку.", 
                show_alert=True
            )
        
        return None  # Не вызываем handler