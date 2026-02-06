# services/achievements.py
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class AchievementSystem:
    """Система геймификации и достижений"""
    
    ACHIEVEMENTS = {
        # Первые шаги
        "first_blood": {
            "name": "Первая кровь",
            "description": "Первый просмотр заказа",
            "icon": "🎯",
            "xp": 10,
            "rarity": "common"
        },
        "first_response": {
            "name": "Первый отклик",
            "description": "Сгенерировал первый AI-отклик",
            "icon": "✨",
            "xp": 25,
            "rarity": "common"
        },
        "first_deal": {
            "name": "Первая сделка",
            "description": "Добавил первую сделку в CRM",
            "icon": "🤝",
            "xp": 50,
            "rarity": "uncommon"
        },
        
        # Активность
        "early_bird": {
            "name": "Ранняя пташка",
            "description": "Откликнулся на заказ в первые 10 минут",
            "icon": "🐤",
            "xp": 30,
            "rarity": "uncommon"
        },
        "night_owl": {
            "name": "Ночная сова",
            "description": "Активен после полуночи",
            "icon": "🦉",
            "xp": 15,
            "rarity": "common"
        },
        "streak_3": {
            "name": "Три дня подряд",
            "description": "Активен 3 дня подряд",
            "icon": "🔥",
            "xp": 30,
            "rarity": "common"
        },
        "streak_7": {
            "name": "Неделя в деле",
            "description": "Активен 7 дней подряд",
            "icon": "⚡",
            "xp": 75,
            "rarity": "uncommon"
        },
        "streak_30": {
            "name": "Месяц без перерыва",
            "description": "Активен 30 дней подряд",
            "icon": "💪",
            "xp": 200,
            "rarity": "rare"
        },
        
        # Заработок
        "first_10k": {
            "name": "Первые 10К",
            "description": "Заработал 10 000 ₽",
            "icon": "💵",
            "xp": 50,
            "rarity": "uncommon"
        },
        "first_50k": {
            "name": "Полтинник",
            "description": "Заработал 50 000 ₽",
            "icon": "💰",
            "xp": 100,
            "rarity": "rare"
        },
        "first_100k": {
            "name": "Сотка",
            "description": "Заработал 100 000 ₽",
            "icon": "💎",
            "xp": 200,
            "rarity": "epic"
        },
        "millionaire": {
            "name": "Миллионер",
            "description": "Заработал 1 000 000 ₽",
            "icon": "👑",
            "xp": 1000,
            "rarity": "legendary"
        },
        
        # Режимы
        "hunter": {
            "name": "Охотник",
            "description": "Включил режим Хищник",
            "icon": "🦁",
            "xp": 20,
            "rarity": "common"
        },
        "pro_subscriber": {
            "name": "PRO",
            "description": "Оформил PRO подписку",
            "icon": "⭐",
            "xp": 100,
            "rarity": "rare"
        },
        
        # Мастерство
        "ai_master_10": {
            "name": "AI-ученик",
            "description": "Сгенерировал 10 откликов",
            "icon": "🤖",
            "xp": 25,
            "rarity": "common"
        },
        "ai_master_50": {
            "name": "AI-мастер",
            "description": "Сгенерировал 50 откликов",
            "icon": "🧠",
            "xp": 75,
            "rarity": "uncommon"
        },
        "ai_master_200": {
            "name": "AI-гуру",
            "description": "Сгенерировал 200 откликов",
            "icon": "🔮",
            "xp": 200,
            "rarity": "rare"
        },
        
        # Сделки
        "deal_master_5": {
            "name": "В деле",
            "description": "Завершил 5 сделок",
            "icon": "📋",
            "xp": 50,
            "rarity": "uncommon"
        },
        "deal_master_20": {
            "name": "Профессионал",
            "description": "Завершил 20 сделок",
            "icon": "🏆",
            "xp": 150,
            "rarity": "rare"
        },
        "deal_master_100": {
            "name": "Легенда фриланса",
            "description": "Завершил 100 сделок",
            "icon": "🌟",
            "xp": 500,
            "rarity": "legendary"
        },
        
        # Особые
        "whale_hunter": {
            "name": "Охотник на китов",
            "description": "Взял заказ на 100K+",
            "icon": "🐋",
            "xp": 150,
            "rarity": "epic"
        },
        "diversifier": {
            "name": "Диверсификатор",
            "description": "Работал в 4 категориях",
            "icon": "🎨",
            "xp": 75,
            "rarity": "uncommon"
        },
        "scam_detector": {
            "name": "Детектив",
            "description": "Использовал детектор кидал 10 раз",
            "icon": "🕵️",
            "xp": 40,
            "rarity": "uncommon"
        },
    }
    
    LEVELS = [
        {"level": 1, "name": "Новичок", "min_xp": 0, "icon": "🌱", "color": "#95a5a6"},
        {"level": 2, "name": "Ученик", "min_xp": 50, "icon": "📚", "color": "#3498db"},
        {"level": 3, "name": "Фрилансер", "min_xp": 150, "icon": "💼", "color": "#2ecc71"},
        {"level": 4, "name": "Специалист", "min_xp": 300, "icon": "⭐", "color": "#9b59b6"},
        {"level": 5, "name": "Эксперт", "min_xp": 500, "icon": "🏆", "color": "#e74c3c"},
        {"level": 6, "name": "Мастер", "min_xp": 800, "icon": "👑", "color": "#f39c12"},
        {"level": 7, "name": "Легенда", "min_xp": 1200, "icon": "🔥", "color": "#e91e63"},
        {"level": 8, "name": "Гуру", "min_xp": 2000, "icon": "💎", "color": "#00bcd4"},
    ]
    
    RARITY_COLORS = {
        "common": "#95a5a6",
        "uncommon": "#2ecc71",
        "rare": "#3498db",
        "epic": "#9b59b6",
        "legendary": "#f39c12",
    }
    
    def get_achievement(self, achievement_id: str) -> Optional[Dict]:
        """Получить информацию о достижении"""
        achievement = self.ACHIEVEMENTS.get(achievement_id)
        if achievement:
            return {
                "id": achievement_id,
                **achievement,
                "color": self.RARITY_COLORS.get(achievement.get("rarity", "common"))
            }
        return None
    
    def get_all_achievements(self, unlocked: List[str] = None) -> List[Dict]:
        """Получить все достижения с отметкой разблокированных"""
        unlocked = unlocked or []
        result = []
        for aid, data in self.ACHIEVEMENTS.items():
            result.append({
                "id": aid,
                **data,
                "unlocked": aid in unlocked,
                "color": self.RARITY_COLORS.get(data.get("rarity", "common"))
            })
        return result
    
    def get_level_info(self, xp: int) -> Dict:
        """Получить информацию об уровне"""
        current_level = self.LEVELS[0]
        next_level = self.LEVELS[1] if len(self.LEVELS) > 1 else None
        
        for i, level in enumerate(self.LEVELS):
            if xp >= level["min_xp"]:
                current_level = level
                next_level = self.LEVELS[i + 1] if i + 1 < len(self.LEVELS) else None
        
        # Прогресс до следующего уровня
        if next_level:
            progress_xp = xp - current_level["min_xp"]
            needed_xp = next_level["min_xp"] - current_level["min_xp"]
            progress_percent = min(100, int((progress_xp / needed_xp) * 100))
        else:
            progress_percent = 100
            progress_xp = 0
            needed_xp = 0
        
        return {
            "current": current_level,
            "next": next_level,
            "xp": xp,
            "progress_percent": progress_percent,
            "progress_xp": progress_xp,
            "needed_xp": needed_xp,
        }
    
    def check_achievements(self, user) -> List[str]:
        """Проверить и разблокировать новые достижения"""
        unlocked = user.achievements or []
        new_achievements = []
        
        # Проверяем каждое достижение
        checks = {
            "first_blood": user.orders_viewed >= 1,
            "first_response": user.responses_sent >= 1,
            "first_deal": user.deals_completed >= 1,
            "hunter": getattr(user, 'predator_mode', False),
            "streak_3": user.streak_days >= 3,
            "streak_7": user.streak_days >= 7,
            "streak_30": user.streak_days >= 30,
            "first_10k": user.total_earnings >= 10000,
            "first_50k": user.total_earnings >= 50000,
            "first_100k": user.total_earnings >= 100000,
            "millionaire": user.total_earnings >= 1000000,
            "ai_master_10": user.responses_sent >= 10,
            "ai_master_50": user.responses_sent >= 50,
            "ai_master_200": user.responses_sent >= 200,
            "deal_master_5": user.deals_completed >= 5,
            "deal_master_20": user.deals_completed >= 20,
            "deal_master_100": user.deals_completed >= 100,
            "pro_subscriber": user.is_pro() if hasattr(user, 'is_pro') else False,
        }
        
        for achievement_id, condition in checks.items():
            if condition and achievement_id not in unlocked:
                new_achievements.append(achievement_id)
        
        return new_achievements


achievements = AchievementSystem()
