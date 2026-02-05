# bot/main.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiohttp import web

from config import Config
from database.db import init_db

from bot.handlers import start, categories, subscription, generate_response, profile, orders

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def health_check(request: web.Request) -> web.Response:
    """Healthcheck endpoint для Railway"""
    return web.Response(text="OK", status=200)


async def main():
    """Запуск бота"""
    
    # Создаём бота БЕЗ DefaultBotProperties
    bot = Bot(token=Config.BOT_TOKEN, parse_mode=ParseMode.HTML)
    
    dp = Dispatcher()
    
    # Регистрируем роутеры
    dp.include_router(start.router)
    dp.include_router(categories.router)
    dp.include_router(subscription.router)
    dp.include_router(generate_response.router)
    dp.include_router(profile.router)
    dp.include_router(orders.router)
    
    # Инициализация БД
    await init_db()
    logger.info("Database initialized")
    
    if Config.WEBHOOK_URL:
        # === WEBHOOK MODE ===
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        
        # Удаляем старый webhook и ставим новый
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(f"{Config.WEBHOOK_URL}{Config.WEBHOOK_PATH}")
        logger.info(f"Webhook set: {Config.WEBHOOK_URL}{Config.WEBHOOK_PATH}")
        
        # Создаём web app
        app = web.Application()
        
        # Health check endpoints
        app.router.add_get("/", health_check)
        app.router.add_get("/health", health_check)
        
        # Webhook handler
        webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_handler.register(app, path=Config.WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        
        # Запускаем сервер
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, Config.WEBAPP_HOST, Config.WEBAPP_PORT)
        await site.start()
        
        logger.info(f"Server running on {Config.WEBAPP_HOST}:{Config.WEBAPP_PORT}")
        
        # Держим запущенным
        await asyncio.Event().wait()
    else:
        # === POLLING MODE ===
        logger.info("Starting polling mode...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
