# services/__init__.py
from .gigachat import gigachat_service, GigaChatService
from .yukassa import yukassa_service, YukassaService
from .scam_detector import scam_detector, ScamDetector
from .price_calculator import price_calculator, PriceCalculator
from .achievements import achievements, AchievementSystem
from .market_analytics import market_analytics, MarketAnalytics
from .smart_alerts import smart_alerts, SmartAlerts

__all__ = [
    'gigachat_service', 'GigaChatService',
    'yukassa_service', 'YukassaService',
    'scam_detector', 'ScamDetector',
    'price_calculator', 'PriceCalculator',
    'achievements', 'AchievementSystem',
    'market_analytics', 'MarketAnalytics',
    'smart_alerts', 'SmartAlerts',
]
