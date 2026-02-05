# database/models.py
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey, JSON, BigInteger
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
    subscription_end = Column(DateTime, nullable=True)
    trial_used = Column(Boolean, default=False)
    
    # Настройки
    categories = Column(JSON, default=list)
    min_budget = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    
    # 🦁 Режим Хищник - мгновенные пуши для жирных заказов
    predator_mode = Column(Boolean, default=False)
    predator_min_budget = Column(Integer, default=50000)  # Минимум для режима Хищник
    
    # Статистика
    total_earnings = Column(Integer, default=0)
    orders_taken = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    payments = relationship("Payment", back_populates="user")
    sent_orders = relationship("SentOrder", back_populates="user")
    
    def has_active_subscription(self) -> bool:
        if self.subscription_end is None:
            return False
        return self.subscription_end > datetime.utcnow()
    
    def is_in_trial(self) -> bool:
        if self.trial_used:
            return False
        if not self.subscription_end:
            return False
        return self.subscription_end > datetime.utcnow()
    
    def start_trial(self):
        from config import Config
        self.subscription_end = datetime.utcnow() + timedelta(days=Config.TRIAL_DAYS)
        self.trial_used = True
    
    def extend_subscription(self, days: int = 30):
        if self.subscription_end and self.subscription_end > datetime.utcnow():
            self.subscription_end += timedelta(days=days)
        else:
            self.subscription_end = datetime.utcnow() + timedelta(days=days)


class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    yukassa_payment_id = Column(String(255), unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(50), default="pending")  # pending, succeeded, canceled
    
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="payments")


class Order(Base):
    """Заказы с бирж"""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True)
    external_id = Column(String(255), nullable=False)  # ID на бирже
    source = Column(String(50), nullable=False)  # kwork, fl, habr, hh, telegram
    
    title = Column(String(500), nullable=False)
    description = Column(String(5000), nullable=True)
    budget = Column(String(100), nullable=True)
    budget_value = Column(Integer, nullable=True)  # Для фильтрации
    url = Column(String(500), nullable=False)
    category = Column(String(100), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    parsed_at = Column(DateTime, default=datetime.utcnow)
    
    # Уникальность по source + external_id
    __table_args__ = (
        {'sqlite_autoincrement': True}
    )


class SentOrder(Base):
    """Какие заказы уже отправлены пользователю"""
    __tablename__ = "sent_orders"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    

    user = relationship("User", back_populates="sent_orders")
