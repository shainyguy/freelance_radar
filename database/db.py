# database/db.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, func, and_, text, update
from database.models import Base, User, Order, Payment, SentOrder, Deal, Income, Achievement
from config import Config
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import logging
import secrets
import string

logger = logging.getLogger(__name__)

engine = create_async_engine(Config.DATABASE_URL, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def run_migrations():
    """Добавляет недостающие колонки"""
    migrations = [
        # User fields
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_type VARCHAR(20) DEFAULT 'free'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_responses_used INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_responses_reset TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS predator_mode BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS predator_min_budget INTEGER DEFAULT 50000",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS xp_points INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS level INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS achievements JSON DEFAULT '[]'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_days INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_earnings INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS orders_viewed INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS responses_sent INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS deals_completed INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20) UNIQUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_earnings INTEGER DEFAULT 0",
        
        # Order fields
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS scam_score INTEGER DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS scam_warnings JSON DEFAULT '[]'",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS views_count INTEGER DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS responses_count INTEGER DEFAULT 0",
        
        # Payment fields
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS subscription_type VARCHAR(20) DEFAULT 'basic'",
    ]
    
    async with engine.begin() as conn:
        for migration in migrations:
            try:
                await conn.execute(text(migration))
            except Exception as e:
                logger.debug(f"Migration skipped: {e}")


async def init_db():
    """Инициализация базы данных"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await run_migrations()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database init error: {e}")
        raise


def generate_referral_code() -> str:
    """Генерирует уникальный реферальный код"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(8))


class Database:
    """Основной класс для работы с БД"""
    
    # ============ USER ============
    
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
                full_name=full_name,
                referral_code=generate_referral_code(),
                last_active=datetime.utcnow()
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
    async def update_user_activity(telegram_id: int):
        """Обновляет активность и streak"""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                now = datetime.utcnow()
                
                # Проверяем streak
                if user.last_active:
                    diff = (now - user.last_active).days
                    if diff == 1:
                        user.streak_days += 1
                    elif diff > 1:
                        user.streak_days = 1
                else:
                    user.streak_days = 1
                
                user.last_active = now
                await session.commit()
    
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
    async def update_user_settings(telegram_id: int, **kwargs):
        """Обновляет настройки пользователя"""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                for key, value in kwargs.items():
                    if hasattr(user, key):
                        setattr(user, key, value)
                await session.commit()
    
    @staticmethod
    async def start_user_trial(telegram_id: int, subscription_type: str = "basic"):
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user and not user.trial_used:
                user.subscription_end = datetime.utcnow() + timedelta(days=Config.TRIAL_DAYS)
                user.subscription_type = subscription_type
                user.trial_used = True
                await session.commit()
                return True
            return False
    
    @staticmethod
    async def extend_subscription(telegram_id: int, days: int, subscription_type: str):
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.subscription_type = subscription_type
                if user.subscription_end and user.subscription_end > datetime.utcnow():
                    user.subscription_end += timedelta(days=days)
                else:
                    user.subscription_end = datetime.utcnow() + timedelta(days=days)
                await session.commit()
    
    @staticmethod
    async def use_ai_response(telegram_id: int) -> bool:
        """Использует AI-отклик. Возвращает True если успешно."""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return False
            
            # PRO - безлимит
            if user.subscription_type == "pro" and user.has_active_subscription():
                user.responses_sent += 1
                await session.commit()
                return True
            
            # Базовая - лимит 50
            if not user.has_active_subscription():
                return False
            
            now = datetime.utcnow()
            if not user.ai_responses_reset or user.ai_responses_reset < now:
                user.ai_responses_used = 0
                user.ai_responses_reset = now + timedelta(days=30)
            
            if user.ai_responses_used >= Config.BASIC_AI_LIMIT:
                return False
            
            user.ai_responses_used += 1
            user.responses_sent += 1
            await session.commit()
            return True
    
    @staticmethod
    async def get_ai_responses_left(telegram_id: int) -> int:
        """Возвращает оставшееся количество AI-откликов"""
        user = await Database.get_user(telegram_id)
        if not user:
            return 0
        
        if user.subscription_type == "pro" and user.has_active_subscription():
            return -1  # Безлимит
        
        if not user.has_active_subscription():
            return 0
        
        now = datetime.utcnow()
        if not user.ai_responses_reset or user.ai_responses_reset < now:
            return Config.BASIC_AI_LIMIT
        
        return max(0, Config.BASIC_AI_LIMIT - (user.ai_responses_used or 0))
    
    # ============ XP & ACHIEVEMENTS ============
    
    @staticmethod
    async def add_xp(telegram_id: int, points: int) -> Dict:
        """Добавляет XP и проверяет level up"""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return {"level_up": False}
            
            old_level = user.level
            user.xp_points += points
            
            # Проверяем новый уровень
            levels = [0, 50, 150, 300, 500, 800, 1200, 2000, 3000]
            new_level = 1
            for i, min_xp in enumerate(levels):
                if user.xp_points >= min_xp:
                    new_level = i + 1
            
            user.level = new_level
            await session.commit()
            
            return {
                "level_up": new_level > old_level,
                "old_level": old_level,
                "new_level": new_level,
                "xp": user.xp_points
            }
    
    @staticmethod
    async def unlock_achievement(telegram_id: int, achievement_id: str) -> bool:
        """Разблокирует достижение"""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return False
            
            achievements = user.achievements or []
            if achievement_id in achievements:
                return False
            
            achievements.append(achievement_id)
            user.achievements = achievements
            await session.commit()
            return True
    
    @staticmethod
    async def increment_stat(telegram_id: int, stat: str, value: int = 1):
        """Увеличивает статистику пользователя"""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user and hasattr(user, stat):
                current = getattr(user, stat) or 0
                setattr(user, stat, current + value)
                await session.commit()
    
    # ============ ORDERS ============
    
    @staticmethod
    async def save_order(order_data: dict) -> Optional[Order]:
        async with async_session() as session:
            result = await session.execute(
                select(Order).where(
                    Order.source == order_data['source'],
                    Order.external_id == order_data['external_id']
                )
            )
            if result.scalar_one_or_none():
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
    async def get_orders(category: str = None, limit: int = 50) -> List[Order]:
        async with async_session() as session:
            query = select(Order).order_by(Order.created_at.desc()).limit(limit)
            if category and category != 'all':
                query = query.where(Order.category == category)
            result = await session.execute(query)
            return result.scalars().all()
    
    @staticmethod
    async def update_order_scam(order_id: int, scam_score: int, warnings: List[str]):
        """Обновляет scam-данные заказа"""
        async with async_session() as session:
            result = await session.execute(
                select(Order).where(Order.id == order_id)
            )
            order = result.scalar_one_or_none()
            if order:
                order.scam_score = scam_score
                order.scam_warnings = warnings
                await session.commit()
    
    @staticmethod
    async def increment_order_views(order_id: int):
        async with async_session() as session:
            await session.execute(
                update(Order).where(Order.id == order_id).values(
                    views_count=Order.views_count + 1
                )
            )
            await session.commit()
    
    # ============ DEALS (CRM) ============
    
    @staticmethod
    async def create_deal(user_id: int, **kwargs) -> Deal:
        async with async_session() as session:
            deal = Deal(user_id=user_id, **kwargs)
            session.add(deal)
            await session.commit()
            await session.refresh(deal)
            return deal
    
    @staticmethod
    async def get_user_deals(user_id: int, status: str = None) -> List[Deal]:
        async with async_session() as session:
            query = select(Deal).where(Deal.user_id == user_id).order_by(Deal.created_at.desc())
            if status:
                query = query.where(Deal.status == status)
            result = await session.execute(query)
            return result.scalars().all()
    
    @staticmethod
    async def update_deal(deal_id: int, **kwargs) -> Optional[Deal]:
        async with async_session() as session:
            result = await session.execute(
                select(Deal).where(Deal.id == deal_id)
            )
            deal = result.scalar_one_or_none()
            if deal:
                for key, value in kwargs.items():
                    if hasattr(deal, key):
                        setattr(deal, key, value)
                
                if kwargs.get('status') == 'completed':
                    deal.completed_at = datetime.utcnow()
                
                await session.commit()
                await session.refresh(deal)
            return deal
    
    @staticmethod
    async def delete_deal(deal_id: int) -> bool:
        async with async_session() as session:
            result = await session.execute(
                select(Deal).where(Deal.id == deal_id)
            )
            deal = result.scalar_one_or_none()
            if deal:
                await session.delete(deal)
                await session.commit()
                return True
            return False
    
    # ============ INCOME ============
    
    @staticmethod
    async def add_income(user_id: int, amount: int, deal_id: int = None, 
                        description: str = None, source: str = "freelance") -> Income:
        async with async_session() as session:
            income = Income(
                user_id=user_id,
                amount=amount,
                deal_id=deal_id,
                description=description,
                source=source
            )
            session.add(income)
            
            # Обновляем total_earnings пользователя
            user_result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                user.total_earnings = (user.total_earnings or 0) + amount
            
            await session.commit()
            await session.refresh(income)
            return income
    
    @staticmethod
    async def get_user_incomes(user_id: int, days: int = 30) -> List[Income]:
        async with async_session() as session:
            since = datetime.utcnow() - timedelta(days=days)
            result = await session.execute(
                select(Income)
                .where(and_(Income.user_id == user_id, Income.received_at >= since))
                .order_by(Income.received_at.desc())
            )
            return result.scalars().all()
    
    @staticmethod
    async def get_user_earnings_stats(user_id: int) -> Dict:
        async with async_session() as session:
            now = datetime.utcnow()
            month_ago = now - timedelta(days=30)
            week_ago = now - timedelta(days=7)
            
            # За месяц
            monthly = await session.execute(
                select(func.sum(Income.amount)).where(
                    and_(Income.user_id == user_id, Income.received_at >= month_ago)
                )
            )
            monthly_sum = monthly.scalar() or 0
            
            # За неделю
            weekly = await session.execute(
                select(func.sum(Income.amount)).where(
                    and_(Income.user_id == user_id, Income.received_at >= week_ago)
                )
            )
            weekly_sum = weekly.scalar() or 0
            
            # Всего
            total = await session.execute(
                select(func.sum(Income.amount)).where(Income.user_id == user_id)
            )
            total_sum = total.scalar() or 0
            
            return {
                "monthly": monthly_sum,
                "weekly": weekly_sum,
                "total": total_sum
            }
    
    # ============ PAYMENTS ============
    
    @staticmethod
    async def create_payment(user_id: int, yukassa_payment_id: str, 
                            amount: float, subscription_type: str) -> Payment:
        async with async_session() as session:
            payment = Payment(
                user_id=user_id,
                yukassa_payment_id=yukassa_payment_id,
                amount=amount,
                subscription_type=subscription_type
            )
            session.add(payment)
            await session.commit()
            return payment
    
    @staticmethod
    async def confirm_payment(yukassa_payment_id: str) -> Optional[User]:
        async with async_session() as session:
            result = await session.execute(
                select(Payment).where(Payment.yukassa_payment_id == yukassa_payment_id)
            )
            payment = result.scalar_one_or_none()
            if payment and payment.status != "succeeded":
                payment.status = "succeeded"
                payment.confirmed_at = datetime.utcnow()
                
                user_result = await session.execute(
                    select(User).where(User.id == payment.user_id)
                )
                user = user_result.scalar_one_or_none()
                if user:
                    days = Config.PRO_DAYS if payment.subscription_type == "pro" else Config.BASIC_DAYS
                    if user.subscription_end and user.subscription_end > datetime.utcnow():
                        user.subscription_end += timedelta(days=days)
                    else:
                        user.subscription_end = datetime.utcnow() + timedelta(days=days)
                    user.subscription_type = payment.subscription_type
                    
                    await session.commit()
                    return user
            return None
    
    # ============ NOTIFICATIONS ============
    
    @staticmethod
    async def mark_order_sent(user_id: int, order_id: int):
        async with async_session() as session:
            existing = await session.execute(
                select(SentOrder).where(
                    SentOrder.user_id == user_id,
                    SentOrder.order_id == order_id
                )
            )
            if existing.scalar_one_or_none():
                return
            
            sent = SentOrder(user_id=user_id, order_id=order_id)
            session.add(sent)
            try:
                await session.commit()
            except:
                await session.rollback()
    
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
    
    # ============ ANALYTICS ============
    
    @staticmethod
    async def get_market_stats(category: str = None) -> Dict:
        async with async_session() as session:
            week_ago = datetime.utcnow() - timedelta(days=7)
            
            base_filter = Order.created_at >= week_ago
            if category:
                base_filter = and_(base_filter, Order.category == category)
            
            # Количество
            count_result = await session.execute(
                select(func.count(Order.id)).where(base_filter)
            )
            weekly_count = count_result.scalar() or 0
            
            # Средний бюджет
            avg_result = await session.execute(
                select(func.avg(Order.budget_value)).where(
                    and_(base_filter, Order.budget_value > 0)
                )
            )
            avg_budget = int(avg_result.scalar() or 0)
            
            # По источникам
            sources_result = await session.execute(
                select(Order.source, func.count(Order.id))
                .where(Order.created_at >= week_ago)
                .group_by(Order.source)
                .order_by(func.count(Order.id).desc())
            )
            sources = [{"source": r[0], "count": r[1]} for r in sources_result]
            
            return {
                "weekly_orders": weekly_count,
                "avg_budget": avg_budget,
                "sources": sources
            }
