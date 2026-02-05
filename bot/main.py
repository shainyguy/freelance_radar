# bot/main.py
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

from bot.handlers import start, categories, subscription, generate_response, profile, orders

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============ HEALTHCHECK ============
async def health_check(request: web.Request) -> web.Response:
    """Healthcheck endpoint для Railway"""
    return web.Response(text="OK", status=200)


async def on_startup(bot: Bot):
    """Действия при запуске"""
    await init_db()
    logger.info("Database initialized")
    
    if Config.WEBHOOK_URL:
        webhook_url = f"{Config.WEBHOOK_URL}{Config.WEBHOOK_PATH}"
        await bot.set_webhook(webhook_url)
        logger.info(f"Webhook set to {webhook_url}")


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
    logger.info("Database initialized")
    
    # Регистрируем startup/shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Создаём web приложение
    app = web.Application()
    
    # ============ ДОБАВЛЯЕМ HEALTHCHECK ROUTE ============
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    
    # Webhook для бота
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=Config.WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)
    
    # Запускаем сервер
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(
        runner, 
        host=Config.WEBAPP_HOST, 
        port=Config.WEBAPP_PORT
    )
    await site.start()
    
    logger.info(f"Server started on {Config.WEBAPP_HOST}:{Config.WEBAPP_PORT}")
    
    # Запускаем планировщик (опционально, можно отключить на старте)
    try:
        scheduler = OrderScheduler(bot)
        scheduler.start()
        logger.info("Scheduler started")
    except Exception as e:
        logger.error(f"Scheduler error: {e}")
    
    # Держим приложение запущенным
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
