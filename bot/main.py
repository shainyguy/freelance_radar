# bot/main.py
import asyncio
import logging
import os
import json
import hashlib
import hmac
from urllib.parse import parse_qsl
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import Config
from database.db import Database, init_db

from bot.handlers import start, categories, subscription, generate_response, profile, orders

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ===== TELEGRAM AUTH =====

def verify_telegram_data(init_data: str) -> dict:
    """Верификация данных от Telegram Web App"""
    if not init_data:
        return None
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


async def get_user_from_request(request: web.Request):
    """Получает пользователя из запроса"""
    # Из header или query
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    if not init_data:
        init_data = request.query.get('initData', '')
    
    if not init_data:
        # Пробуем из body
        try:
            body = await request.json()
            init_data = body.get('initData', '')
        except:
            pass
    
    user_data = verify_telegram_data(init_data)
    if user_data:
        user = await Database.get_or_create_user(
            telegram_id=user_data.get('id'),
            username=user_data.get('username'),
            full_name=f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
        )
        return user
    return None


# ===== API HANDLERS =====

async def api_user(request: web.Request) -> web.Response:
    """Получение данных пользователя"""
    user = await get_user_from_request(request)
    
    if not user:
        return web.json_response({
            'id': 0,
            'has_subscription': False,
            'is_new': True,
            'categories': [],
            'orders_count': 0,
            'earnings': 0
        })
    
    return web.json_response({
        'id': user.id,
        'telegram_id': user.telegram_id,
        'username': user.username,
        'has_subscription': user.has_active_subscription(),
        'is_trial': getattr(user, 'is_in_trial', lambda: False)(),
        'categories': user.categories or [],
        'predator_mode': getattr(user, 'predator_mode', False),
        'min_budget': user.min_budget or 0,
        'orders_count': getattr(user, 'orders_taken', 0),
        'earnings': getattr(user, 'total_earnings', 0)
    })


async def api_orders(request: web.Request) -> web.Response:
    """Получение списка заказов из БД"""
    category = request.query.get('category', 'all')
    
    from database.db import async_session
    from database.models import Order
    from sqlalchemy import select, desc
    from datetime import datetime, timezone
    
    async with async_session() as session:
        query = select(Order).order_by(desc(Order.created_at)).limit(30)
        
        if category != 'all':
            query = query.where(Order.category == category)
        
        result = await session.execute(query)
        db_orders = result.scalars().all()
    
    orders_data = []
    for order in db_orders:
        # Время назад
        now = datetime.now(timezone.utc)
        created = order.created_at.replace(tzinfo=timezone.utc) if order.created_at.tzinfo is None else order.created_at
        diff = (now - created).total_seconds()
        
        if diff < 60:
            time_ago = "только что"
        elif diff < 3600:
            time_ago = f"{int(diff // 60)} мин назад"
        elif diff < 86400:
            time_ago = f"{int(diff // 3600)} ч назад"
        else:
            time_ago = f"{int(diff // 86400)} дн назад"
        
        # AI Score (простая логика)
        score = 50
        if order.budget_value and order.budget_value >= 50000:
            score += 30
        elif order.budget_value and order.budget_value >= 20000:
            score += 20
        if diff < 3600:  # Свежий заказ
            score += 20
        score = min(score, 99)
        
        orders_data.append({
            'id': order.id,
            'title': order.title,
            'description': (order.description or '')[:200],
            'source': order.source,
            'budget': order.budget or 'Договорная',
            'budget_value': order.budget_value or 0,
            'url': order.url,
            'category': order.category,
            'time_ago': time_ago,
            'ai_score': score,
            'hot': (order.budget_value or 0) >= 30000
        })
    
    return web.json_response(orders_data)


async def api_turbo_parse(request: web.Request) -> web.Response:
    """Турбо-парсинг всех бирж"""
    user = await get_user_from_request(request)
    
    from parsers import ALL_PARSERS
    
    new_orders_count = 0
    
    # Категории для парсинга
    if user and user.categories:
        categories = user.categories
    else:
        categories = ['design', 'python', 'copywriting', 'marketing']
    
    for parser in ALL_PARSERS:
        for category in categories:
            try:
                orders = await parser.parse_orders(category)
                for order_data in orders:
                    order = await Database.save_order(order_data)
                    if order:
                        new_orders_count += 1
            except Exception as e:
                logger.error(f"Parse error {parser.SOURCE_NAME}/{category}: {e}")
        
        # Закрываем сессию парсера
        try:
            await parser.close()
        except:
            pass
    
    return web.json_response({
        'success': True,
        'new_orders': new_orders_count
    })


async def api_generate_response(request: web.Request) -> web.Response:
    """Генерация AI-отклика"""
    try:
        body = await request.json()
        order_id = body.get('order_id')
        
        order = await Database.get_order_by_id(order_id)
        if not order:
            return web.json_response({'error': 'Order not found'}, status=404)
        
        from services.gigachat import gigachat_service
        
        response_text = await gigachat_service.generate_response(
            order.title,
            order.description or ''
        )
        
        return web.json_response({'response': response_text})
        
    except Exception as e:
        logger.error(f"Generate response error: {e}")
        return web.json_response({
            'response': f"Здравствуйте!\n\nЗаинтересовал ваш проект. Имею опыт в данной области — 50+ выполненных задач.\n\nГотов обсудить детали! 🚀"
        })


async def api_stats(request: web.Request) -> web.Response:
    """Статистика"""
    from database.db import async_session
    from database.models import Order
    from sqlalchemy import select, func
    
    async with async_session() as session:
        result = await session.execute(select(func.count(Order.id)))
        total_orders = result.scalar() or 0
    
    return web.json_response({
        'total_orders': total_orders,
        'responses': 0,
        'earnings': 0
    })


# ===== WEB HANDLERS =====

async def handle_index(request):
    return web.Response(text="Freelance Radar Bot is running!")


async def handle_health(request):
    return web.Response(text="OK")


async def handle_webapp(request):
    """Mini App HTML"""
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', request.host)
    api_base = f"https://{domain}" if domain else ""
    
    html = get_webapp_html(api_base)
    return web.Response(text=html, content_type='text/html', charset='utf-8')


def get_webapp_html(api_base: str) -> str:
    return f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Freelance Radar</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 100%);
            color: #fff; min-height: 100vh; padding: 16px; padding-bottom: 100px;
        }}
        .container {{ max-width: 100%; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 24px; }}
        .logo {{ font-size: 48px; margin-bottom: 8px; animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0%, 100% {{ transform: scale(1); }} 50% {{ transform: scale(1.05); }} }}
        h1 {{ font-size: 22px; background: linear-gradient(135deg, #6c5ce7, #a29bfe);
             -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .subtitle {{ color: #888; font-size: 13px; margin-top: 4px; }}
        
        .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 16px; }}
        .stat-card {{ background: rgba(255,255,255,0.05); border-radius: 14px; padding: 14px 8px; 
                     text-align: center; border: 1px solid rgba(255,255,255,0.1); }}
        .stat-value {{ font-size: 22px; font-weight: 700; color: #6c5ce7; }}
        .stat-label {{ font-size: 10px; color: #888; text-transform: uppercase; margin-top: 2px; }}
        
        .turbo-btn {{
            width: 100%; padding: 16px; background: linear-gradient(135deg, #6c5ce7, #a29bfe);
            border: none; border-radius: 14px; color: white; font-size: 15px; font-weight: 600;
            cursor: pointer; margin-bottom: 16px; display: flex; align-items: center;
            justify-content: center; gap: 8px; position: relative; overflow: hidden;
        }}
        .turbo-btn:disabled {{ opacity: 0.7; }}
        .turbo-btn:active {{ transform: scale(0.98); }}
        
        .section-title {{ font-size: 15px; font-weight: 600; margin: 16px 0 12px; display: flex;
                         align-items: center; gap: 8px; }}
        .badge {{ background: #6c5ce7; padding: 2px 8px; border-radius: 10px; font-size: 11px; }}
        
        .order-card {{
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 14px; padding: 14px; margin-bottom: 10px; position: relative;
        }}
        .order-card.hot::after {{
            content: '🔥'; position: absolute; top: 10px; right: 10px; font-size: 16px;
        }}
        .order-header {{ display: flex; gap: 10px; margin-bottom: 10px; }}
        .order-source {{
            width: 40px; height: 40px; border-radius: 10px; display: flex;
            align-items: center; justify-content: center; font-size: 18px; flex-shrink: 0;
        }}
        .order-source.kwork {{ background: linear-gradient(135deg, #00d26a, #00b894); }}
        .order-source.fl {{ background: linear-gradient(135deg, #0984e3, #74b9ff); }}
        .order-source.habr {{ background: linear-gradient(135deg, #6c5ce7, #a29bfe); }}
        .order-source.hh {{ background: linear-gradient(135deg, #d63031, #ff7675); }}
        .order-info {{ flex: 1; min-width: 0; }}
        .order-title {{ font-size: 13px; font-weight: 600; line-height: 1.3; margin-bottom: 4px;
                       display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
        .order-meta {{ display: flex; gap: 10px; font-size: 11px; color: #888; }}
        
        .ai-score {{ display: flex; align-items: center; gap: 6px; margin: 10px 0; padding: 8px;
                    background: rgba(108, 92, 231, 0.1); border-radius: 10px; font-size: 12px; }}
        .score-bar {{ flex: 1; height: 5px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden; }}
        .score-fill {{ height: 100%; border-radius: 3px; }}
        .score-fill.high {{ background: linear-gradient(90deg, #00d26a, #00b894); }}
        .score-fill.medium {{ background: linear-gradient(90deg, #ffc107, #ffab00); }}
        .score-fill.low {{ background: linear-gradient(90deg, #ff4757, #ff6b81); }}
        .score-value {{ font-size: 13px; font-weight: 700; min-width: 35px; text-align: right; }}
        .score-value.high {{ color: #00d26a; }}
        .score-value.medium {{ color: #ffc107; }}
        .score-value.low {{ color: #ff4757; }}
        
        .order-actions {{ display: flex; gap: 8px; }}
        .order-btn {{
            flex: 1; padding: 10px; border: none; border-radius: 10px;
            font-size: 12px; font-weight: 600; cursor: pointer; display: flex;
            align-items: center; justify-content: center; gap: 4px;
        }}
        .order-btn.primary {{ background: linear-gradient(135deg, #6c5ce7, #a29bfe); color: white; }}
        .order-btn.secondary {{ background: rgba(255,255,255,0.1); color: white; }}
        .order-btn:active {{ transform: scale(0.95); }}
        
        .empty-state {{ text-align: center; padding: 40px 20px; }}
        .empty-icon {{ font-size: 48px; margin-bottom: 12px; }}
        .empty-title {{ font-size: 16px; font-weight: 600; margin-bottom: 6px; }}
        .empty-text {{ font-size: 13px; color: #888; }}
        
        .loading {{ text-align: center; padding: 30px; color: #888; }}
        .spinner {{ display: inline-block; width: 24px; height: 24px; border: 3px solid rgba(255,255,255,0.1);
                   border-top-color: #6c5ce7; border-radius: 50%; animation: spin 1s linear infinite; }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        
        .toast {{
            position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%) translateY(100px);
            background: #00d26a; color: white; padding: 12px 20px; border-radius: 10px;
            font-size: 13px; font-weight: 500; opacity: 0; transition: all 0.3s; z-index: 1000;
        }}
        .toast.error {{ background: #ff4757; }}
        .toast.show {{ transform: translateX(-50%) translateY(0); opacity: 1; }}
        
        .modal {{
            position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8);
            display: none; align-items: center; justify-content: center; z-index: 2000; padding: 20px;
        }}
        .modal.show {{ display: flex; }}
        .modal-content {{
            background: #1a1a2e; border-radius: 16px; padding: 20px; max-width: 100%; width: 100%;
            max-height: 80vh; overflow-y: auto;
        }}
        .modal-title {{ font-size: 16px; font-weight: 600; margin-bottom: 12px; }}
        .modal-text {{ font-size: 14px; line-height: 1.5; white-space: pre-wrap; margin-bottom: 16px;
                      background: rgba(255,255,255,0.05); padding: 12px; border-radius: 10px; }}
        .modal-btn {{
            width: 100%; padding: 14px; background: #00d26a; border: none; border-radius: 10px;
            color: white; font-size: 14px; font-weight: 600; cursor: pointer;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">📡</div>
            <h1>Freelance Radar</h1>
            <p class="subtitle">Охотник за жирными заказами</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value" id="ordersCount">—</div>
                <div class="stat-label">Заказов</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="responsesCount">—</div>
                <div class="stat-label">Откликов</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="earnings">—</div>
                <div class="stat-label">Заработано</div>
            </div>
        </div>
        
        <button class="turbo-btn" id="turboBtn" onclick="turboParse()">
            <span id="turboIcon">⚡</span>
            <span id="turboText">НАЙТИ ЗАКАЗЫ</span>
        </button>
        
        <div class="section-title">
            <span>📋 Заказы</span>
            <span class="badge" id="ordersCountBadge">0</span>
        </div>
        
        <div id="ordersList">
            <div class="empty-state">
                <div class="empty-icon">🔍</div>
                <div class="empty-title">Пока нет заказов</div>
                <div class="empty-text">Нажми «Найти заказы» чтобы найти свежие заказы на биржах</div>
            </div>
        </div>
    </div>
    
    <div class="toast" id="toast"></div>
    
    <div class="modal" id="modal" onclick="closeModal(event)">
        <div class="modal-content" onclick="event.stopPropagation()">
            <div class="modal-title">✨ AI-отклик</div>
            <div class="modal-text" id="modalText">Загрузка...</div>
            <button class="modal-btn" onclick="copyText()">📋 Скопировать</button>
        </div>
    </div>
    
    <script>
        const API_BASE = "{api_base}";
        const tg = window.Telegram.WebApp;
        
        let orders = [];
        
        // Init
        tg.ready();
        tg.expand();
        
        document.addEventListener('DOMContentLoaded', async () => {{
            await loadStats();
            await loadOrders();
            haptic('light');
        }});
        
        function haptic(type) {{
            if (tg.HapticFeedback) {{
                if (type === 'light') tg.HapticFeedback.impactOccurred('light');
                else if (type === 'medium') tg.HapticFeedback.impactOccurred('medium');
                else if (type === 'heavy') tg.HapticFeedback.impactOccurred('heavy');
                else if (type === 'success') tg.HapticFeedback.notificationOccurred('success');
                else if (type === 'error') tg.HapticFeedback.notificationOccurred('error');
            }}
        }}
        
        async function loadStats() {{
            try {{
                const res = await fetch(API_BASE + '/api/stats');
                const data = await res.json();
                document.getElementById('ordersCount').textContent = data.total_orders || 0;
                document.getElementById('responsesCount').textContent = data.responses || 0;
                document.getElementById('earnings').textContent = data.earnings ? data.earnings.toLocaleString() : '0';
            }} catch (e) {{
                console.error('Stats error:', e);
            }}
        }}
        
        async function loadOrders() {{
            const list = document.getElementById('ordersList');
            list.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
            
            try {{
                const res = await fetch(API_BASE + '/api/orders');
                orders = await res.json();
                
                document.getElementById('ordersCountBadge').textContent = orders.length;
                
                if (orders.length === 0) {{
                    list.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-icon">🔍</div>
                            <div class="empty-title">Пока нет заказов</div>
                            <div class="empty-text">Нажми «Найти заказы» для поиска</div>
                        </div>`;
                    return;
                }}
                
                list.innerHTML = orders.map(o => createOrderCard(o)).join('');
                
            }} catch (e) {{
                console.error('Orders error:', e);
                list.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon">⚠️</div>
                        <div class="empty-title">Ошибка загрузки</div>
                        <div class="empty-text">Попробуй обновить страницу</div>
                    </div>`;
            }}
        }}
        
        function createOrderCard(o) {{
            const sourceEmoji = {{ kwork: '🟢', 'fl.ru': '🔵', habr_freelance: '🟣', hh: '🔴' }};
            const sourceClass = o.source.replace('.', '').replace('_', '');
            const emoji = sourceEmoji[o.source] || '📋';
            
            const scoreClass = o.ai_score >= 70 ? 'high' : o.ai_score >= 50 ? 'medium' : 'low';
            
            return `
                <div class="order-card ${{o.hot ? 'hot' : ''}}">
                    <div class="order-header">
                        <div class="order-source ${{sourceClass}}">${{emoji}}</div>
                        <div class="order-info">
                            <div class="order-title">${{escapeHtml(o.title)}}</div>
                            <div class="order-meta">
                                <span>💰 ${{o.budget}}</span>
                                <span>⏰ ${{o.time_ago}}</span>
                            </div>
                        </div>
                    </div>
                    <div class="ai-score">
                        <span>🎯 Match</span>
                        <div class="score-bar"><div class="score-fill ${{scoreClass}}" style="width: ${{o.ai_score}}%"></div></div>
                        <span class="score-value ${{scoreClass}}">${{o.ai_score}}%</span>
                    </div>
                    <div class="order-actions">
                        <button class="order-btn primary" onclick="generateResponse(${{o.id}})">✨ Отклик</button>
                        <button class="order-btn secondary" onclick="openOrder('${{o.url}}')">🔗 Открыть</button>
                    </div>
                </div>`;
        }}
        
        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}
        
        async function turboParse() {{
            const btn = document.getElementById('turboBtn');
            const icon = document.getElementById('turboIcon');
            const text = document.getElementById('turboText');
            
            btn.disabled = true;
            icon.textContent = '🔄';
            text.textContent = 'ИЩЕМ ЗАКАЗЫ...';
            haptic('heavy');
            
            try {{
                const res = await fetch(API_BASE + '/api/turbo-parse', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ initData: tg.initData }})
                }});
                const data = await res.json();
                
                if (data.success) {{
                    showToast(`✅ Найдено ${{data.new_orders}} новых заказов!`);
                    haptic('success');
                    await loadStats();
                    await loadOrders();
                }} else {{
                    showToast('⚠️ Ошибка поиска', true);
                    haptic('error');
                }}
            }} catch (e) {{
                console.error('Parse error:', e);
                showToast('⚠️ Ошибка соединения', true);
                haptic('error');
            }}
            
            icon.textContent = '⚡';
            text.textContent = 'НАЙТИ ЗАКАЗЫ';
            btn.disabled = false;
        }}
        
        async function generateResponse(orderId) {{
            haptic('medium');
            
            const modal = document.getElementById('modal');
            const modalText = document.getElementById('modalText');
            
            modal.classList.add('show');
            modalText.textContent = 'Генерирую отклик...';
            
            try {{
                const res = await fetch(API_BASE + '/api/generate-response', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ order_id: orderId, initData: tg.initData }})
                }});
                const data = await res.json();
                modalText.textContent = data.response;
                haptic('success');
            }} catch (e) {{
                modalText.textContent = 'Ошибка генерации. Попробуйте ещё раз.';
                haptic('error');
            }}
        }}
        
        function copyText() {{
            const text = document.getElementById('modalText').textContent;
            navigator.clipboard.writeText(text).then(() => {{
                showToast('📋 Скопировано!');
                haptic('success');
                closeModal();
            }});
        }}
        
        function closeModal(e) {{
            if (!e || e.target.classList.contains('modal')) {{
                document.getElementById('modal').classList.remove('show');
            }}
        }}
        
        function openOrder(url) {{
            haptic('light');
            tg.openLink(url);
        }}
        
        function showToast(msg, isError = false) {{
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.className = 'toast' + (isError ? ' error' : '');
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 3000);
        }}
    </script>
</body>
</html>'''


# ===== CREATE APP =====

def create_web_app():
    app = web.Application()
    
    # Pages
    app.router.add_get('/', handle_index)
    app.router.add_get('/health', handle_health)
    app.router.add_get('/webapp', handle_webapp)
    
    # API
    app.router.add_get('/api/user', api_user)
    app.router.add_get('/api/orders', api_orders)
    app.router.add_get('/api/stats', api_stats)
    app.router.add_post('/api/turbo-parse', api_turbo_parse)
    app.router.add_post('/api/generate-response', api_generate_response)
    
    logger.info("Routes registered")
    return app


# ===== MAIN =====

async def main():
    await init_db()
    logger.info("Database initialized")
    
    bot = Bot(
        token=Config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    dp.include_router(start.router)
    dp.include_router(categories.router)
    dp.include_router(subscription.router)
    dp.include_router(generate_response.router)
    dp.include_router(profile.router)
    dp.include_router(orders.router)
    
    app = create_web_app()
    
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '')
    logger.info(f"Domain: {{domain}}")
    
    if domain:
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(f"https://{{domain}}/webhook")
        
        logger.info(f"Webhook: https://{{domain}}/webhook")
        logger.info(f"WebApp: https://{{domain}}/webapp")
        
        webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_handler.register(app, path='/webhook')
        setup_application(app, dp, bot=bot)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', Config.WEBAPP_PORT)
        await site.start()
        
        logger.info(f"Server on port {{Config.WEBAPP_PORT}}")
        await asyncio.Event().wait()
    else:
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', Config.WEBAPP_PORT)
        await site.start()
        
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
