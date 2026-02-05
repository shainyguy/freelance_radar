# bot/api/routes.py
from aiohttp import web
import json
import hashlib
import hmac
from urllib.parse import parse_qsl
from config import Config
from database.db import Database
from services.gigachat import gigachat_service
import logging

logger = logging.getLogger(__name__)


def verify_telegram_data(init_data: str) -> dict:
    """Верификация данных от Telegram Web App"""
    try:
        parsed = dict(parse_qsl(init_data))
        check_hash = parsed.pop('hash', '')
        
        data_check_string = '\n'.join(
            f'{k}={v}' for k, v in sorted(parsed.items())
        )
        
        secret_key = hmac.new(
            b'WebAppData',
            Config.BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()
        
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if calculated_hash == check_hash:
            user_data = json.loads(parsed.get('user', '{}'))
            return user_data
        return None
    except Exception as e:
        logger.error(f"Verify error: {e}")
        return None


async def get_user_from_request(request: web.Request) -> dict:
    """Получает пользователя из запроса"""
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    if not init_data:
        body = await request.json()
        init_data = body.get('initData', '')
    
    user_data = verify_telegram_data(init_data)
    if user_data:
        user = await Database.get_or_create_user(
            telegram_id=user_data.get('id'),
            username=user_data.get('username'),
            full_name=f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
        )
        return user
    return None


# ========== API Handlers ==========

async def api_user(request: web.Request) -> web.Response:
    """Получение данных пользователя"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    return web.json_response({
        'id': user.id,
        'telegram_id': user.telegram_id,
        'username': user.username,
        'has_subscription': user.has_active_subscription(),
        'is_trial': user.is_in_trial(),
        'categories': user.categories or [],
        'predator_mode': getattr(user, 'predator_mode', False),
        'min_budget': user.min_budget or 0
    })


async def api_orders(request: web.Request) -> web.Response:
    """Получение списка заказов"""
    user = await get_user_from_request(request)
    category = request.query.get('category', 'all')
    
    from database.db import async_session
    from database.models import Order
    from sqlalchemy import select, desc
    
    async with async_session() as session:
        query = select(Order).order_by(desc(Order.created_at)).limit(50)
        
        if category != 'all':
            query = query.where(Order.category == category)
        
        result = await session.execute(query)
        orders = result.scalars().all()
    
    orders_data = []
    for order in orders:
        orders_data.append({
            'id': order.id,
            'title': order.title,
            'description': order.description[:200] if order.description else '',
            'source': order.source,
            'budget': order.budget,
            'budget_value': order.budget_value or 0,
            'url': order.url,
            'category': order.category,
            'time_ago': get_time_ago(order.created_at),
            'ai_score': calculate_ai_score(order, user),
            'competition': estimate_competition(order)
        })
    
    return web.json_response(orders_data)


async def api_turbo_parse(request: web.Request) -> web.Response:
    """Принудительный парсинг всех бирж"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    if not user.has_active_subscription():
        return web.json_response({'error': 'Subscription required'}, status=403)
    
    from parsers import ALL_PARSERS
    
    new_orders_count = 0
    categories = user.categories or ['design', 'python', 'copywriting', 'marketing']
    
    for parser in ALL_PARSERS:
        for category in categories:
            try:
                orders = await parser.parse_orders(category)
                for order_data in orders:
                    order = await Database.save_order(order_data)
                    if order:
                        new_orders_count += 1
            except Exception as e:
                logger.error(f"Parse error {parser.SOURCE_NAME}: {e}")
    
    # Закрываем сессии
    for parser in ALL_PARSERS:
        await parser.close()
    
    return web.json_response({
        'success': True,
        'new_orders': new_orders_count
    })


async def api_generate_response(request: web.Request) -> web.Response:
    """Генерация AI-отклика"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    if not user.has_active_subscription():
        return web.json_response({'error': 'Subscription required'}, status=403)
    
    body = await request.json()
    order_id = body.get('order_id')
    
    order = await Database.get_order_by_id(order_id)
    if not order:
        return web.json_response({'error': 'Order not found'}, status=404)
    
    try:
        response_text = await gigachat_service.generate_response(
            order.title,
            order.description or ''
        )
        return web.json_response({'response': response_text})
    except Exception as e:
        logger.error(f"Generate response error: {e}")
        return web.json_response({'error': str(e)}, status=500)


async def api_predator_mode(request: web.Request) -> web.Response:
    """Включение/выключение режима Хищник"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    body = await request.json()
    enabled = body.get('enabled', False)
    
    await Database.update_predator_mode(user.telegram_id, enabled)
    
    return web.json_response({'success': True, 'enabled': enabled})


async def api_stats(request: web.Request) -> web.Response:
    """Статистика пользователя"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    # В реальном приложении тут была бы реальная статистика
    return web.json_response({
        'orders_today': 47,
        'responses': 12,
        'earnings': '89K',
        'total_earnings': '156 000'
    })


# ========== Helper Functions ==========

def get_time_ago(dt) -> str:
    """Возвращает относительное время"""
    from datetime import datetime, timezone
    
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    diff = now - dt
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "только что"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes} мин назад"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} ч назад"
    else:
        days = int(seconds // 86400)
        return f"{days} дн назад"


def calculate_ai_score(order, user) -> int:
    """Рассчитывает AI Match Score"""
    score = 50  # Базовый скор
    
    # Совпадение категории
    if user and order.category in (user.categories or []):
        score += 20
    
    # Бюджет
    if order.budget_value:
        if order.budget_value >= 50000:
            score += 15
        elif order.budget_value >= 20000:
            score += 10
    
    # Свежесть заказа
    from datetime import datetime, timezone
    age_hours = (datetime.now(timezone.utc) - order.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
    if age_hours < 1:
        score += 15
    elif age_hours < 6:
        score += 10
    
    return min(score, 99)


def estimate_competition(order) -> int:
    """Оценивает уровень конкуренции (1-5)"""
    from datetime import datetime, timezone
    
    # Свежие заказы - меньше конкуренция
    age_hours = (datetime.now(timezone.utc) - order.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
    
    if age_hours < 0.5:
        return 1
    elif age_hours < 2:
        return 2
    elif age_hours < 6:
        return 3
    elif age_hours < 24:
        return 4
    else:
        return 5


def setup_api_routes(app: web.Application):
    """Настройка API роутов"""
    app.router.add_post('/api/user', api_user)
    app.router.add_get('/api/orders', api_orders)
    app.router.add_post('/api/turbo-parse', api_turbo_parse)
    app.router.add_post('/api/generate-response', api_generate_response)
    app.router.add_post('/api/predator-mode', api_predator_mode)
    app.router.add_get('/api/stats', api_stats)
    
    # Static files for Mini App
    app.router.add_static('/static/', path='./static', name='static')
    
    # Serve index.html
    async def serve_webapp(request):
        return web.FileResponse('./static/index.html')
    
    app.router.add_get('/webapp', serve_webapp)
