# database/models.py
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey, JSON, BigInteger, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    
    # Подписка
    subscription_type = Column(String(20), default="free")  # free, basic, pro
    subscription_end = Column(DateTime, nullable=True)
    trial_used = Column(Boolean, default=False)
    
    # Лимиты
    ai_responses_used = Column(Integer, default=0)  # Использовано AI-откликов в этом месяце
    ai_responses_reset = Column(DateTime, nullable=True)  # Когда сбросить счётчик
    
    # Настройки
    categories = Column(JSON, default=list)
    min_budget = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    predator_mode = Column(Boolean, default=False)
    predator_min_budget = Column(Integer, default=50000)
    
    # Геймификация
    xp_points = Column(Integer, default=0)
    level = Column(Integer, default=1)
    achievements = Column(JSON, default=list)  # ["first_blood", "hunter", ...]
    streak_days = Column(Integer, default=0)
    last_active = Column(DateTime, nullable=True)
    
    # Статистика
    total_earnings = Column(Integer, default=0)
    orders_viewed = Column(Integer, default=0)
    responses_sent = Column(Integer, default=0)
    deals_completed = Column(Integer, default=0)
    
    # Реферальная система
    referral_code = Column(String(20), unique=True, nullable=True)
    referred_by = Column(Integer, nullable=True)
    referral_earnings = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    payments = relationship("Payment", back_populates="user")
    sent_orders = relationship("SentOrder", back_populates="user")
    deals = relationship("Deal", back_populates="user")
    incomes = relationship("Income", back_populates="user")
    
    def has_active_subscription(self) -> bool:
        if self.subscription_end is None:
            return False
        return self.subscription_end > datetime.utcnow()
    
    def is_pro(self) -> bool:
        return self.has_active_subscription() and self.subscription_type == "pro"
    
    def is_basic(self) -> bool:
        return self.has_active_subscription() and self.subscription_type == "basic"
    
    def can_use_ai_response(self) -> bool:
        if self.is_pro():
            return True  # Безлимит для PRO
        if not self.has_active_subscription():
            return False
        # Базовая - 50 в месяц
        if self.ai_responses_reset and self.ai_responses_reset < datetime.utcnow():
            return True  # Счётчик сбросится
        return self.ai_responses_used < 50
    
    def use_ai_response(self):
        now = datetime.utcnow()
        # Сброс счётчика каждый месяц
        if not self.ai_responses_reset or self.ai_responses_reset < now:
            self.ai_responses_used = 0
            self.ai_responses_reset = now + timedelta(days=30)
        self.ai_responses_used += 1
    
    def start_trial(self, subscription_type: str = "basic"):
        self.subscription_end = datetime.utcnow() + timedelta(days=3)
        self.subscription_type = subscription_type
        self.trial_used = True
    
    def extend_subscription(self, days: int = 30, subscription_type: str = None):
        if subscription_type:
            self.subscription_type = subscription_type
        if self.subscription_end and self.subscription_end > datetime.utcnow():
            self.subscription_end += timedelta(days=days)
        else:
            self.subscription_end = datetime.utcnow() + timedelta(days=days)
    
    def add_xp(self, points: int):
        self.xp_points += points
        # Проверяем левел-ап
        new_level = self._calculate_level()
        if new_level > self.level:
            self.level = new_level
            return True  # Новый уровень!
        return False
    
    def _calculate_level(self) -> int:
        levels = [0, 50, 150, 300, 500, 800, 1200, 2000]
        for i, min_xp in enumerate(levels):
            if self.xp_points < min_xp:
                return i
        return len(levels)


class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    yukassa_payment_id = Column(String(255), unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    subscription_type = Column(String(20), default="basic")  # basic, pro
    status = Column(String(50), default="pending")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="payments")


class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True)
    external_id = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False)
    
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    budget = Column(String(100), nullable=True)
    budget_value = Column(Integer, nullable=True)
    url = Column(String(500), nullable=False)
    category = Column(String(100), nullable=True)
    
    # Scam Detection
    scam_score = Column(Integer, default=0)
    scam_warnings = Column(JSON, default=list)
    
    # Analytics
    views_count = Column(Integer, default=0)
    responses_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    parsed_at = Column(DateTime, default=datetime.utcnow)


class SentOrder(Base):
    __tablename__ = "sent_orders"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="sent_orders")


class Deal(Base):
    """CRM - Сделки фрилансера"""
    __tablename__ = "deals"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_id = Column(Integer, nullable=True)  # Связь с заказом (опционально)
    
    title = Column(String(500), nullable=False)
    client_name = Column(String(255), nullable=True)
    client_contact = Column(String(255), nullable=True)  # Telegram, email и т.д.
    
    amount = Column(Integer, default=0)  # Сумма сделки
    paid_amount = Column(Integer, default=0)  # Оплачено
    
    # lead, negotiation, in_progress, review, completed, cancelled
    status = Column(String(50), default="lead")
    
    started_at = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="deals")
    incomes = relationship("Income", back_populates="deal")


class Income(Base):
    """Доходы"""
    __tablename__ = "incomes"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    deal_id = Column(Integer, ForeignKey("deals.id"), nullable=True)
    
    amount = Column(Integer, nullable=False)
    description = Column(String(500), nullable=True)
    source = Column(String(100), nullable=True)  # freelance, referral, bonus
    
    received_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="incomes")
    deal = relationship("Deal", back_populates="incomes")


class Achievement(Base):
    """Полученные достижения"""
    __tablename__ = "user_achievements"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    achievement_id = Column(String(50), nullable=False)  # first_blood, hunter, etc.
    
    unlocked_at = Column(DateTime, default=datetime.utcnow)
