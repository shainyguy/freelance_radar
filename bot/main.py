# bot/main.py (обновлённый)
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config import Config
from database.db import init_db
from services.scheduler import OrderScheduler
from bot.middlewares.subscription import SubscriptionMiddleware

from bot.handlers import start, categories, subscription, generate_response, profile, orders
from bot.handlers.payment_webhook import setup_payment_routes

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    """Действия при запуске"""
    await init_db()
    logger.info("Database initialized")
    
    if Config.WEBHOOK_URL:
        await bot.set_webhook(f"{Config.WEBHOOK_URL}{Config.WEBHOOK_PATH}")
        logger.info(f"Webhook set to {Config.WEBHOOK_URL}{Config.WEBHOOK_PATH}")


async def on_shutdown(bot: Bot):
    """Действия при остановке"""
    await bot.delete_webhook()
    logger.info("Bot stopped")


def create_bot() -> Bot:
    return Bot(
        token=Config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    
    # Регистрируем middleware
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
    
    # Регистрируем роутеры
    dp.include_router(start.router)
    dp.include_router(categories.router)
    dp.include_router(subscription.router)
    dp.include_router(generate_response.router)
    dp.include_router(profile.router)
    dp.include_router(orders.router)
    
    return dp


async def main():
    """Запуск бота"""
    bot = create_bot()
    dp = create_dispatcher()
    
    # Инициализация БД
    await init_db()
    
    # Запускаем планировщик мониторинга
    scheduler = OrderScheduler(bot)
    scheduler.start()
    
    if Config.WEBHOOK_URL:
        # Webhook режим (для Railway/production)
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)
        
        app = web.Application()
        
        # Webhook для бота
        webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_handler.register(app, path=Config.WEBHOOK_PATH)
        
        # Webhook для ЮKassa
        setup_payment_routes(app)
        
        setup_application(app, dp, bot=bot)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, Config.WEBAPP_HOST, Config.WEBAPP_PORT)
        await site.start()
        
        logger.info(f"Bot started on {Config.WEBAPP_HOST}:{Config.WEBAPP_PORT}")
        
        # Держим бота запущенным
        await asyncio.Event().wait()
    else:
        # Polling режим (для локальной разработки)
        logger.info("Starting bot in polling mode...")
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())