# parsers/habr_freelance.py
import aiohttp
import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseParser
import logging

logger = logging.getLogger(__name__)


class HabrFreelanceParser(BaseParser):
    """Habr Freelance закрылся, возвращаем пустой список"""
    
    SOURCE_NAME = "habr_freelance"
    BASE_URL = "https://freelance.habr.com"
    
    async def parse_orders(self, category: str) -> List[Dict[str, Any]]:
        # Habr Freelance больше не работает (410 Gone)
        # Возвращаем пустой список
        logger.debug("Habr Freelance is closed, skipping...")
        return []
