# parsers/freelanceru.py
import aiohttp
import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseParser
import logging

logger = logging.getLogger(__name__)


class FreelanceRuParser(BaseParser):
    SOURCE_NAME = "freelance.ru"
    BASE_URL = "https://freelance.ru"
    
    CATEGORY_MAP = {
        "design": "/projects/?cat=18",
        "python": "/projects/?cat=3",
        "copywriting": "/projects/?cat=15",
        "marketing": "/projects/?cat=13",
    }
    
    async def parse_orders(self, category: str) -> List[Dict[str, Any]]:
        orders = []
        
        try:
            path = self.CATEGORY_MAP.get(category, "/projects/")
            url = f"{self.BASE_URL}{path}"
            
            session = await self.get_session()
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status != 200:
                    logger.warning(f"Freelance.ru returned {response.status}")
                    return orders
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                projects = soup.select('.project, .project-item, [class*="project"]')[:15]
                
                for project in projects:
                    try:
                        title_el = project.select_one('a.project-name, .title a, h2 a')
                        if not title_el:
                            continue
                        
                        title = title_el.get_text(strip=True)
                        href = title_el.get('href', '')
                        
                        if not title or len(title) < 5:
                            continue
                        
                        order_id = re.search(r'/(\d+)', href)
                        order_id = order_id.group(1) if order_id else href
                        
                        price_el = project.select_one('.price, .cost, [class*="price"]')
                        budget = price_el.get_text(strip=True) if price_el else "Договорная"
                        
                        full_url = href if href.startswith('http') else f"{self.BASE_URL}{href}"
                        
                        orders.append({
                            'external_id': order_id,
                            'source': self.SOURCE_NAME,
                            'title': title[:200],
                            'description': '',
                            'budget': budget,
                            'budget_value': self._extract_price(budget),
                            'url': full_url,
                            'category': category
                        })
                        
                    except Exception as e:
                        continue
                        
        except Exception as e:
            logger.error(f"Freelance.ru parse error: {e}")
        
        logger.info(f"Freelance.ru: found {len(orders)} orders for {category}")
        return orders
    
    def _extract_price(self, text: str) -> int:
        if not text:
            return 0
        numbers = re.findall(r'\d+', text.replace(' ', ''))
        return int(numbers[0]) if numbers else 0
