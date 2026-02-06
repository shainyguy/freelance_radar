# services/yukassa.py
"""
YooKassa payment service.
"""
import logging
import uuid

from config import Config

logger = logging.getLogger(__name__)

# Пробуем импортировать yookassa
try:
    from yookassa import Configuration, Payment
    YOOKASSA_AVAILABLE = True
except ImportError:
    YOOKASSA_AVAILABLE = False
    logger.warning("yookassa not installed, payment features disabled")


class YukassaService:
    """Сервис для работы с ЮKassa"""
    
    def __init__(self):
        if YOOKASSA_AVAILABLE and Config.YUKASSA_SHOP_ID and Config.YUKASSA_SECRET_KEY:
            Configuration.account_id = Config.YUKASSA_SHOP_ID
            Configuration.secret_key = Config.YUKASSA_SECRET_KEY
            self.enabled = True
        else:
            self.enabled = False
            logger.info("YooKassa is not configured")
    
    async def create_payment(self, user_id: int, subscription_type: str = "basic") -> tuple:
        """
        Создаёт платёж
        
        Args:
            user_id: ID пользователя
            subscription_type: "basic" или "pro"
        
        Returns:
            (payment_id, confirmation_url)
        """
        # Определяем сумму по типу подписки
        if subscription_type == "pro":
            amount = Config.PRO_PRICE
            description = "PRO подписка Freelance Radar на 30 дней"
        else:
            amount = Config.BASIC_PRICE
            description = "Базовая подписка Freelance Radar на 30 дней"
        
        if not self.enabled:
            # Заглушка для тестов
            logger.warning("YooKassa disabled, returning test payment")
            return "test_payment_id", "https://example.com/pay"
        
        try:
            idempotence_key = str(uuid.uuid4())
            
            payment = Payment.create({
                "amount": {
                    "value": str(amount),
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"https://t.me/FreelanceRadarBot?start=payment_success"
                },
                "capture": True,
                "description": description,
                "metadata": {
                    "user_id": user_id,
                    "subscription_type": subscription_type
                }
            }, idempotence_key)
            
            return payment.id, payment.confirmation.confirmation_url
            
        except Exception as e:
            logger.error(f"YuKassa payment creation error: {e}")
            raise
    
    async def check_payment(self, payment_id: str):
        """Проверяет статус платежа"""
        if not self.enabled:
            return None
        
        try:
            payment = Payment.find_one(payment_id)
            return payment
        except Exception as e:
            logger.error(f"YuKassa payment check error: {e}")
            return None


yukassa_service = YukassaService()
