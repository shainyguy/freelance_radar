# parsers/telegram_channels.py
"""
Парсер Telegram-каналов.
Требует настройки Telethon с API ID и API Hash.
Пока отключён.
"""

from typing import List, Dict, Any
from .base import BaseParser
import logging

logger = logging.getLogger(__name__)


class TelegramChannelsParser(BaseParser):
    """
    Парсер Telegram-каналов с заказами.
    
    Для работы требуется:
    1. Получить API ID и API Hash на https://my.telegram.org
    2. Установить telethon: pip install telethon
    3. Настроить авторизацию
    
    Пока возвращает пустой список.
    """
    
    SOURCE_NAME = "telegram"
    
    CHANNELS = {
        "design": [
            "@designjobsru",
            "@design_hunters",
        ],
        "python": [
            "@pythondevjob",
            "@python_jobs_ru",
        ],
        "copywriting": [
            "@textjob",
        ],
    }
    
    async def parse_orders(self, category: str) -> List[Dict[str, Any]]:
        """Пока не реализовано - возвращает пустой список"""
        logger.debug("TelegramChannelsParser is not configured, skipping...")
        return []
