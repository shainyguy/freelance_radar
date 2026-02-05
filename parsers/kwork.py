# parsers/kwork.py
import aiohttp
import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseParser
import logging

logger = logging.getLogger(__name__)


class KworkParser(BaseParser):
    SOURCE_NAME = "kwork"
    BASE_URL = "https://kwork.ru"
    
    CATEGORY_MAP = {
        "design": "/projects?c=11",  # Дизайн
        "python": "/projects?c=41",  # Программирование
        "copywriting": "/projects?c=15",  # Тексты
        "marketing": "/projects?c=33",  # Маркетинг
        "video": "/projects?c=19",  # Видео
        "audio": "/projects?c=21",  # Аудио
    }
    
    async def parse_orders(self, category: str) -> List[Dict[str, Any]]:
        orders = []
        
        try:
            url_path = self.CATEGORY_MAP.get(category, "/projects")
            url = f"{self.BASE_URL}{url_path}&a=1"  # a=1 - сортировка по новым
            
            session = await self.get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Kwork returned {response.status}")
                    return orders
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем карточки проектов
                project_cards = soup.find_all('div', class_='card__content')
                
                for card in project_cards[:20]:  # Берём 20 последних
                    try:
                        # Заголовок и ссылка
                        title_elem = card.find('a', class_='wants-card__header-title')
                        if not title_elem:
                            continue
                        
                        title = title_elem.get_text(strip=True)
                        url = self.BASE_URL + title_elem.get('href', '')
                        
                        # Извлекаем ID из URL
                        external_id = re.search(r'/(\d+)', url)
                        external_id = external_id.group(1) if external_id else url
                        
                        # Описание
                        desc_elem = card.find('div', class_='wants-card__description-text')
                        description = desc_elem.get_text(strip=True) if desc_elem else ""
                        
                        # Бюджет
                        price_elem = card.find('div', class_='wants-card__price')
                        budget = price_elem.get_text(strip=True) if price_elem else "Не указан"
                        
                        # Парсим числовое значение бюджета
                        budget_value = 0
                        if budget:
                            numbers = re.findall(r'\d+', budget.replace(' ', ''))
                            if numbers:
                                budget_value = int(numbers[0])
                        
                        orders.append({
                            'external_id': external_id,
                            'source': self.SOURCE_NAME,
                            'title': title,
                            'description': description[:4000],
                            'budget': budget,
                            'budget_value': budget_value,
                            'url': url,
                            'category': category
                        })
                        
                    except Exception as e:
                        logger.error(f"Error parsing Kwork card: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error parsing Kwork: {e}")
        
        return orders