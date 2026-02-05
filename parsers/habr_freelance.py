# parsers/habr_freelance.py
import aiohttp
import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseParser
import logging

logger = logging.getLogger(__name__)


class HabrFreelanceParser(BaseParser):
    SOURCE_NAME = "habr_freelance"
    BASE_URL = "https://freelance.habr.com"
    
    CATEGORY_MAP = {
        "design": "/tasks?categories=design_creative",
        "python": "/tasks?categories=development_backend",
        "copywriting": "/tasks?categories=marketing_seo",
        "marketing": "/tasks?categories=marketing_smm",
    }
    
    async def parse_orders(self, category: str) -> List[Dict[str, Any]]:
        orders = []
        
        try:
            url_path = self.CATEGORY_MAP.get(category, "/tasks")
            url = f"{self.BASE_URL}{url_path}"
            
            session = await self.get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Habr Freelance returned {response.status}")
                    return orders
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем задачи
                tasks = soup.find_all('article', class_='task')
                
                for task in tasks[:20]:
                    try:
                        # Заголовок
                        title_elem = task.find('a', class_='task__title')
                        if not title_elem:
                            continue
                        
                        title = title_elem.get_text(strip=True)
                        url = title_elem.get('href', '')
                        if not url.startswith('http'):
                            url = self.BASE_URL + url
                        
                        external_id = re.search(r'/task/(\d+)', url)
                        external_id = external_id.group(1) if external_id else url
                        
                        # Описание
                        desc_elem = task.find('div', class_='task__description')
                        description = desc_elem.get_text(strip=True) if desc_elem else ""
                        
                        # Бюджет
                        price_elem = task.find('span', class_='task__price')
                        budget = price_elem.get_text(strip=True) if price_elem else "По договорённости"
                        
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
                        logger.error(f"Error parsing Habr task: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error parsing Habr Freelance: {e}")
        
        return orders