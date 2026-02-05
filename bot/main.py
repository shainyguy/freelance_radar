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
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data))
        check_hash = parsed.pop('hash', '')
        data_check_string = '\n'.join(f'{k}={v}' for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b'WebAppData', Config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if calculated_hash == check_hash:
            return json.loads(parsed.get('user', '{}'))
        return None
    except:
        return None


async def get_user_from_request(request: web.Request):
    init_data = request.headers.get('X-Telegram-Init-Data', '') or request.query.get('initData', '')
    if not init_data:
        try:
            body = await request.json()
            init_data = body.get('initData', '')
        except:
            pass
    
    user_data = verify_telegram_data(init_data)
    if user_data:
        return await Database.get_or_create_user(
            telegram_id=user_data.get('id'),
            username=user_data.get('username'),
            full_name=f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
        )
    return None


# ===== API =====

async def api_user(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'id': 0, 'is_new': True})
    
    from datetime import datetime
    days_left = 0
    if user.subscription_end:
        days_left = max(0, (user.subscription_end - datetime.utcnow()).days)
    
    return web.json_response({
        'id': user.id,
        'telegram_id': user.telegram_id,
        'username': user.username or 'Аноним',
        'full_name': user.full_name or 'Пользователь',
        'has_subscription': user.has_active_subscription(),
        'subscription_days': days_left,
        'categories': user.categories or [],
        'min_budget': user.min_budget or 0,
        'is_active': user.is_active,
        'created_at': user.created_at.isoformat() if user.created_at else None
    })


async def api_orders(request: web.Request) -> web.Response:
    category = request.query.get('category', 'all')
    
    from database.db import async_session
    from database.models import Order
    from sqlalchemy import select, desc
    from datetime import datetime, timezone
    
    async with async_session() as session:
        query = select(Order).order_by(desc(Order.created_at)).limit(50)
        if category != 'all':
            query = query.where(Order.category == category)
        result = await session.execute(query)
        db_orders = result.scalars().all()
    
    orders_data = []
    for order in db_orders:
        now = datetime.now(timezone.utc)
        created = order.created_at.replace(tzinfo=timezone.utc) if order.created_at.tzinfo is None else order.created_at
        diff = (now - created).total_seconds()
        
        if diff < 60: time_ago = "сейчас"
        elif diff < 3600: time_ago = f"{int(diff // 60)} мин"
        elif diff < 86400: time_ago = f"{int(diff // 3600)} ч"
        else: time_ago = f"{int(diff // 86400)} дн"
        
        score = 50
        if order.budget_value and order.budget_value >= 50000: score += 35
        elif order.budget_value and order.budget_value >= 20000: score += 20
        if diff < 1800: score += 15
        score = min(score, 99)
        
        orders_data.append({
            'id': order.id,
            'title': order.title,
            'description': (order.description or '')[:300],
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


async def api_stats(request: web.Request) -> web.Response:
    from database.db import async_session
    from database.models import Order
    from sqlalchemy import select, func
    
    async with async_session() as session:
        result = await session.execute(select(func.count(Order.id)))
        total = result.scalar() or 0
        
        # Считаем по источникам
        sources_result = await session.execute(
            select(Order.source, func.count(Order.id)).group_by(Order.source)
        )
        sources = {row[0]: row[1] for row in sources_result}
    
    return web.json_response({
        'total_orders': total,
        'by_source': sources,
        'responses': 0,
        'earnings': 0
    })


async def api_turbo_parse(request: web.Request) -> web.Response:
    from parsers import ALL_PARSERS
    
    new_count = 0
    categories = ['design', 'python', 'copywriting', 'marketing']
    
    for parser in ALL_PARSERS:
        for category in categories:
            try:
                found = await parser.parse_orders(category)
                for order_data in found:
                    order = await Database.save_order(order_data)
                    if order:
                        new_count += 1
            except Exception as e:
                logger.error(f"Parse error {parser.SOURCE_NAME}: {e}")
        try:
            await parser.close()
        except:
            pass
    
    return web.json_response({'success': True, 'new_orders': new_count})


async def api_generate_response(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        order_id = body.get('order_id')
        order = await Database.get_order_by_id(order_id)
        
        if not order:
            return web.json_response({'error': 'Not found'}, status=404)
        
        from services.gigachat import gigachat_service
        response = await gigachat_service.generate_response(order.title, order.description or '')
        return web.json_response({'response': response})
    except Exception as e:
        return web.json_response({
            'response': "Здравствуйте!\n\nЗаинтересовал ваш проект. Имею опыт в данной области.\n\nГотов обсудить детали! 🚀"
        })


async def api_save_categories(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    body = await request.json()
    categories = body.get('categories', [])
    await Database.update_user_categories(user.telegram_id, categories)
    return web.json_response({'success': True})


# ===== WEB HANDLERS =====

async def handle_index(request):
    return web.Response(text="Freelance Radar Bot is running!")

async def handle_health(request):
    return web.Response(text="OK")

async def handle_webapp(request):
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', request.host)
    api_base = f"https://{domain}" if domain else ""
    return web.Response(text=get_webapp_html(api_base), content_type='text/html', charset='utf-8')


def get_webapp_html(api_base: str) -> str:
    return '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Freelance Radar</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg: #0a0a0f; --bg2: #12121a; --card: rgba(255,255,255,0.05);
            --border: rgba(255,255,255,0.1); --text: #fff; --text2: #888;
            --accent: #6c5ce7; --accent2: #a29bfe; --success: #00d26a;
            --warning: #ffc107; --danger: #ff4757;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: var(--bg);
               color: var(--text); min-height: 100vh; padding-bottom: 80px; }
        
        /* Header */
        .header { background: var(--bg2); padding: 16px; text-align: center; border-bottom: 1px solid var(--border); }
        .logo { font-size: 32px; }
        .title { font-size: 18px; font-weight: 700; background: linear-gradient(135deg, var(--accent), var(--accent2));
                 -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        
        /* Tabs */
        .tabs { display: flex; background: var(--bg2); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 100; }
        .tab { flex: 1; padding: 14px 8px; text-align: center; font-size: 13px; font-weight: 500; color: var(--text2);
               border-bottom: 2px solid transparent; cursor: pointer; transition: all 0.2s; }
        .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
        .tab-icon { font-size: 18px; display: block; margin-bottom: 4px; }
        
        /* Pages */
        .page { display: none; padding: 16px; }
        .page.active { display: block; }
        
        /* Stats */
        .stats { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 16px; }
        .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 14px; text-align: center; }
        .stat-value { font-size: 24px; font-weight: 700; color: var(--accent); }
        .stat-label { font-size: 11px; color: var(--text2); margin-top: 4px; }
        
        /* Button */
        .btn { width: 100%; padding: 14px; border: none; border-radius: 12px; font-size: 15px; font-weight: 600;
               cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; margin-bottom: 16px; }
        .btn-primary { background: linear-gradient(135deg, var(--accent), var(--accent2)); color: white; }
        .btn-secondary { background: var(--card); color: white; border: 1px solid var(--border); }
        .btn:disabled { opacity: 0.6; }
        .btn:active { transform: scale(0.98); }
        
        /* Section */
        .section-title { font-size: 15px; font-weight: 600; margin: 16px 0 12px; display: flex; align-items: center; gap: 8px; }
        .badge { background: var(--accent); padding: 2px 8px; border-radius: 10px; font-size: 11px; }
        
        /* Order Card */
        .order-card { background: var(--card); border: 1px solid var(--border); border-radius: 14px;
                      padding: 14px; margin-bottom: 10px; position: relative; }
        .order-card.hot::after { content: '🔥'; position: absolute; top: 10px; right: 10px; }
        .order-header { display: flex; gap: 10px; margin-bottom: 10px; }
        .order-source { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center;
                        justify-content: center; font-size: 16px; font-weight: 600; flex-shrink: 0; }
        .order-source.hh { background: #d63031; }
        .order-source.kwork { background: #00b894; }
        .order-source.fl { background: #0984e3; }
        .order-source.freelance { background: #6c5ce7; }
        .order-info { flex: 1; min-width: 0; }
        .order-title { font-size: 13px; font-weight: 600; line-height: 1.3; margin-bottom: 4px;
                       display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .order-meta { display: flex; gap: 10px; font-size: 11px; color: var(--text2); flex-wrap: wrap; }
        .order-actions { display: flex; gap: 8px; margin-top: 10px; }
        .order-btn { flex: 1; padding: 10px; border: none; border-radius: 10px; font-size: 12px; font-weight: 600; cursor: pointer; }
        .order-btn.primary { background: var(--accent); color: white; }
        .order-btn.secondary { background: var(--card); color: white; border: 1px solid var(--border); }
        
        /* Profile */
        .profile-header { text-align: center; padding: 20px 0; }
        .avatar { width: 80px; height: 80px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--accent2));
                  display: flex; align-items: center; justify-content: center; font-size: 32px; margin: 0 auto 12px; }
        .profile-name { font-size: 18px; font-weight: 600; }
        .profile-username { font-size: 13px; color: var(--text2); }
        
        .profile-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 20px 0; }
        .profile-stat { background: var(--card); border-radius: 12px; padding: 12px; text-align: center; }
        .profile-stat-value { font-size: 20px; font-weight: 700; color: var(--accent); }
        .profile-stat-label { font-size: 10px; color: var(--text2); margin-top: 2px; }
        
        .setting-item { background: var(--card); border-radius: 12px; padding: 14px; margin-bottom: 8px;
                        display: flex; align-items: center; justify-content: space-between; }
        .setting-info { display: flex; align-items: center; gap: 12px; }
        .setting-icon { font-size: 20px; }
        .setting-text h4 { font-size: 14px; font-weight: 500; }
        .setting-text p { font-size: 11px; color: var(--text2); }
        
        /* Categories */
        .categories-grid { display: flex; flex-wrap: wrap; gap: 8px; }
        .category-chip { padding: 10px 16px; background: var(--card); border: 1px solid var(--border);
                         border-radius: 20px; font-size: 13px; cursor: pointer; transition: all 0.2s; }
        .category-chip.active { background: var(--accent); border-color: var(--accent); }
        
        /* Empty State */
        .empty-state { text-align: center; padding: 40px 20px; }
        .empty-icon { font-size: 48px; margin-bottom: 12px; }
        .empty-title { font-size: 16px; font-weight: 600; margin-bottom: 6px; }
        .empty-text { font-size: 13px; color: var(--text2); }
        
        /* Loading */
        .loading { text-align: center; padding: 30px; }
        .spinner { display: inline-block; width: 24px; height: 24px; border: 3px solid var(--border);
                   border-top-color: var(--accent); border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        
        /* Toast */
        .toast { position: fixed; bottom: 90px; left: 50%; transform: translateX(-50%) translateY(100px);
                 background: var(--success); color: white; padding: 12px 20px; border-radius: 10px;
                 font-size: 13px; opacity: 0; transition: all 0.3s; z-index: 1000; }
        .toast.error { background: var(--danger); }
        .toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }
        
        /* Modal */
        .modal { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8);
                 display: none; align-items: center; justify-content: center; z-index: 2000; padding: 20px; }
        .modal.show { display: flex; }
        .modal-content { background: var(--bg2); border-radius: 16px; padding: 20px; width: 100%; max-height: 80vh; overflow-y: auto; }
        .modal-title { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
        .modal-text { font-size: 14px; line-height: 1.5; white-space: pre-wrap; margin-bottom: 16px;
                      background: var(--card); padding: 12px; border-radius: 10px; }
        .modal-btn { width: 100%; padding: 14px; background: var(--success); border: none; border-radius: 10px;
                     color: white; font-size: 14px; font-weight: 600; cursor: pointer; }
        
        /* Subscription Banner */
        .sub-banner { background: linear-gradient(135deg, var(--accent), var(--accent2)); border-radius: 14px;
                      padding: 16px; margin-bottom: 16px; position: relative; overflow: hidden; }
        .sub-banner h3 { font-size: 15px; margin-bottom: 4px; }
        .sub-banner p { font-size: 12px; opacity: 0.9; }
        .sub-price { font-size: 24px; font-weight: 700; margin: 8px 0; }
    </style>
</head>
<body>
    <!-- Header -->
    <div class="header">
        <div class="logo">📡</div>
        <div class="title">Freelance Radar</div>
    </div>
    
    <!-- Tabs -->
    <div class="tabs">
        <div class="tab active" onclick="showPage('orders')">
            <span class="tab-icon">📋</span>Заказы
        </div>
        <div class="tab" onclick="showPage('search')">
            <span class="tab-icon">🔍</span>Поиск
        </div>
        <div class="tab" onclick="showPage('profile')">
            <span class="tab-icon">👤</span>Профиль
        </div>
    </div>
    
    <!-- Orders Page -->
    <div class="page active" id="page-orders">
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value" id="totalOrders">—</div>
                <div class="stat-label">Всего заказов</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="newOrders">—</div>
                <div class="stat-label">Новых сегодня</div>
            </div>
        </div>
        
        <button class="btn btn-primary" id="turboBtn" onclick="turboParse()">
            <span id="turboIcon">⚡</span>
            <span id="turboText">НАЙТИ ЗАКАЗЫ</span>
        </button>
        
        <div class="section-title">
            <span>📋 Последние заказы</span>
            <span class="badge" id="ordersCount">0</span>
        </div>
        
        <div id="ordersList"></div>
    </div>
    
    <!-- Search Page -->
    <div class="page" id="page-search">
        <div class="section-title">🎯 Категории</div>
        <p style="font-size: 12px; color: var(--text2); margin-bottom: 12px;">Выбери категории для поиска заказов</p>
        
        <div class="categories-grid" id="categoriesGrid"></div>
        
        <button class="btn btn-primary" style="margin-top: 20px;" onclick="saveCategories()">
            💾 Сохранить
        </button>
        
        <div class="section-title" style="margin-top: 24px;">📊 Статистика по биржам</div>
        <div id="sourcesStats"></div>
    </div>
    
    <!-- Profile Page -->
    <div class="page" id="page-profile">
        <div class="profile-header">
            <div class="avatar" id="userAvatar">👤</div>
            <div class="profile-name" id="userName">Загрузка...</div>
            <div class="profile-username" id="userUsername">@...</div>
        </div>
        
        <div class="profile-stats">
            <div class="profile-stat">
                <div class="profile-stat-value" id="profileOrders">0</div>
                <div class="profile-stat-label">Просмотрено</div>
            </div>
            <div class="profile-stat">
                <div class="profile-stat-value" id="profileResponses">0</div>
                <div class="profile-stat-label">Откликов</div>
            </div>
            <div class="profile-stat">
                <div class="profile-stat-value" id="profileEarnings">0</div>
                <div class="profile-stat-label">Заработано</div>
            </div>
        </div>
        
        <div id="subBanner"></div>
        
        <div class="section-title">⚙️ Настройки</div>
        
        <div class="setting-item">
            <div class="setting-info">
                <div class="setting-icon">🔔</div>
                <div class="setting-text">
                    <h4>Уведомления</h4>
                    <p>Получать новые заказы</p>
                </div>
            </div>
            <span style="color: var(--success);">Вкл</span>
        </div>
        
        <div class="setting-item">
            <div class="setting-info">
                <div class="setting-icon">💰</div>
                <div class="setting-text">
                    <h4>Мин. бюджет</h4>
                    <p id="minBudgetText">Не установлен</p>
                </div>
            </div>
        </div>
        
        <div class="setting-item">
            <div class="setting-info">
                <div class="setting-icon">🎯</div>
                <div class="setting-text">
                    <h4>Категории</h4>
                    <p id="categoriesText">Не выбраны</p>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Toast -->
    <div class="toast" id="toast"></div>
    
    <!-- Modal -->
    <div class="modal" id="modal" onclick="closeModal(event)">
        <div class="modal-content" onclick="event.stopPropagation()">
            <div class="modal-title">✨ AI-отклик</div>
            <div class="modal-text" id="modalText">Загрузка...</div>
            <button class="modal-btn" onclick="copyText()">📋 Скопировать</button>
        </div>
    </div>
    
    <script>
        const API = "''' + api_base + '''";
        const tg = window.Telegram.WebApp;
        
        let orders = [];
        let user = null;
        let selectedCategories = [];
        
        const CATEGORIES = [
            { id: 'python', name: '🐍 Python', icon: '🐍' },
            { id: 'design', name: '🎨 Дизайн', icon: '🎨' },
            { id: 'copywriting', name: '✍️ Тексты', icon: '✍️' },
            { id: 'marketing', name: '📈 Маркетинг', icon: '📈' },
        ];
        
        // Init
        tg.ready();
        tg.expand();
        
        document.addEventListener('DOMContentLoaded', async () => {
            await loadUser();
            await loadOrders();
            await loadStats();
            renderCategories();
            haptic('light');
        });
        
        function haptic(type) {
            if (!tg.HapticFeedback) return;
            if (type === 'success') tg.HapticFeedback.notificationOccurred('success');
            else if (type === 'error') tg.HapticFeedback.notificationOccurred('error');
            else tg.HapticFeedback.impactOccurred(type);
        }
        
        function showPage(name) {
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById('page-' + name).classList.add('active');
            event.currentTarget.classList.add('active');
            haptic('light');
        }
        
        async function loadUser() {
            try {
                const res = await fetch(API + '/api/user', {
                    headers: { 'X-Telegram-Init-Data': tg.initData }
                });
                user = await res.json();
                
                document.getElementById('userName').textContent = user.full_name || 'Пользователь';
                document.getElementById('userUsername').textContent = user.username ? '@' + user.username : '';
                
                if (user.min_budget) {
                    document.getElementById('minBudgetText').textContent = user.min_budget.toLocaleString() + ' ₽';
                }
                
                if (user.categories && user.categories.length) {
                    selectedCategories = user.categories;
                    document.getElementById('categoriesText').textContent = user.categories.join(', ');
                }
                
                // Subscription banner
                if (user.has_subscription) {
                    document.getElementById('subBanner').innerHTML = `
                        <div class="setting-item" style="background: linear-gradient(135deg, var(--success), #00b894);">
                            <div class="setting-info">
                                <div class="setting-icon">✅</div>
                                <div class="setting-text">
                                    <h4 style="color: white;">Подписка активна</h4>
                                    <p style="color: rgba(255,255,255,0.8);">Осталось ${user.subscription_days} дней</p>
                                </div>
                            </div>
                        </div>`;
                } else {
                    document.getElementById('subBanner').innerHTML = `
                        <div class="sub-banner">
                            <h3>🚀 Получи полный доступ</h3>
                            <p>AI-отклики, уведомления, все биржи</p>
                            <div class="sub-price">690 ₽/мес</div>
                            <button class="btn btn-secondary" style="background: white; color: var(--accent);" 
                                    onclick="tg.openLink('https://t.me/FreelanceRadarBot')">
                                Попробовать 3 дня бесплатно
                            </button>
                        </div>`;
                }
            } catch (e) {
                console.error('User error:', e);
            }
        }
        
        async function loadStats() {
            try {
                const res = await fetch(API + '/api/stats');
                const data = await res.json();
                
                document.getElementById('totalOrders').textContent = data.total_orders || 0;
                document.getElementById('newOrders').textContent = Math.min(data.total_orders || 0, 50);
                
                // Sources stats
                if (data.by_source) {
                    const html = Object.entries(data.by_source).map(([source, count]) => `
                        <div class="setting-item">
                            <div class="setting-info">
                                <div class="setting-icon">${getSourceEmoji(source)}</div>
                                <div class="setting-text">
                                    <h4>${source}</h4>
                                    <p>${count} заказов</p>
                                </div>
                            </div>
                        </div>
                    `).join('');
                    document.getElementById('sourcesStats').innerHTML = html || '<p style="color: var(--text2);">Нет данных</p>';
                }
            } catch (e) {
                console.error('Stats error:', e);
            }
        }
        
        async function loadOrders() {
            const list = document.getElementById('ordersList');
            list.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
            
            try {
                const res = await fetch(API + '/api/orders');
                orders = await res.json();
                
                document.getElementById('ordersCount').textContent = orders.length;
                
                if (!orders.length) {
                    list.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-icon">🔍</div>
                            <div class="empty-title">Пока нет заказов</div>
                            <div class="empty-text">Нажми «Найти заказы» для поиска</div>
                        </div>`;
                    return;
                }
                
                list.innerHTML = orders.map(o => createOrderCard(o)).join('');
            } catch (e) {
                list.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon">⚠️</div>
                        <div class="empty-title">Ошибка загрузки</div>
                    </div>`;
            }
        }
        
        function getSourceEmoji(source) {
            const map = { hh: '🔴', kwork: '🟢', 'fl.ru': '🔵', 'freelance.ru': '🟣' };
            return map[source] || '📋';
        }
        
        function getSourceClass(source) {
            if (source.includes('kwork')) return 'kwork';
            if (source.includes('fl')) return 'fl';
            if (source.includes('hh')) return 'hh';
            return 'freelance';
        }
        
        function createOrderCard(o) {
            return `
                <div class="order-card ${o.hot ? 'hot' : ''}">
                    <div class="order-header">
                        <div class="order-source ${getSourceClass(o.source)}">${getSourceEmoji(o.source)}</div>
                        <div class="order-info">
                            <div class="order-title">${escapeHtml(o.title)}</div>
                            <div class="order-meta">
                                <span>💰 ${o.budget}</span>
                                <span>⏰ ${o.time_ago}</span>
                                <span>📍 ${o.source}</span>
                            </div>
                        </div>
                    </div>
                    <div class="order-actions">
                        <button class="order-btn primary" onclick="generateResponse(${o.id})">✨ Отклик</button>
                        <button class="order-btn secondary" onclick="openOrder('${escapeHtml(o.url)}')">🔗 Открыть</button>
                    </div>
                </div>`;
        }
        
        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function renderCategories() {
            const grid = document.getElementById('categoriesGrid');
            grid.innerHTML = CATEGORIES.map(c => `
                <div class="category-chip ${selectedCategories.includes(c.id) ? 'active' : ''}" 
                     onclick="toggleCategory('${c.id}', this)">
                    ${c.name}
                </div>
            `).join('');
        }
        
        function toggleCategory(id, el) {
            haptic('light');
            if (selectedCategories.includes(id)) {
                selectedCategories = selectedCategories.filter(c => c !== id);
                el.classList.remove('active');
            } else {
                selectedCategories.push(id);
                el.classList.add('active');
            }
        }
        
        async function saveCategories() {
            try {
                await fetch(API + '/api/save-categories', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ categories: selectedCategories, initData: tg.initData })
                });
                showToast('✅ Категории сохранены!');
                haptic('success');
            } catch (e) {
                showToast('❌ Ошибка сохранения', true);
            }
        }
        
        async function turboParse() {
            const btn = document.getElementById('turboBtn');
            const icon = document.getElementById('turboIcon');
            const text = document.getElementById('turboText');
            
            btn.disabled = true;
            icon.textContent = '🔄';
            text.textContent = 'ИЩЕМ...';
            haptic('heavy');
            
            try {
                const res = await fetch(API + '/api/turbo-parse', { method: 'POST' });
                const data = await res.json();
                
                showToast(`✅ Найдено ${data.new_orders} заказов!`);
                haptic('success');
                
                await loadStats();
                await loadOrders();
            } catch (e) {
                showToast('❌ Ошибка поиска', true);
                haptic('error');
            }
            
            icon.textContent = '⚡';
            text.textContent = 'НАЙТИ ЗАКАЗЫ';
            btn.disabled = false;
        }
        
        async function generateResponse(orderId) {
            haptic('medium');
            
            const modal = document.getElementById('modal');
            const modalText = document.getElementById('modalText');
            
            modal.classList.add('show');
            modalText.textContent = '✨ Генерирую отклик...';
            
            try {
                const res = await fetch(API + '/api/generate-response', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ order_id: orderId })
                });
                const data = await res.json();
                modalText.textContent = data.response;
                haptic('success');
            } catch (e) {
                modalText.textContent = 'Ошибка генерации';
                haptic('error');
            }
        }
        
        function copyText() {
            const text = document.getElementById('modalText').textContent;
            navigator.clipboard.writeText(text).then(() => {
                showToast('📋 Скопировано!');
                haptic('success');
                closeModal();
            });
        }
        
        function closeModal(e) {
            if (!e || e.target.classList.contains('modal')) {
                document.getElementById('modal').classList.remove('show');
            }
        }
        
        function openOrder(url) {
            haptic('light');
            tg.openLink(url);
        }
        
        function showToast(msg, isError = false) {
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.className = 'toast' + (isError ? ' error' : '');
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 3000);
        }
    </script>
</body>
</html>'''


# ===== APP =====

def create_web_app():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/health', handle_health)
    app.router.add_get('/webapp', handle_webapp)
    app.router.add_get('/api/user', api_user)
    app.router.add_get('/api/orders', api_orders)
    app.router.add_get('/api/stats', api_stats)
    app.router.add_post('/api/turbo-parse', api_turbo_parse)
    app.router.add_post('/api/generate-response', api_generate_response)
    app.router.add_post('/api/save-categories', api_save_categories)
    return app


async def main():
    await init_db()
    logger.info("Database initialized")
    
    bot = Bot(token=Config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    
    dp.include_router(start.router)
    dp.include_router(categories.router)
    dp.include_router(subscription.router)
    dp.include_router(generate_response.router)
    dp.include_router(profile.router)
    dp.include_router(orders.router)
    
    app = create_web_app()
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '')
    
    if domain:
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(f"https://{domain}/webhook")
        logger.info(f"Webhook: https://{domain}/webhook")
        
        webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_handler.register(app, path='/webhook')
        setup_application(app, dp, bot=bot)
        
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, '0.0.0.0', Config.WEBAPP_PORT).start()
        logger.info(f"Server on port {Config.WEBAPP_PORT}")
        await asyncio.Event().wait()
    else:
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, '0.0.0.0', Config.WEBAPP_PORT).start()
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
