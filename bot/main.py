# bot/main.py
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from config import Config
from database.db import init_db

from bot.handlers import start, categories, subscription, generate_response, profile, orders
from bot.api.routes import setup_api_routes

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK", status=200)


async def main():
    # Инициализация
    await init_db()
    logger.info("Database initialized")
    
    # Бот
    bot = Bot(token=Config.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    
    # Роутеры
    dp.include_router(start.router)
    dp.include_router(categories.router)
    dp.include_router(subscription.router)
    dp.include_router(generate_response.router)
    dp.include_router(profile.router)
    dp.include_router(orders.router)
    
    # Web Application
    app = web.Application()
    
    # Health check
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    # API для Mini App
    setup_api_routes(app)
    
    # Webhook для бота
    if Config.WEBHOOK_URL:
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(f"{Config.WEBHOOK_URL}{Config.WEBHOOK_PATH}")
        
        webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_handler.register(app, path=Config.WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        
        # Запуск сервера
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, Config.WEBAPP_HOST, Config.WEBAPP_PORT)
        await site.start()
        
        logger.info(f"Server started on {Config.WEBAPP_HOST}:{Config.WEBAPP_PORT}")
        
        # Планировщик
        from services.scheduler import OrderScheduler
        scheduler = OrderScheduler(bot)
        scheduler.start()
        
        await asyncio.Event().wait()
    else:
        # Polling
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
