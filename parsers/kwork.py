# parsers/kwork.py
import aiohttp
import re
import json
from typing import List, Dict, Any
from .base import BaseParser
import logging

logger = logging.getLogger(__name__)


class KworkParser(BaseParser):
    SOURCE_NAME = "kwork"
    BASE_URL = "https://kwork.ru"
    
    # Используем API Kwork (более надёжно)
    API_URL = "https://kwork.ru/api/want/getwants"
    
    CATEGORY_MAP = {
        "design": 11,
        "python": 41,
        "copywriting": 15,
        "marketing": 33,
    }
    
    async def parse_orders(self, category: str) -> List[Dict[str, Any]]:
        orders = []
        
        try:
            cat_id = self.CATEGORY_MAP.get(category, 41)
            
            session = await self.get_session()
            
            # Пробуем через главную страницу проектов
            url = f"{self.BASE_URL}/projects?c={cat_id}"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status != 200:
                    logger.warning(f"Kwork returned {response.status}")
                    return orders
                
                html = await response.text()
                
                # Ищем JSON с данными в HTML
                # Kwork хранит данные в window.__INITIAL_STATE__
                match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?});', html, re.DOTALL)
                
                if match:
                    try:
                        data = json.loads(match.group(1))
                        wants = data.get('wantsStore', {}).get('wants', [])
                        
                        for item in wants[:15]:
                            try:
                                order_id = str(item.get('id', ''))
                                title = item.get('name', '')
                                description = item.get('description', '')
                                
                                price_from = item.get('priceFrom', 0)
                                price_to = item.get('priceTo', 0)
                                
                                if price_from and price_to:
                                    budget = f"{price_from:,} - {price_to:,} ₽".replace(',', ' ')
                                elif price_from:
                                    budget = f"от {price_from:,} ₽".replace(',', ' ')
                                else:
                                    budget = "Договорная"
                                
                                orders.append({
                                    'external_id': order_id,
                                    'source': self.SOURCE_NAME,
                                    'title': title,
                                    'description': description[:2000],
                                    'budget': budget,
                                    'budget_value': price_from or price_to or 0,
                                    'url': f"{self.BASE_URL}/projects/{order_id}",
                                    'category': category
                                })
                            except Exception as e:
                                continue
                    except json.JSONDecodeError:
                        pass
                
                # Fallback: парсим HTML
                if not orders:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    cards = soup.select('.want-card, .kwork-card, [class*="want"]')[:15]
                    
                    for card in cards:
                        try:
                            link = card.select_one('a[href*="/projects/"]')
                            if not link:
                                continue
                            
                            title = link.get_text(strip=True)
                            href = link.get('href', '')
                            
                            if not title or len(title) < 10:
                                continue
                            
                            order_id = re.search(r'/projects/(\d+)', href)
                            order_id = order_id.group(1) if order_id else href
                            
                            price_el = card.select_one('[class*="price"], .price')
                            budget = price_el.get_text(strip=True) if price_el else "Договорная"
                            
                            orders.append({
                                'external_id': order_id,
                                'source': self.SOURCE_NAME,
                                'title': title[:200],
                                'description': '',
                                'budget': budget,
                                'budget_value': self._extract_price(budget),
                                'url': f"{self.BASE_URL}{href}" if href.startswith('/') else href,
                                'category': category
                            })
                        except Exception as e:
                            continue
                            
        except Exception as e:
            logger.error(f"Kwork parse error: {e}")
        
        logger.info(f"Kwork: found {len(orders)} orders for {category}")
        return orders
    
    def _extract_price(self, text: str) -> int:
        if not text:
            return 0
        numbers = re.findall(r'\d+', text.replace(' ', ''))
        return int(numbers[0]) if numbers else 0
