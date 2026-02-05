# database/db.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from database.models import Base, User, Order, Payment, SentOrder
from config import Config
from typing import Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Настройки для разных БД
connect_args = {}
if "sqlite" in Config.DATABASE_URL:
    connect_args = {"check_same_thread": False}

# Создаём engine
engine = create_async_engine(
    Config.DATABASE_URL, 
    echo=False,
    pool_pre_ping=True,  # Проверка соединения
)

async_session = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)


async def init_db():
    """Инициализация базы данных"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info(f"Database initialized successfully")
    except Exception as e:
        logger.error(f"Database init error: {e}")
        raise


class Database:
    @staticmethod
    async def get_user(telegram_id: int) -> Optional[User]:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()
    
    @staticmethod
    async def create_user(telegram_id: int, username: str = None, full_name: str = None) -> User:
        async with async_session() as session:
            user = User(
                telegram_id=telegram_id,
                username=username,
                full_name=full_name
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user
    
    @staticmethod
    async def get_or_create_user(telegram_id: int, username: str = None, full_name: str = None) -> User:
        user = await Database.get_user(telegram_id)
        if not user:
            user = await Database.create_user(telegram_id, username, full_name)
        return user
    
    @staticmethod
    async def update_user_categories(telegram_id: int, categories: List[str]):
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.categories = categories
                await session.commit()
    
    @staticmethod
    async def start_user_trial(telegram_id: int):
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user and not user.trial_used:
                user.start_trial()
                await session.commit()
    
    @staticmethod
    async def update_user_min_budget(telegram_id: int, min_budget: int):
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.min_budget = min_budget
                await session.commit()
    
    @staticmethod
    async def update_user_active(telegram_id: int, is_active: bool):
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.is_active = is_active
                await session.commit()
    
    @staticmethod
    async def extend_user_subscription(telegram_id: int, days: int = 30):
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.extend_subscription(days)
                await session.commit()
    
    @staticmethod
    async def save_order(order_data: dict) -> Optional[Order]:
        async with async_session() as session:
            result = await session.execute(
                select(Order).where(
                    Order.source == order_data['source'],
                    Order.external_id == order_data['external_id']
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return None
            
            order = Order(**order_data)
            session.add(order)
            await session.commit()
            await session.refresh(order)
            return order
    
    @staticmethod
    async def get_order_by_id(order_id: int) -> Optional[Order]:
        async with async_session() as session:
            result = await session.execute(
                select(Order).where(Order.id == order_id)
            )
            return result.scalar_one_or_none()
    
    @staticmethod
    async def get_active_users_for_category(category: str) -> List[User]:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(
                    User.is_active == True,
                    User.subscription_end > datetime.utcnow()
                )
            )
            users = result.scalars().all()
            return [u for u in users if category in (u.categories or [])]
    
    @staticmethod
    async def mark_order_sent(user_id: int, order_id: int):
        async with async_session() as session:
            sent = SentOrder(user_id=user_id, order_id=order_id)
            session.add(sent)
            await session.commit()
    
    @staticmethod
    async def is_order_sent(user_id: int, order_id: int) -> bool:
        async with async_session() as session:
            result = await session.execute(
                select(SentOrder).where(
                    SentOrder.user_id == user_id,
                    SentOrder.order_id == order_id
                )
            )
            return result.scalar_one_or_none() is not None
    
    @staticmethod
    async def create_payment(user_id: int, yukassa_payment_id: str, amount: float) -> Payment:
        async with async_session() as session:
            payment = Payment(
                user_id=user_id,
                yukassa_payment_id=yukassa_payment_id,
                amount=amount
            )
            session.add(payment)
            await session.commit()
            return payment
    
    @staticmethod
    async def confirm_payment(yukassa_payment_id: str):
        async with async_session() as session:
            result = await session.execute(
                select(Payment).where(Payment.yukassa_payment_id == yukassa_payment_id)
            )
            payment = result.scalar_one_or_none()
            if payment:
                payment.status = "succeeded"
                payment.confirmed_at = datetime.utcnow()
                
                user_result = await session.execute(
                    select(User).where(User.id == payment.user_id)
                )
                user = user_result.scalar_one_or_none()
                if user:
                    user.extend_subscription(30)
                
                await session.commit()
