# services/yukassa.py
from yookassa import Configuration, Payment
from yookassa.domain.response import PaymentResponse
from config import Config
import uuid
import logging

logger = logging.getLogger(__name__)

# Настройка ЮKassa
Configuration.account_id = Config.YUKASSA_SHOP_ID
Configuration.secret_key = Config.YUKASSA_SECRET_KEY


class YukassaService:
    """Сервис для работы с ЮKassa"""
    
    @staticmethod
    async def create_payment(user_id: int, amount: float = Config.SUBSCRIPTION_PRICE) -> tuple[str, str]:
        """
        Создаёт платёж
        Возвращает (payment_id, confirmation_url)
        """
        try:
            idempotence_key = str(uuid.uuid4())
            
            payment = Payment.create({
                "amount": {
                    "value": str(amount),
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"https://t.me/your_bot?start=payment_success_{user_id}"
                },
                "capture": True,
                "description": f"Подписка Freelance Radar на 30 дней",
                "metadata": {
                    "user_id": user_id
                }
            }, idempotence_key)
            
            return payment.id, payment.confirmation.confirmation_url
            
        except Exception as e:
            logger.error(f"YuKassa payment creation error: {e}")
            raise
    
    @staticmethod
    async def check_payment(payment_id: str) -> PaymentResponse:
        """Проверяет статус платежа"""
        try:
            payment = Payment.find_one(payment_id)
            return payment
        except Exception as e:
            logger.error(f"YuKassa payment check error: {e}")
            raise


yukassa_service = YukassaService()