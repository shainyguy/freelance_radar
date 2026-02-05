# parsers/telegram_channels.py
from typing import List, Dict, Any
from .base import BaseParser
import logging
from telethon import TelegramClient
from telethon.tl.types import Message
import re

logger = logging.getLogger(__name__)


class TelegramChannelsParser(BaseParser):
    """
    Парсер Telegram-каналов с заказами.
    Требует отдельную настройку Telethon client.
    """
    
    SOURCE_NAME = "telegram"
    
    # Популярные каналы с заказами
    CHANNELS = {
        "design": [
            "@designjobsru",
            "@design_hunters",
            "@fordesigners",
        ],
        "python": [
            "@pythondevjob",
            "@python_jobs_ru",
            "@devjobs",
        ],
        "copywriting": [
            "@textjob",
            "@copyjobs",
        ],
    }
    
    def __init__(self, client: TelegramClient = None):
        super().__init__()
        self.client = client
    
    async def parse_orders(self, category: str) -> List[Dict[str, Any]]:
        orders = []
        
        if not self.client:
            logger.warning("Telegram client not configured")
            return orders
        
        channels = self.CHANNELS.get(category, [])
        
        for channel in channels:
            try:
                async for message in self.client.iter_messages(channel, limit=10):
                    if not isinstance(message, Message) or not message.text:
                        continue
                    
                    # Простая фильтрация - ищем сообщения похожие на заказы
                    text = message.text
                    if len(text) < 50:  # Слишком короткие пропускаем
                        continue
                    
                    # Ищем признаки заказа
                    order_keywords = ['ищу', 'требуется', 'нужен', 'заказ', 'бюджет', 'оплата', 'проект']
                    if not any(kw in text.lower() for kw in order_keywords):
                        continue
                    
                    # Извлекаем бюджет если есть
                    budget_match = re.search(r'(\d+[\s]*[кkКK]?[\s]*(?:руб|₽|rub|р\b))', text)
                    budget = budget_match.group(1) if budget_match else "Не указан"
                    
                    budget_value = 0
                    if budget_match:
                        numbers = re.findall(r'\d+', budget.replace(' ', ''))
                        if numbers:
                            budget_value = int(numbers[0])
                            if 'к' in budget.lower() or 'k' in budget.lower():
                                budget_value *= 1000
                    
                    orders.append({
                        'external_id': f"{channel}_{message.id}",
                        'source': self.SOURCE_NAME,
                        'title': text[:100] + "..." if len(text) > 100 else text,
                        'description': text[:4000],
                        'budget': budget,
                        'budget_value': budget_value,
                        'url': f"https://t.me/{channel.replace('@', '')}/{message.id}",
                        'category': category
                    })
                    
            except Exception as e:
                logger.error(f"Error parsing Telegram channel {channel}: {e}")
                continue
        
        return orders