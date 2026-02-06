# config.py
import os
from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        return "sqlite+aiosqlite:///./data.db"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class Config:
    # Telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # Админы (через запятую в env: ADMIN_IDS=123456,789012)
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
    
    # GigaChat
    GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
    
    # YooKassa
    YUKASSA_SHOP_ID = os.getenv("YUKASSA_SHOP_ID")
    YUKASSA_SECRET_KEY = os.getenv("YUKASSA_SECRET_KEY")
    
    # Database
    DATABASE_URL = get_database_url()
    
    # Subscriptions
    TRIAL_DAYS = 3
    
    # Базовая подписка
    BASIC_PRICE = 690
    BASIC_DAYS = 30
    BASIC_AI_LIMIT = 50
    
    # PRO подписка
    PRO_PRICE = 1490
    PRO_DAYS = 30
    PRO_AI_LIMIT = -1  # Безлимит
    
    # Webhook
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    WEBHOOK_PATH = "/webhook"
    WEBAPP_HOST = "0.0.0.0"
    WEBAPP_PORT = int(os.getenv("PORT", 8080))
    
    # Parsing
    PARSE_INTERVAL = 60
    
    @classmethod
    def is_admin(cls, telegram_id: int) -> bool:
        """Проверяет, является ли пользователь админом"""
        return telegram_id in cls.ADMIN_IDS
