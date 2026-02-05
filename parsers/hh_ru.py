# parsers/hh_ru.py
import aiohttp
import re
from typing import List, Dict, Any
from .base import BaseParser
import logging

logger = logging.getLogger(__name__)


class HHParser(BaseParser):
    """
    Парсер HeadHunter API для поиска проектной работы.
    Использует официальный API HH.
    """
    
    SOURCE_NAME = "hh"
    BASE_URL = "https://api.hh.ru"
    
    # Маппинг категорий на специализации HH
    CATEGORY_MAP = {
        "design": {
            "text": "дизайнер",
            "professional_role": 34,  # Дизайнер/Художник
        },
        "python": {
            "text": "python разработчик",
            "professional_role": 96,  # Программист
        },
        "copywriting": {
            "text": "копирайтер",
            "professional_role": 124,  # Копирайтер
        },
        "marketing": {
            "text": "маркетолог",
            "professional_role": 70,  # Маркетолог
        },
    }
    
    async def parse_orders(self, category: str) -> List[Dict[str, Any]]:
        orders = []
        
        try:
            cat_config = self.CATEGORY_MAP.get(category, {"text": category})
            
            params = {
                "text": cat_config.get("text", category),
                "area": 113,  # Россия
                "per_page": 20,
                "order_by": "publication_time",
                "schedule": "remote",  # Удалённая работа
                # Можно добавить project work
            }
            
            if "professional_role" in cat_config:
                params["professional_role"] = cat_config["professional_role"]
            
            session = await self.get_session()
            
            async with session.get(
                f"{self.BASE_URL}/vacancies",
                params=params,
                headers={"User-Agent": "FreelanceRadarBot/1.0"}
            ) as response:
                
                if response.status != 200:
                    logger.error(f"HH.ru API returned {response.status}")
                    return orders
                
                data = await response.json()
                
                for item in data.get("items", []):
                    try:
                        # Формируем данные о вакансии
                        external_id = str(item.get("id", ""))
                        title = item.get("name", "Без названия")
                        url = item.get("alternate_url", "")
                        
                        # Описание (краткое, полное нужно запрашивать отдельно)
                        snippet = item.get("snippet", {})
                        description = ""
                        if snippet.get("requirement"):
                            description += snippet["requirement"] + "\n"
                        if snippet.get("responsibility"):
                            description += snippet["responsibility"]
                        
                        # Очищаем от HTML
                        description = re.sub(r'<[^>]+>', '', description)
                        
                        # Зарплата
                        salary = item.get("salary")
                        budget = "Не указана"
                        budget_value = 0
                        
                        if salary:
                            if salary.get("from") and salary.get("to"):
                                budget = f"{salary['from']:,} - {salary['to']:,} {salary.get('currency', 'RUR')}"
                                budget_value = salary["from"]
                            elif salary.get("from"):
                                budget = f"от {salary['from']:,} {salary.get('currency', 'RUR')}"
                                budget_value = salary["from"]
                            elif salary.get("to"):
                                budget = f"до {salary['to']:,} {salary.get('currency', 'RUR')}"
                                budget_value = salary["to"]
                        
                        # Работодатель
                        employer = item.get("employer", {})
                        employer_name = employer.get("name", "")
                        if employer_name:
                            description = f"🏢 {employer_name}\n\n{description}"
                        
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
                        logger.error(f"Error parsing HH vacancy: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error parsing HH.ru: {e}")
        
        return orders