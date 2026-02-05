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
        "design": "/projects/category/dizain/",
        "python": "/projects/category/programmirovanie/",
        "copywriting": "/projects/category/teksty/",
        "marketing": "/projects/category/reklama-i-marketing/",
    }
    
    async def parse_orders(self, category: str) -> List[Dict[str, Any]]:
        orders = []
        
        try:
            path = self.CATEGORY_MAP.get(category, "/projects/")
            url = f"{self.BASE_URL}{path}"
            
            session = await self.get_session()
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            }
            
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status != 200:
                    logger.warning(f"FL.ru returned {response.status}")
                    return orders
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем проекты
                projects = soup.select('[id^="project-item"], .b-post, .project-item')[:15]
                
                for project in projects:
                    try:
                        # Заголовок
                        title_el = project.select_one('a.b-post__link, .project-name a, h2 a')
                        if not title_el:
                            continue
                        
                        title = title_el.get_text(strip=True)
                        href = title_el.get('href', '')
                        
                        if not title or len(title) < 5:
                            continue
                        
                        # ID
                        order_id = re.search(r'/(\d+)', href)
                        order_id = order_id.group(1) if order_id else href
                        
                        # Описание
                        desc_el = project.select_one('.b-post__body, .project-descr')
                        description = desc_el.get_text(strip=True)[:500] if desc_el else ""
                        
                        # Цена
                        price_el = project.select_one('.b-post__price, .project-price, [class*="price"]')
                        budget = price_el.get_text(strip=True) if price_el else "Договорная"
                        
                        full_url = href if href.startswith('http') else f"{self.BASE_URL}{href}"
                        
                        orders.append({
                            'external_id': order_id,
                            'source': self.SOURCE_NAME,
                            'title': title[:200],
                            'description': description,
                            'budget': budget,
                            'budget_value': self._extract_price(budget),
                            'url': full_url,
                            'category': category
                        })
                        
                    except Exception as e:
                        continue
                        
        except Exception as e:
            logger.error(f"FL.ru parse error: {e}")
        
        logger.info(f"FL.ru: found {len(orders)} orders for {category}")
        return orders
    
    def _extract_price(self, text: str) -> int:
        if not text:
            return 0
        numbers = re.findall(r'\d+', text.replace(' ', ''))
        return int(numbers[0]) if numbers else 0
