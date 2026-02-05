# config.py
import os
from dotenv import load_dotenv

load_dotenv()

def get_database_url() -> str:
    """Получает и преобразует DATABASE_URL для asyncpg"""
    url = os.getenv("DATABASE_URL")
    
    if not url:
        # Если нет - используем SQLite
        return "sqlite+aiosqlite:///./data.db"
    
    # Railway даёт postgres:// или postgresql://
    # Нужно заменить на postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    return url


class Config:
    # Telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # GigaChat
    GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
    
    # YooKassa
    YUKASSA_SHOP_ID = os.getenv("YUKASSA_SHOP_ID")
    YUKASSA_SECRET_KEY = os.getenv("YUKASSA_SECRET_KEY")
    
    # Database
    DATABASE_URL = get_database_url()
    
    # Subscription
    TRIAL_DAYS = 3
    SUBSCRIPTION_PRICE = 690
    SUBSCRIPTION_DAYS = 30
    
    # Webhook
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    WEBHOOK_PATH = "/webhook"
    WEBAPP_HOST = "0.0.0.0"
    WEBAPP_PORT = int(os.getenv("PORT", 8080))
    
    # Parsing
    PARSE_INTERVAL = 60
