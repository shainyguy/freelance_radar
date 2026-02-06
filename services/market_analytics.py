# services/market_analytics.py
from datetime import datetime, timedelta
from typing import Dict, List
from database.db import async_session
from database.models import Order, Deal, Income
from sqlalchemy import select, func, and_


class MarketAnalytics:
    """Аналитика рынка и персональная статистика"""
    
    async def get_market_stats(self, category: str = None) -> Dict:
        """Общая статистика рынка"""
        async with async_session() as session:
            now = datetime.utcnow()
            week_ago = now - timedelta(days=7)
            month_ago = now - timedelta(days=30)
            
            # Базовый запрос
            base_filter = Order.created_at >= week_ago
            if category:
                base_filter = and_(base_filter, Order.category == category)
            
            # Количество заказов за неделю
            weekly_count = await session.execute(
                select(func.count(Order.id)).where(base_filter)
            )
            weekly_orders = weekly_count.scalar() or 0
            
            # Средний бюджет
            avg_budget = await session.execute(
                select(func.avg(Order.budget_value)).where(
                    and_(base_filter, Order.budget_value > 0)
                )
            )
            avg_budget_value = int(avg_budget.scalar() or 0)
            
            # Максимальный бюджет
            max_budget = await session.execute(
                select(func.max(Order.budget_value)).where(base_filter)
            )
            max_budget_value = max_budget.scalar() or 0
            
            # По источникам
            sources = await session.execute(
                select(Order.source, func.count(Order.id).label('count'))
                .where(Order.created_at >= week_ago)
                .group_by(Order.source)
                .order_by(func.count(Order.id).desc())
            )
            sources_data = [{"source": r[0], "count": r[1]} for r in sources]
            
            # По категориям
            categories = await session.execute(
                select(Order.category, func.count(Order.id).label('count'))
                .where(Order.created_at >= week_ago)
                .group_by(Order.category)
                .order_by(func.count(Order.id).desc())
            )
            categories_data = [{"category": r[0], "count": r[1]} for r in categories if r[0]]
            
            # Тренд (сравнение с прошлой неделей)
            two_weeks_ago = now - timedelta(days=14)
            prev_week = await session.execute(
                select(func.count(Order.id)).where(
                    and_(Order.created_at >= two_weeks_ago, Order.created_at < week_ago)
                )
            )
            prev_week_orders = prev_week.scalar() or 1
            
            trend_percent = int(((weekly_orders - prev_week_orders) / prev_week_orders) * 100)
            
            return {
                "weekly_orders": weekly_orders,
                "daily_avg": weekly_orders // 7 if weekly_orders else 0,
                "avg_budget": avg_budget_value,
                "max_budget": max_budget_value,
                "sources": sources_data[:5],
                "categories": categories_data[:5],
                "trend_percent": trend_percent,
                "trend_text": f"+{trend_percent}%" if trend_percent > 0 else f"{trend_percent}%",
                "trend_emoji": "📈" if trend_percent > 0 else "📉" if trend_percent < 0 else "📊",
                "best_category": categories_data[0]["category"] if categories_data else None,
                "best_source": sources_data[0]["source"] if sources_data else None,
            }
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """Персональная статистика пользователя"""
        async with async_session() as session:
            now = datetime.utcnow()
            month_ago = now - timedelta(days=30)
            
            # Доходы за месяц
            monthly_income = await session.execute(
                select(func.sum(Income.amount)).where(
                    and_(Income.user_id == user_id, Income.received_at >= month_ago)
                )
            )
            monthly_earnings = monthly_income.scalar() or 0
            
            # Всего доходов
            total_income = await session.execute(
                select(func.sum(Income.amount)).where(Income.user_id == user_id)
            )
            total_earnings = total_income.scalar() or 0
            
            # Сделки
            deals_count = await session.execute(
                select(func.count(Deal.id)).where(Deal.user_id == user_id)
            )
            total_deals = deals_count.scalar() or 0
            
            # Активные сделки
            active_deals = await session.execute(
                select(func.count(Deal.id)).where(
                    and_(Deal.user_id == user_id, Deal.status.in_(["lead", "negotiation", "in_progress"]))
                )
            )
            active_count = active_deals.scalar() or 0
            
            # Завершённые сделки
            completed_deals = await session.execute(
                select(func.count(Deal.id)).where(
                    and_(Deal.user_id == user_id, Deal.status == "completed")
                )
            )
            completed_count = completed_deals.scalar() or 0
            
            # Средний чек
            avg_deal = await session.execute(
                select(func.avg(Deal.amount)).where(
                    and_(Deal.user_id == user_id, Deal.status == "completed", Deal.amount > 0)
                )
            )
            avg_deal_value = int(avg_deal.scalar() or 0)
            
            # Доходы по месяцам (для графика)
            # Можно добавить группировку по месяцам
            
            return {
                "monthly_earnings": monthly_earnings,
                "total_earnings": total_earnings,
                "total_deals": total_deals,
                "active_deals": active_count,
                "completed_deals": completed_count,
                "avg_deal": avg_deal_value,
                "conversion_rate": int((completed_count / total_deals * 100)) if total_deals else 0,
            }
    
    async def get_hot_categories(self) -> List[Dict]:
        """Горячие категории (с ростом заказов)"""
        async with async_session() as session:
            now = datetime.utcnow()
            week_ago = now - timedelta(days=7)
            
            result = await session.execute(
                select(
                    Order.category,
                    func.count(Order.id).label('count'),
                    func.avg(Order.budget_value).label('avg_budget')
                )
                .where(and_(Order.created_at >= week_ago, Order.category.isnot(None)))
                .group_by(Order.category)
                .order_by(func.count(Order.id).desc())
                .limit(5)
            )
            
            return [
                {
                    "category": r[0],
                    "count": r[1],
                    "avg_budget": int(r[2] or 0)
                }
                for r in result
            ]


market_analytics = MarketAnalytics()
