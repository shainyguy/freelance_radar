# parsers/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any
import aiohttp
import logging

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Базовый класс для парсеров бирж"""
    
    SOURCE_NAME = "base"
    BASE_URL = ""
    
    def __init__(self):
        self.session = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    @abstractmethod
    async def parse_orders(self, category: str) -> List[Dict[str, Any]]:
        """
        Парсит заказы по категории.
        Возвращает список словарей с ключами:
        - external_id: str
        - source: str
        - title: str
        - description: str
        - budget: str
        - budget_value: int (optional)
        - url: str
        - category: str
        """
        pass
    
    def normalize_category(self, category: str) -> str:
        """Преобразует нашу категорию в категорию биржи"""
        return category