# services/scheduler.py
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database.db import Database
from config import Config
import logging
from aiogram import Bot

logger = logging.getLogger(__name__)


class OrderScheduler:
    """Планировщик для мониторинга бирж"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.categories = ["design", "python", "copywriting", "marketing"]
    
    async def check_new_orders(self):
        """Проверяет новые заказы на всех биржах"""
        # Импортируем здесь, чтобы избежать circular import
        from parsers import ALL_PARSERS
        from bot.keyboards.keyboards import get_order_keyboard
        
        logger.info("Checking for new orders...")
        
        for parser in ALL_PARSERS:
            for category in self.categories:
                try:
                    orders = await parser.parse_orders(category)
                    
                    for order_data in orders:
                        # Сохраняем заказ (если новый)
                        order = await Database.save_order(order_data)
                        
                        if order:  # Новый заказ
                            # Находим пользователей с этой категорией
                            users = await Database.get_active_users_for_category(category)
                            
                            for user in users:
                                # Проверяем минимальный бюджет
                                if user.min_budget and order.budget_value:
                                    if order.budget_value < user.min_budget:
                                        continue
                                
                                # Отправляем уведомление
                                await self._send_order_notification(user, order, get_order_keyboard)
                                
                except Exception as e:
                    logger.error(f"Error in scheduler for {parser.SOURCE_NAME}/{category}: {e}")
        
        # Закрываем сессии парсеров
        for parser in ALL_PARSERS:
            await parser.close()
    
    async def _send_order_notification(self, user, order, get_order_keyboard):
        """Отправляет уведомление о новом заказе"""
        try:
            # Проверяем, не отправляли ли уже
            if await Database.is_order_sent(user.id, order.id):
                return
            
            source_emoji = {
                "kwork": "🟢",
                "fl.ru": "🔵",
                "habr_freelance": "🟣",
                "hh": "🔴",
                "telegram": "📱"
            }
            
            emoji = source_emoji.get(order.source, "📋")
            desc = order.description[:500] if order.description else ""
            
            text = f"""
{emoji} <b>Новый заказ на {order.source}</b>

📌 <b>{order.title}</b>

{desc}{'...' if len(order.description or '') > 500 else ''}

💰 Бюджет: {order.budget}

🔗 <a href="{order.url}">Открыть заказ</a>
"""
            
            await self.bot.send_message(
                user.telegram_id,
                text,
                parse_mode="HTML",
                reply_markup=get_order_keyboard(order.id, order.url),
                disable_web_page_preview=True
            )
            
            await Database.mark_order_sent(user.id, order.id)
            
        except Exception as e:
            logger.error(f"Error sending notification to {user.telegram_id}: {e}")
    
    def start(self):
        """Запускает планировщик"""
        self.scheduler.add_job(
            self.check_new_orders,
            'interval',
            seconds=Config.PARSE_INTERVAL,
            id='check_orders',
            max_instances=1
        )
        self.scheduler.start()
        logger.info(f"Scheduler started with interval {Config.PARSE_INTERVAL}s")
    
    def stop(self):
        """Останавливает планировщик"""
        self.scheduler.shutdown()
