# services/smart_alerts.py
from typing import Dict, Tuple
from services.scam_detector import scam_detector


class SmartAlerts:
    """Умная система приоритетных уведомлений"""
    
    async def analyze_order(self, order: Dict, user) -> Dict:
        """Полный анализ заказа для уведомления"""
        priority_score = 0
        reasons = []
        
        budget = order.get('budget_value', 0)
        
        # 1. Высокий бюджет
        if budget >= 100000:
            priority_score += 60
            reasons.append("💎 Премиум заказ (100K+)")
        elif budget >= 50000:
            priority_score += 45
            reasons.append("🔥 Жирный заказ (50K+)")
        elif budget >= 30000:
            priority_score += 30
            reasons.append("💰 Хороший бюджет (30K+)")
        elif budget >= 15000:
            priority_score += 15
            reasons.append("💵 Нормальный бюджет")
        
        # 2. Совпадение категории
        user_categories = getattr(user, 'categories', None) or []
        if order.get('category') in user_categories:
            priority_score += 25
            reasons.append("🎯 Твоя категория")
        
        # 3. Минимальный бюджет пользователя
        min_budget = getattr(user, 'min_budget', 0) or 0
        if budget >= min_budget and min_budget > 0:
            priority_score += 10
            reasons.append(f"✅ Бюджет от {min_budget:,}₽")
        
        # 4. Проверка на скам
        scam_result = await scam_detector.analyze(
            order.get('title', ''),
            order.get('description', ''),
            order.get('budget', ''),
            budget
        )
        
        if scam_result['risk_level'] == 'safe':
            priority_score += 15
            reasons.append("✅ Безопасный заказ")
        elif scam_result['risk_level'] == 'low':
            priority_score += 10
            reasons.append("🟢 Низкий риск")
        elif scam_result['risk_level'] == 'high':
            priority_score -= 30
            reasons.append("⚠️ Подозрительный заказ")
        
        # 5. Свежесть (для новых заказов)
        priority_score += 10
        reasons.append("⚡ Новый заказ")
        
        # Определяем тип уведомления
        predator_mode = getattr(user, 'predator_mode', False)
        predator_min = getattr(user, 'predator_min_budget', 50000) or 50000
        
        if predator_mode and budget >= predator_min:
            notification_type = "predator"
            should_notify = True
            urgency = "critical"
        elif priority_score >= 70:
            notification_type = "hot"
            should_notify = True
            urgency = "high"
        elif priority_score >= 50:
            notification_type = "good"
            should_notify = True
            urgency = "medium"
        elif priority_score >= 30:
            notification_type = "normal"
            should_notify = True
            urgency = "low"
        else:
            notification_type = "skip"
            should_notify = False
            urgency = "none"
        
        return {
            "priority_score": priority_score,
            "notification_type": notification_type,
            "should_notify": should_notify,
            "urgency": urgency,
            "reasons": reasons[:4],
            "scam_check": scam_result,
            "emoji": self._get_priority_emoji(priority_score),
        }
    
    def _get_priority_emoji(self, score: int) -> str:
        if score >= 80:
            return "🚨"
        elif score >= 60:
            return "🔥"
        elif score >= 40:
            return "⭐"
        elif score >= 20:
            return "📋"
        return "📄"
    
    def format_notification(self, order: Dict, analysis: Dict) -> str:
        """Форматирует уведомление о заказе"""
        emoji = analysis['emoji']
        title = order.get('title', 'Без названия')
        budget = order.get('budget', 'Договорная')
        source = order.get('source', 'Неизвестно')
        url = order.get('url', '')
        
        # Заголовок по типу
        headers = {
            "predator": "🦁 РЕЖИМ ХИЩНИК",
            "hot": "🔥 ГОРЯЧИЙ ЗАКАЗ",
            "good": "⭐ ХОРОШИЙ ЗАКАЗ",
            "normal": "📋 НОВЫЙ ЗАКАЗ",
        }
        header = headers.get(analysis['notification_type'], "📋 НОВЫЙ ЗАКАЗ")
        
        # Причины
        reasons_text = "\n".join(f"  {r}" for r in analysis['reasons'])
        
        # Предупреждение о скаме
        scam_warning = ""
        if analysis['scam_check']['risk_level'] in ['medium', 'high']:
            scam_warning = f"\n\n⚠️ {analysis['scam_check']['risk_text']}"
        
        return f"""
{header}

📌 <b>{title}</b>

💰 Бюджет: {budget}
📍 Источник: {source}

<b>Почему подходит:</b>
{reasons_text}
{scam_warning}

🔗 <a href="{url}">Открыть заказ</a>
"""


smart_alerts = SmartAlerts()
