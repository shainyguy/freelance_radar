# services/price_calculator.py
import re
from typing import Dict


class PriceCalculator:
    """Умный калькулятор цены"""
    
    # Рыночные ставки по категориям
    MARKET_RATES = {
        "python": {
            "hourly": {"min": 1500, "avg": 2500, "max": 5000},
            "project": {"min": 10000, "avg": 35000, "max": 150000},
            "keywords": ["бот", "парсер", "api", "django", "flask", "fastapi", "telegram"]
        },
        "design": {
            "hourly": {"min": 800, "avg": 1500, "max": 3500},
            "project": {"min": 5000, "avg": 20000, "max": 100000},
            "keywords": ["лого", "лендинг", "баннер", "ui", "ux", "figma", "дизайн"]
        },
        "copywriting": {
            "per_1000": {"min": 200, "avg": 500, "max": 1500},
            "project": {"min": 2000, "avg": 8000, "max": 30000},
            "keywords": ["текст", "статья", "копирайт", "контент", "seo"]
        },
        "marketing": {
            "hourly": {"min": 1000, "avg": 2000, "max": 5000},
            "project": {"min": 15000, "avg": 50000, "max": 300000},
            "keywords": ["smm", "таргет", "реклама", "продвижение", "маркетинг"]
        },
    }
    
    # Множители сложности
    COMPLEXITY_PATTERNS = {
        "high": [
            (r'highload|высоконагруженн', 1.8),
            (r'машинн\w+\s*обучен|ml|ai|нейросет', 2.0),
            (r'блокчейн|crypto|web3', 1.7),
            (r'интеграци\w+.*api', 1.4),
            (r'с\s*нуля|полный\s*цикл', 1.5),
            (r'срочно|за\s*\d+\s*дн|быстро', 1.3),
        ],
        "medium": [
            (r'доработк|изменени|правк', 0.8),
            (r'стандарт|типов', 1.0),
            (r'по\s*образцу|по\s*примеру', 0.9),
        ],
        "low": [
            (r'прост\w+|базов\w+|минимальн', 0.6),
            (r'шаблон|готов\w+\s*решени', 0.5),
            (r'небольш\w+|мелк', 0.7),
        ],
    }
    
    async def calculate(self, title: str, description: str, category: str, 
                       client_budget: int = 0) -> Dict:
        """Рассчитывает рекомендуемую цену"""
        text = f"{title} {description}".lower()
        
        # Получаем базовые ставки
        rates = self.MARKET_RATES.get(category, self.MARKET_RATES["python"])
        base_rates = rates.get("project", rates.get("hourly", {"min": 1000, "avg": 3000, "max": 10000}))
        
        # Определяем сложность и множитель
        multiplier, complexity = self._detect_complexity(text)
        
        # Рассчитываем цены
        recommended_min = int(base_rates["min"] * multiplier)
        recommended_avg = int(base_rates["avg"] * multiplier)
        recommended_max = int(base_rates["max"] * multiplier)
        
        # Анализируем бюджет заказчика
        budget_analysis = self._analyze_budget(client_budget, recommended_min, recommended_avg, recommended_max)
        
        # Формируем совет
        tip = self._generate_tip(budget_analysis, client_budget, recommended_avg, complexity)
        
        return {
            "recommended_min": recommended_min,
            "recommended_avg": recommended_avg,
            "recommended_max": recommended_max,
            "complexity": complexity,
            "complexity_text": {"high": "🔴 Высокая", "medium": "🟡 Средняя", "low": "🟢 Низкая"}[complexity],
            "multiplier": multiplier,
            "budget_analysis": budget_analysis,
            "tip": tip,
            "negotiation_range": f"{recommended_min:,} — {recommended_max:,} ₽".replace(",", " "),
            "sweet_spot": f"{recommended_avg:,} ₽".replace(",", " "),
        }
    
    def _detect_complexity(self, text: str) -> tuple:
        """Определяет сложность и множитель"""
        max_multiplier = 1.0
        detected_complexity = "medium"
        
        for complexity, patterns in self.COMPLEXITY_PATTERNS.items():
            for pattern, mult in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    if mult > max_multiplier:
                        max_multiplier = mult
                        detected_complexity = complexity
                    elif mult < 1.0 and max_multiplier == 1.0:
                        max_multiplier = mult
                        detected_complexity = complexity
        
        return max_multiplier, detected_complexity
    
    def _analyze_budget(self, client_budget: int, min_price: int, avg_price: int, max_price: int) -> Dict:
        """Анализирует бюджет клиента"""
        if not client_budget:
            return {"status": "unknown", "text": "Бюджет не указан", "emoji": "❓"}
        
        if client_budget < min_price * 0.5:
            return {"status": "too_low", "text": "Сильно ниже рынка", "emoji": "🔴"}
        elif client_budget < min_price:
            return {"status": "below", "text": "Ниже рынка", "emoji": "🟡"}
        elif client_budget <= avg_price:
            return {"status": "normal", "text": "В рынке", "emoji": "🟢"}
        elif client_budget <= max_price:
            return {"status": "good", "text": "Хороший бюджет", "emoji": "💚"}
        else:
            return {"status": "generous", "text": "Щедрый бюджет!", "emoji": "💎"}
    
    def _generate_tip(self, analysis: Dict, client_budget: int, avg_price: int, complexity: str) -> str:
        """Генерирует персональный совет"""
        status = analysis["status"]
        
        tips = {
            "too_low": f"⚠️ Бюджет сильно ниже рынка. Предложи {avg_price:,}₽ или упрощённый вариант за {client_budget:,}₽",
            "below": f"💡 Можешь запросить {avg_price:,}₽, обосновав качеством и опытом",
            "normal": "✅ Адекватный бюджет. Смело откликайся!",
            "good": "💪 Хороший бюджет! Можешь предложить доп. услуги",
            "generous": "🎯 Отличный бюджет! Предложи премиум-решение с поддержкой",
            "unknown": f"💡 Рекомендуемая цена: {avg_price:,}₽ (сложность: {complexity})",
        }
        
        return tips.get(status, tips["unknown"]).replace(",", " ")


price_calculator = PriceCalculator()
