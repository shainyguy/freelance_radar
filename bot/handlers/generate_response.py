# bot/handlers/generate_response.py
from aiogram import Router, F
from aiogram.types import CallbackQuery
from database.db import Database
from services.gigachat import gigachat_service
from database.models import Order
from sqlalchemy import select
from database.db import async_session

router = Router()


@router.callback_query(F.data.startswith("generate:"))
async def generate_response(callback: CallbackQuery):
    user = await Database.get_user(callback.from_user.id)
    
    # Проверяем подписку
    if not user.has_active_subscription():
        await callback.answer(
            "Для генерации откликов нужна активная подписка!",
            show_alert=True
        )
        return
    
    order_id = int(callback.data.split(":")[1])
    
    # Получаем заказ из БД
    async with async_session() as session:
        result = await session.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
    
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    await callback.answer("✨ Генерирую отклик...")
    
    # Показываем сообщение о загрузке
    loading_msg = await callback.message.reply("⏳ Генерирую идеальный отклик...")
    
    try:
        # Генерируем отклик
        response_text = await gigachat_service.generate_response(
            order.title,
            order.description
        )
        
        await loading_msg.edit_text(
            f"""
✨ <b>Готовый отклик:</b>

{response_text}

<i>Скопируй текст и отправь заказчику!</i>
""",
            parse_mode="HTML"
        )
        
    except Exception as e:
        await loading_msg.edit_text(
            "❌ Не удалось сгенерировать отклик. Попробуйте позже."
        )


@router.callback_query(F.data.startswith("hide:"))
async def hide_order(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer("Заказ скрыт")