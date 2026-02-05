# bot/main.py - максимально простой вариант
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from config import Config
from database.db import init_db

from bot.handlers import start, categories, subscription, generate_response, profile, orders

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    # Инициализация БД
    await init_db()
    logger.info("Database initialized")
    
    # Создаём бота
    bot = Bot(token=Config.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    
    # Регистрируем роутеры
    dp.include_router(start.router)
    dp.include_router(categories.router)
    dp.include_router(subscription.router)
    dp.include_router(generate_response.router)
    dp.include_router(profile.router)
    dp.include_router(orders.router)
    
    # Запускаем
    logger.info("Starting bot...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
