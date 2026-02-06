# bot/main.py
import asyncio
import logging
import os
import json
import hashlib
import hmac
from urllib.parse import parse_qsl
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import Config
from database.db import Database, init_db

from bot.handlers import start, categories, subscription, generate_response, profile, orders

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============ AUTH ============

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
    except Exception as e:
        logger.error(f"Auth error: {e}")
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


# ============ API ============

async def api_user(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    
    if not user:
        return web.json_response({
            'id': 0, 
            'is_new': True,
            'is_admin': False,
            'is_pro': False,
            'has_subscription': False
        })
    
    is_admin = Config.is_admin(user.telegram_id)
    is_pro = is_admin or (user.subscription_type == 'pro' and user.has_active_subscription())
    has_sub = is_admin or user.has_active_subscription()
    
    days_left = 0
    if user.subscription_end:
        days_left = max(0, (user.subscription_end - datetime.utcnow()).days)
    
    return web.json_response({
        'id': user.id,
        'telegram_id': user.telegram_id,
        'username': user.username or '',
        'full_name': user.full_name or 'Пользователь',
        'is_admin': is_admin,
        'is_pro': is_pro,
        'has_subscription': has_sub,
        'subscription_type': 'pro' if is_admin else (user.subscription_type or 'free'),
        'subscription_days': 999 if is_admin else days_left,
        'trial_used': user.trial_used if hasattr(user, 'trial_used') else False,
        'categories': user.categories or [],
        'predator_mode': getattr(user, 'predator_mode', False),
    })


async def api_orders(request: web.Request) -> web.Response:
    try:
        db_orders = await Database.get_orders(limit=30)
        
        orders_data = []
        for order in db_orders:
            # Время назад
            now = datetime.utcnow()
            created = order.created_at if order.created_at else now
            diff = (now - created).total_seconds()
            
            if diff < 60:
                time_ago = "сейчас"
            elif diff < 3600:
                time_ago = f"{int(diff // 60)} мин"
            elif diff < 86400:
                time_ago = f"{int(diff // 3600)} ч"
            else:
                time_ago = f"{int(diff // 86400)} дн"
            
            orders_data.append({
                'id': order.id,
                'title': order.title or 'Без названия',
                'source': order.source or 'unknown',
                'budget': order.budget or 'Договорная',
                'budget_value': order.budget_value or 0,
                'url': order.url or '',
                'time_ago': time_ago,
                'hot': (order.budget_value or 0) >= 30000,
            })
        
        return web.json_response(orders_data)
    except Exception as e:
        logger.error(f"Orders error: {e}")
        return web.json_response([])


async def api_turbo_parse(request: web.Request) -> web.Response:
    try:
        from parsers import ALL_PARSERS
        
        new_count = 0
        categories = ['python', 'design', 'copywriting', 'marketing']
        
        for parser in ALL_PARSERS:
            for cat in categories:
                try:
                    found = await parser.parse_orders(cat)
                    for order_data in found:
                        order = await Database.save_order(order_data)
                        if order:
                            new_count += 1
                except Exception as e:
                    logger.error(f"Parse {parser.SOURCE_NAME}/{cat}: {e}")
            try:
                await parser.close()
            except:
                pass
        
        return web.json_response({'success': True, 'new_orders': new_count})
    except Exception as e:
        logger.error(f"Turbo parse error: {e}")
        return web.json_response({'success': False, 'new_orders': 0, 'error': str(e)})


async def api_generate_response(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        order_id = body.get('order_id')
        
        order = await Database.get_order_by_id(order_id)
        if not order:
            return web.json_response({'response': 'Заказ не найден'})
        
        from services.gigachat import gigachat_service
        response = await gigachat_service.generate_response(order.title, order.description or '')
        
        return web.json_response({'response': response})
    except Exception as e:
        logger.error(f"Generate error: {e}")
        return web.json_response({
            'response': f"Здравствуйте!\n\nЗаинтересовал ваш проект. Имею опыт в данной области.\n\nГотов обсудить детали!"
        })


async def api_trial(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'success': False, 'message': 'Не авторизован'})
    
    try:
        success = await Database.start_user_trial(user.telegram_id, 'pro')
        if success:
            return web.json_response({'success': True, 'message': 'Пробный период активирован!'})
        else:
            return web.json_response({'success': False, 'message': 'Пробный период уже использован'})
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)})


async def api_settings(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'success': False})
    
    try:
        body = await request.json()
        
        if 'categories' in body:
            await Database.update_user_categories(user.telegram_id, body['categories'])
        if 'predator_mode' in body:
            await Database.update_user_settings(user.telegram_id, predator_mode=body['predator_mode'])
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})


# ============ WEB ============

async def handle_index(request):
    return web.Response(text="Freelance Radar Bot is running!")

async def handle_health(request):
    return web.Response(text="OK")

async def handle_webapp(request):
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
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:#0a0a0f; color:#fff; min-height:100vh; padding:16px; padding-bottom:80px; }}
        
        .header {{ text-align:center; margin-bottom:20px; }}
        .logo {{ font-size:40px; margin-bottom:8px; }}
        .title {{ font-size:20px; font-weight:700; background:linear-gradient(135deg,#6c5ce7,#a29bfe); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
        .subtitle {{ font-size:12px; color:#888; margin-top:4px; }}
        
        .user-badge {{ display:inline-block; background:#6c5ce7; color:#fff; font-size:10px; padding:4px 10px; border-radius:10px; margin-top:8px; }}
        .user-badge.admin {{ background:linear-gradient(135deg,#9b59b6,#8e44ad); }}
        .user-badge.pro {{ background:linear-gradient(135deg,#f39c12,#e67e22); }}
        
        .btn {{ width:100%; padding:14px; border:none; border-radius:12px; font-size:15px; font-weight:600; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:8px; margin-bottom:12px; }}
        .btn-primary {{ background:linear-gradient(135deg,#6c5ce7,#a29bfe); color:#fff; }}
        .btn-success {{ background:#00d26a; color:#fff; }}
        .btn:disabled {{ opacity:0.6; }}
        .btn:active {{ transform:scale(0.98); }}
        
        .section {{ margin-top:20px; }}
        .section-title {{ font-size:14px; font-weight:600; margin-bottom:10px; display:flex; align-items:center; gap:8px; }}
        .badge {{ background:#6c5ce7; padding:2px 8px; border-radius:10px; font-size:11px; }}
        
        .order-card {{ background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:12px; padding:12px; margin-bottom:10px; }}
        .order-card.hot {{ border-color:#ff4757; }}
        .order-title {{ font-size:13px; font-weight:500; margin-bottom:6px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
        .order-meta {{ display:flex; gap:10px; font-size:11px; color:#888; flex-wrap:wrap; margin-bottom:10px; }}
        .order-actions {{ display:flex; gap:8px; }}
        .order-btn {{ flex:1; padding:10px; border:none; border-radius:8px; font-size:12px; font-weight:600; cursor:pointer; }}
        .order-btn.primary {{ background:#6c5ce7; color:#fff; }}
        .order-btn.secondary {{ background:rgba(255,255,255,0.1); color:#fff; }}
        
        .empty {{ text-align:center; padding:40px 20px; color:#888; }}
        .empty-icon {{ font-size:48px; margin-bottom:12px; }}
        
        .loading {{ text-align:center; padding:20px; }}
        .spinner {{ display:inline-block; width:24px; height:24px; border:3px solid rgba(255,255,255,0.1); border-top-color:#6c5ce7; border-radius:50%; animation:spin 1s linear infinite; }}
        @keyframes spin {{ to {{ transform:rotate(360deg); }} }}
        
        .toast {{ position:fixed; bottom:20px; left:50%; transform:translateX(-50%) translateY(100px); background:#00d26a; color:#fff; padding:12px 24px; border-radius:10px; font-size:14px; opacity:0; transition:all 0.3s; z-index:1000; }}
        .toast.error {{ background:#ff4757; }}
        .toast.show {{ transform:translateX(-50%) translateY(0); opacity:1; }}
        
        .modal {{ position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.9); display:none; align-items:center; justify-content:center; z-index:2000; padding:20px; }}
        .modal.show {{ display:flex; }}
        .modal-content {{ background:#1a1a2e; border-radius:16px; padding:20px; width:100%; max-width:400px; }}
        .modal-title {{ font-size:18px; font-weight:600; margin-bottom:16px; text-align:center; }}
        .modal-text {{ font-size:14px; line-height:1.6; background:rgba(255,255,255,0.05); padding:12px; border-radius:10px; margin-bottom:16px; white-space:pre-wrap; max-height:300px; overflow-y:auto; }}
        .modal-btn {{ width:100%; padding:14px; background:#00d26a; border:none; border-radius:10px; color:#fff; font-size:14px; font-weight:600; cursor:pointer; }}
        .modal-close {{ width:100%; padding:12px; background:transparent; border:1px solid rgba(255,255,255,0.2); border-radius:10px; color:#888; font-size:14px; cursor:pointer; margin-top:8px; }}
        
        .tabs {{ display:flex; gap:8px; margin-bottom:16px; }}
        .tab {{ flex:1; padding:10px; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:10px; text-align:center; font-size:12px; cursor:pointer; }}
        .tab.active {{ background:#6c5ce7; border-color:#6c5ce7; }}
        
        .settings-item {{ background:rgba(255,255,255,0.05); border-radius:10px; padding:12px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; }}
        .settings-label {{ font-size:13px; }}
        .toggle {{ width:44px; height:24px; background:rgba(255,255,255,0.2); border-radius:12px; position:relative; cursor:pointer; }}
        .toggle.active {{ background:#6c5ce7; }}
        .toggle::after {{ content:''; position:absolute; width:20px; height:20px; background:#fff; border-radius:50%; top:2px; left:2px; transition:0.2s; }}
        .toggle.active::after {{ left:22px; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">📡</div>
        <div class="title">Freelance Radar</div>
        <div class="subtitle">Охотник за заказами</div>
        <div class="user-badge" id="userBadge" style="display:none;">Загрузка...</div>
    </div>
    
    <div class="tabs">
        <div class="tab active" onclick="showTab('orders')">📋 Заказы</div>
        <div class="tab" onclick="showTab('settings')">⚙️ Настройки</div>
    </div>
    
    <div id="ordersTab">
        <button class="btn btn-primary" id="parseBtn" onclick="turboParse()">
            ⚡ НАЙТИ ЗАКАЗЫ
        </button>
        
        <div class="section">
            <div class="section-title">
                📋 Найденные заказы
                <span class="badge" id="ordersCount">0</span>
            </div>
            <div id="ordersList">
                <div class="empty">
                    <div class="empty-icon">🔍</div>
                    <div>Нажмите "Найти заказы" для поиска</div>
                </div>
            </div>
        </div>
    </div>
    
    <div id="settingsTab" style="display:none;">
        <div class="section-title">⚙️ Настройки</div>
        
        <div class="settings-item">
            <span class="settings-label">🦁 Режим Хищник (50K+)</span>
            <div class="toggle" id="predatorToggle" onclick="togglePredator()"></div>
        </div>
        
        <div class="section-title" style="margin-top:20px;">🎯 Категории</div>
        <div id="categoriesList"></div>
        
        <button class="btn btn-success" style="margin-top:16px;" onclick="saveSettings()">💾 Сохранить</button>
        
        <div class="section-title" style="margin-top:24px;">💳 Подписка</div>
        <div id="subscriptionInfo"></div>
    </div>
    
    <div class="toast" id="toast"></div>
    
    <div class="modal" id="modal" onclick="if(event.target===this)closeModal()">
        <div class="modal-content">
            <div class="modal-title" id="modalTitle">✨ AI-отклик</div>
            <div class="modal-text" id="modalText">Загрузка...</div>
            <button class="modal-btn" id="modalBtn" onclick="copyText()">📋 Скопировать</button>
            <button class="modal-close" onclick="closeModal()">Закрыть</button>
        </div>
    </div>
    
    <script>
        const API = "{api_base}";
        const tg = window.Telegram.WebApp;
        
        let user = null;
        let orders = [];
        let selectedCategories = [];
        
        const ALL_CATEGORIES = [
            {{id: 'python', name: '🐍 Python'}},
            {{id: 'design', name: '🎨 Дизайн'}},
            {{id: 'copywriting', name: '✍️ Тексты'}},
            {{id: 'marketing', name: '📈 Маркетинг'}}
        ];
        
        // Init
        tg.ready();
        tg.expand();
        
        // Load on start
        init();
        
        async function init() {{
            console.log('Init started');
            try {{
                await loadUser();
                await loadOrders();
                renderCategories();
                console.log('Init complete');
            }} catch(e) {{
                console.error('Init error:', e);
            }}
        }}
        
        async function loadUser() {{
            try {{
                const res = await fetch(API + '/api/user', {{
                    headers: {{'X-Telegram-Init-Data': tg.initData || ''}}
                }});
                user = await res.json();
                console.log('User loaded:', user);
                
                const badge = document.getElementById('userBadge');
                if (user.is_admin) {{
                    badge.textContent = '👑 ADMIN';
                    badge.className = 'user-badge admin';
                    badge.style.display = 'inline-block';
                }} else if (user.is_pro) {{
                    badge.textContent = '⭐ PRO';
                    badge.className = 'user-badge pro';
                    badge.style.display = 'inline-block';
                }} else if (user.has_subscription) {{
                    badge.textContent = '📦 Базовая';
                    badge.className = 'user-badge';
                    badge.style.display = 'inline-block';
                }} else {{
                    badge.style.display = 'none';
                }}
                
                selectedCategories = user.categories || [];
                
                if (user.predator_mode) {{
                    document.getElementById('predatorToggle').classList.add('active');
                }}
                
                renderSubscription();
                
            }} catch(e) {{
                console.error('Load user error:', e);
            }}
        }}
        
        async function loadOrders() {{
            const list = document.getElementById('ordersList');
            list.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
            
            try {{
                const res = await fetch(API + '/api/orders');
                orders = await res.json();
                console.log('Orders loaded:', orders.length);
                
                document.getElementById('ordersCount').textContent = orders.length;
                
                if (orders.length === 0) {{
                    list.innerHTML = '<div class="empty"><div class="empty-icon">🔍</div><div>Нажмите "Найти заказы"</div></div>';
                    return;
                }}
                
                list.innerHTML = orders.map(o => `
                    <div class="order-card ${{o.hot ? 'hot' : ''}}">
                        <div class="order-title">${{escapeHtml(o.title)}}</div>
                        <div class="order-meta">
                            <span>💰 ${{o.budget}}</span>
                            <span>⏰ ${{o.time_ago}}</span>
                            <span>📍 ${{o.source}}</span>
                        </div>
                        <div class="order-actions">
                            <button class="order-btn primary" onclick="generateResponse(${{o.id}})">✨ Отклик</button>
                            <button class="order-btn secondary" onclick="openOrder('${{escapeHtml(o.url)}}')">🔗 Открыть</button>
                        </div>
                    </div>
                `).join('');
                
            }} catch(e) {{
                console.error('Load orders error:', e);
                list.innerHTML = '<div class="empty"><div class="empty-icon">⚠️</div><div>Ошибка загрузки</div></div>';
            }}
        }}
        
        function escapeHtml(text) {{
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}
        
        async function turboParse() {{
            const btn = document.getElementById('parseBtn');
            btn.disabled = true;
            btn.innerHTML = '🔄 ИЩЕМ ЗАКАЗЫ...';
            
            try {{
                if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred('heavy');
                
                const res = await fetch(API + '/api/turbo-parse', {{method: 'POST'}});
                const data = await res.json();
                
                console.log('Parse result:', data);
                
                if (data.success) {{
                    showToast('✅ Найдено ' + data.new_orders + ' заказов!');
                    if (tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
                    await loadOrders();
                }} else {{
                    showToast('Ошибка поиска', true);
                }}
                
            }} catch(e) {{
                console.error('Parse error:', e);
                showToast('Ошибка: ' + e.message, true);
            }}
            
            btn.disabled = false;
            btn.innerHTML = '⚡ НАЙТИ ЗАКАЗЫ';
        }}
        
        async function generateResponse(orderId) {{
            if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
            
            document.getElementById('modal').classList.add('show');
            document.getElementById('modalTitle').textContent = '✨ AI-отклик';
            document.getElementById('modalText').textContent = 'Генерирую отклик...';
            
            try {{
                const res = await fetch(API + '/api/generate-response', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{order_id: orderId}})
                }});
                const data = await res.json();
                
                document.getElementById('modalText').textContent = data.response;
                if (tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
                
            }} catch(e) {{
                document.getElementById('modalText').textContent = 'Ошибка генерации';
            }}
        }}
        
        function copyText() {{
            const text = document.getElementById('modalText').textContent;
            navigator.clipboard.writeText(text).then(() => {{
                showToast('📋 Скопировано!');
                closeModal();
            }});
        }}
        
        function closeModal() {{
            document.getElementById('modal').classList.remove('show');
        }}
        
        function openOrder(url) {{
            if (url) tg.openLink(url);
        }}
        
        function showTab(tab) {{
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            
            document.getElementById('ordersTab').style.display = tab === 'orders' ? 'block' : 'none';
            document.getElementById('settingsTab').style.display = tab === 'settings' ? 'block' : 'none';
        }}
        
        function renderCategories() {{
            const list = document.getElementById('categoriesList');
            list.innerHTML = ALL_CATEGORIES.map(c => `
                <div class="settings-item" onclick="toggleCategory('${{c.id}}', this)" style="cursor:pointer;">
                    <span class="settings-label">${{c.name}}</span>
                    <span>${{selectedCategories.includes(c.id) ? '✅' : '⬜'}}</span>
                </div>
            `).join('');
        }}
        
        function toggleCategory(id, el) {{
            if (selectedCategories.includes(id)) {{
                selectedCategories = selectedCategories.filter(c => c !== id);
            }} else {{
                selectedCategories.push(id);
            }}
            renderCategories();
        }}
        
        function togglePredator() {{
            const toggle = document.getElementById('predatorToggle');
            toggle.classList.toggle('active');
        }}
        
        async function saveSettings() {{
            try {{
                await fetch(API + '/api/settings', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        categories: selectedCategories,
                        predator_mode: document.getElementById('predatorToggle').classList.contains('active'),
                        initData: tg.initData
                    }})
                }});
                showToast('✅ Сохранено!');
            }} catch(e) {{
                showToast('Ошибка сохранения', true);
            }}
        }}
        
        function renderSubscription() {{
            const info = document.getElementById('subscriptionInfo');
            
            if (user.is_admin) {{
                info.innerHTML = '<div class="settings-item" style="background:linear-gradient(135deg,#9b59b6,#8e44ad);"><span>👑 Админ - полный доступ</span></div>';
            }} else if (user.is_pro) {{
                info.innerHTML = '<div class="settings-item" style="background:linear-gradient(135deg,#f39c12,#e67e22);"><span>⭐ PRO - ' + user.subscription_days + ' дней</span></div>';
            }} else if (user.has_subscription) {{
                info.innerHTML = '<div class="settings-item" style="background:#00d26a;"><span>📦 Базовая - ' + user.subscription_days + ' дней</span></div>';
            }} else {{
                info.innerHTML = `
                    <div class="settings-item">
                        <span>Нет подписки</span>
                    </div>
                    ${{!user.trial_used ? '<button class="btn btn-success" onclick="startTrial()">🎁 Попробовать 3 дня бесплатно</button>' : ''}}
                `;
            }}
        }}
        
        async function startTrial() {{
            try {{
                const res = await fetch(API + '/api/trial', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{initData: tg.initData}})
                }});
                const data = await res.json();
                
                if (data.success) {{
                    showToast('🎉 ' + data.message);
                    await loadUser();
                }} else {{
                    showToast(data.message, true);
                }}
            }} catch(e) {{
                showToast('Ошибка', true);
            }}
        }}
        
        function showToast(msg, isError) {{
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.className = 'toast' + (isError ? ' error' : '');
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 3000);
        }}
    </script>
</body>
</html>'''


# ============ APP ============

def create_web_app():
    app = web.Application()
    
    app.router.add_get('/', handle_index)
    app.router.add_get('/health', handle_health)
    app.router.add_get('/webapp', handle_webapp)
    
    app.router.add_get('/api/user', api_user)
    app.router.add_get('/api/orders', api_orders)
    app.router.add_post('/api/turbo-parse', api_turbo_parse)
    app.router.add_post('/api/generate-response', api_generate_response)
    app.router.add_post('/api/trial', api_trial)
    app.router.add_post('/api/settings', api_settings)
    
    return app


# ============ MAIN ============

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
        logger.info(f"WebApp: https://{domain}/webapp")
        
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
