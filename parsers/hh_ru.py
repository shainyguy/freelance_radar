# parsers/hh_ru.py
import aiohttp
from typing import List, Dict, Any
from .base import BaseParser
import logging

logger = logging.getLogger(__name__)


class HHParser(BaseParser):
    SOURCE_NAME = "hh"
    API_URL = "https://api.hh.ru/vacancies"
    
    CATEGORY_MAP = {
        "design": {"text": "дизайнер", "professional_role": 34},
        "python": {"text": "python", "professional_role": 96},
        "copywriting": {"text": "копирайтер", "professional_role": 124},
        "marketing": {"text": "маркетолог", "professional_role": 70},
    }
    
    async def parse_orders(self, category: str) -> List[Dict[str, Any]]:
        orders = []
        
        try:
            config = self.CATEGORY_MAP.get(category, {"text": category})
            
            params = {
                "text": config.get("text", category),
                "area": 113,  # Россия
                "per_page": 20,
                "order_by": "publication_time",
                "schedule": "remote",
            }
            
            session = await self.get_session()
            
            async with session.get(
                self.API_URL,
                params=params,
                headers={"User-Agent": "FreelanceRadar/1.0"},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                
                if response.status != 200:
                    logger.warning(f"HH.ru returned {response.status}")
                    return orders
                
                data = await response.json()
                
                for item in data.get("items", [])[:15]:
                    try:
                        # Зарплата
                        salary = item.get("salary")
                        budget = "Не указана"
                        budget_value = 0
                        
                        if salary:
                            currency = salary.get("currency", "RUR")
                            if salary.get("from") and salary.get("to"):
                                budget = f"{salary['from']:,} - {salary['to']:,} {currency}".replace(',', ' ')
                                budget_value = salary["from"]
                            elif salary.get("from"):
                                budget = f"от {salary['from']:,} {currency}".replace(',', ' ')
                                budget_value = salary["from"]
                            elif salary.get("to"):
                                budget = f"до {salary['to']:,} {currency}".replace(',', ' ')
                                budget_value = salary["to"]
                        
                        # Описание
                        snippet = item.get("snippet", {})
                        description = ""
                        if snippet.get("requirement"):
                            description = snippet["requirement"]
                        if snippet.get("responsibility"):
                            description += "\n" + snippet["responsibility"]
                        
                        # Убираем HTML теги
                        import re
                        description = re.sub(r'<[^>]+>', '', description)
                        
                        # Работодатель
                        employer = item.get("employer", {}).get("name", "")
                        if employer:
                            description = f"🏢 {employer}\n\n{description}"
                        
                        orders.append({
                            'external_id': str(item.get("id", "")),
                            'source': self.SOURCE_NAME,
                            'title': item.get("name", "Без названия"),
                            'description': description[:2000],
                            'budget': budget,
                            'budget_value': budget_value,
                            'url': item.get("alternate_url", ""),
                            'category': category
                        })
                        
                    except Exception as e:
                        continue
                        
        except Exception as e:
            logger.error(f"HH.ru parse error: {e}")
        
        logger.info(f"HH.ru: found {len(orders)} orders for {category}")
        return orders
