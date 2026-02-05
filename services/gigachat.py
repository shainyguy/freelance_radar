# services/gigachat.py
import aiohttp
import json
import uuid
import ssl
from config import Config
import logging

logger = logging.getLogger(__name__)


class GigaChatService:
    """Сервис для работы с GigaChat API"""
    
    AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    
    def __init__(self):
        self.access_token = None
        self.token_expires = 0
    
    async def _get_token(self) -> str:
        """Получает токен доступа"""
        import time
        
        if self.access_token and time.time() < self.token_expires:
            return self.access_token
        
        # Создаём SSL контекст без верификации (для GigaChat)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {Config.GIGACHAT_AUTH_KEY}"
        }
        
        data = "scope=GIGACHAT_API_PERS"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.AUTH_URL,
                headers=headers,
                data=data,
                ssl=ssl_context
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"GigaChat auth error: {error_text}")
                    raise Exception(f"Auth failed: {response.status}")
                
                result = await response.json()
                self.access_token = result["access_token"]
                self.token_expires = result["expires_at"] / 1000  # в секундах
                return self.access_token
    
    async def generate_response(self, order_title: str, order_description: str) -> str:
        """Генерирует отклик на заказ"""
        
        token = await self._get_token()
        
        prompt = f"""Ты - опытный фрилансер. Напиши короткий, но убедительный отклик на заказ.
Отклик должен быть:
- Персонализированным (упомяни детали заказа)
- Профессиональным, но дружелюбным
- Кратким (3-5 предложений)
- С призывом к действию

Заказ:
Название: {order_title}
Описание: {order_description}

Напиши только текст отклика, без лишних комментариев:"""

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        payload = {
            "model": "GigaChat",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.API_URL,
                headers=headers,
                json=payload,
                ssl=ssl_context
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"GigaChat API error: {error_text}")
                    return "Извините, не удалось сгенерировать отклик. Попробуйте позже."
                
                result = await response.json()
                return result["choices"][0]["message"]["content"]


gigachat_service = GigaChatService()