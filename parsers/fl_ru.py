# parsers/fl_ru.py
import aiohttp
import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseParser
import logging

logger = logging.getLogger(__name__)


class FLRuParser(BaseParser):
    SOURCE_NAME = "fl.ru"
    BASE_URL = "https://www.fl.ru"
    
    CATEGORY_MAP = {
        "design": "/projects/?kind=5",  # Дизайн
        "python": "/projects/?kind=1",  # Программирование
        "copywriting": "/projects/?kind=3",  # Тексты
        "marketing": "/projects/?kind=4",  # Реклама и маркетинг
    }
    
    async def parse_orders(self, category: str) -> List[Dict[str, Any]]:
        orders = []
        
        try:
            url_path = self.CATEGORY_MAP.get(category, "/projects/")
            url = f"{self.BASE_URL}{url_path}"
            
            session = await self.get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"FL.ru returned {response.status}")
                    return orders
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем проекты
                projects = soup.find_all('div', class_='b-post')
                
                for project in projects[:20]:
                    try:
                        # Заголовок
                        title_elem = project.find('a', class_='b-post__link')
                        if not title_elem:
                            continue
                        
                        title = title_elem.get_text(strip=True)
                        url = title_elem.get('href', '')
                        if not url.startswith('http'):
                            url = self.BASE_URL + url
                        
                        external_id = re.search(r'/(\d+)', url)
                        external_id = external_id.group(1) if external_id else url
                        
                        # Описание
                        desc_elem = project.find('div', class_='b-post__txt')
                        description = desc_elem.get_text(strip=True) if desc_elem else ""
                        
                        # Бюджет
                        price_elem = project.find('div', class_='b-post__price')
                        budget = price_elem.get_text(strip=True) if price_elem else "Договорная"
                        
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
                        logger.error(f"Error parsing FL.ru project: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error parsing FL.ru: {e}")
        
        return orders