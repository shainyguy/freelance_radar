# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # GigaChat
    GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
    
    # YooKassa
    YUKASSA_SHOP_ID = os.getenv("YUKASSA_SHOP_ID")
    YUKASSA_SECRET_KEY = os.getenv("YUKASSA_SECRET_KEY")
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./freelance_radar.db")
    
    # Subscription
    TRIAL_DAYS = 3
    SUBSCRIPTION_PRICE = 690
    SUBSCRIPTION_DAYS = 30
    
    # Webhook
    WEBHOOK_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN")  # Railway автоматически даёт
    if WEBHOOK_URL and not WEBHOOK_URL.startswith("https://"):
        WEBHOOK_URL = f"https://{WEBHOOK_URL}"
    
    WEBHOOK_PATH = "/webhook"
    WEBAPP_HOST = "0.0.0.0"
    WEBAPP_PORT = int(os.getenv("PORT", 8080))  # Railway даёт PORT
    
    # Parsing
    PARSE_INTERVAL = 60
