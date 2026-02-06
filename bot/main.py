# bot/main.py
import asyncio
import logging
import os
import json
import hashlib
import hmac
from urllib.parse import parse_qsl
from datetime import datetime, timezone
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import Config
from database.db import Database, init_db

from bot.handlers import start, categories, subscription, generate_response, profile, orders

from services.scam_detector import scam_detector
from services.price_calculator import price_calculator
from services.achievements import achievements
from services.market_analytics import market_analytics

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
    except:
        pass
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
        user = await Database.get_or_create_user(
            telegram_id=user_data.get('id'),
            username=user_data.get('username'),
            full_name=f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
        )
        await Database.update_user_activity(user_data.get('id'))
        return user
    return None


# ============ API HANDLERS ============

async def api_user(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'id': 0, 'is_new': True})
    
    days_left = 0
    if user.subscription_end:
        days_left = max(0, (user.subscription_end - datetime.utcnow()).days)
    
    ai_left = await Database.get_ai_responses_left(user.telegram_id)
    level_info = achievements.get_level_info(user.xp_points or 0)
    
    # Проверяем админа
    is_admin = Config.is_admin(user.telegram_id)
    
    # Админ имеет PRO доступ
    is_pro = is_admin or (user.subscription_type == 'pro' and user.has_active_subscription())
    has_subscription = is_admin or user.has_active_subscription()
    
    return web.json_response({
        'id': user.id,
        'telegram_id': user.telegram_id,
        'username': user.username or '',
        'full_name': user.full_name or 'Пользователь',
        'subscription_type': 'pro' if is_admin else (user.subscription_type or 'free'),
        'has_subscription': has_subscription,
        'is_pro': is_pro,
        'is_admin': is_admin,
        'subscription_days': 999 if is_admin else days_left,
        'ai_responses_left': -1 if is_admin else ai_left,  # Безлимит для админа
        'trial_used': user.trial_used,
        'categories': user.categories or [],
        'min_budget': user.min_budget or 0,
        'predator_mode': user.predator_mode or False,
        'xp': user.xp_points or 0,
        'level': level_info['current'],
        'level_progress': level_info['progress_percent'],
        'achievements': user.achievements or [],
        'streak_days': user.streak_days or 0,
        'total_earnings': user.total_earnings or 0,
        'orders_viewed': user.orders_viewed or 0,
        'responses_sent': user.responses_sent or 0,
        'deals_completed': user.deals_completed or 0,
        'referral_code': user.referral_code,
    })


async def api_orders(request: web.Request) -> web.Response:
    category = request.query.get('category', 'all')
    
    db_orders = await Database.get_orders(category if category != 'all' else None, limit=50)
    
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
            'hot': (order.budget_value or 0) >= 30000,
            'scam_score': order.scam_score or 0,
        })
    
    return web.json_response(orders_data)


async def api_turbo_parse(request: web.Request) -> web.Response:
    from parsers import ALL_PARSERS
    
    new_count = 0
    categories = ['design', 'python', 'copywriting', 'marketing']
    
    for parser in ALL_PARSERS:
        for category in categories:
            try:
                found = await parser.parse_orders(category)
                for order_data in found:
                    # Анализируем на скам
                    scam_result = await scam_detector.analyze(
                        order_data.get('title', ''),
                        order_data.get('description', ''),
                        order_data.get('budget', ''),
                        order_data.get('budget_value', 0)
                    )
                    order_data['scam_score'] = scam_result['risk_score']
                    order_data['scam_warnings'] = scam_result['warnings']
                    
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
    user = await get_user_from_request(request)
    
    try:
        body = await request.json()
        order_id = body.get('order_id')
        order = await Database.get_order_by_id(order_id)
        
        if not order:
            return web.json_response({'error': 'Order not found'}, status=404)
        
        # Проверяем лимит AI
        if user:
            can_use = await Database.use_ai_response(user.telegram_id)
            if not can_use:
                left = await Database.get_ai_responses_left(user.telegram_id)
                return web.json_response({
                    'error': 'limit_reached',
                    'message': f'Лимит AI-откликов исчерпан. Осталось: {left}',
                    'upgrade_needed': True
                }, status=403)
            
            # Добавляем XP
            xp_result = await Database.add_xp(user.telegram_id, 5)
        
        from services.gigachat import gigachat_service
        response = await gigachat_service.generate_response(order.title, order.description or '')
        
        return web.json_response({'response': response, 'xp_earned': 5})
    except Exception as e:
        logger.error(f"Generate error: {e}")
        return web.json_response({
            'response': "Здравствуйте!\n\nЗаинтересовал ваш проект. Имею опыт в данной области.\n\nГотов обсудить детали! 🚀"
        })


async def api_scam_check(request: web.Request) -> web.Response:
    """Проверка заказа на мошенничество"""
    user = await get_user_from_request(request)
    
    # Проверяем PRO или админ
    has_access = Config.is_admin(user.telegram_id) if user else False
    if not has_access and user:
        has_access = user.subscription_type == 'pro' and user.has_active_subscription()
    
    if not has_access:
        return web.json_response({'error': 'PRO subscription required', 'upgrade': True}, status=403)
    
    try:
        body = await request.json()
        order_id = body.get('order_id')
        
        order = await Database.get_order_by_id(order_id)
        if not order:
            return web.json_response({'error': 'Not found'}, status=404)
        
        result = await scam_detector.analyze(
            order.title,
            order.description or '',
            order.budget or '',
            order.budget_value or 0
        )
        
        # Сохраняем результат
        await Database.update_order_scam(order_id, result['risk_score'], result['warnings'])
        
        # XP за использование
        await Database.add_xp(user.telegram_id, 2)
        
        return web.json_response(result)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def api_scam_check(request: web.Request) -> web.Response:
    """Проверка заказа на мошенничество"""
    user = await get_user_from_request(request)
    
    # Проверяем PRO или админ
    has_access = Config.is_admin(user.telegram_id) if user else False
    if not has_access and user:
        has_access = user.subscription_type == 'pro' and user.has_active_subscription()
    
    if not has_access:
        return web.json_response({'error': 'PRO subscription required', 'upgrade': True}, status=403)
    
    try:
        body = await request.json()
        order_id = body.get('order_id')
        
        order = await Database.get_order_by_id(order_id)
        if not order:
            return web.json_response({'error': 'Not found'}, status=404)
        
        result = await price_calculator.calculate(
            order.title,
            order.description or '',
            order.category or 'python',
            order.budget_value or 0
        )
        
        return web.json_response(result)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def api_stats(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    
    market = await Database.get_market_stats()
    
    user_stats = {}
    if user:
        earnings = await Database.get_user_earnings_stats(user.id)
        user_stats = {
            'monthly_earnings': earnings['monthly'],
            'weekly_earnings': earnings['weekly'],
            'total_earnings': earnings['total'],
        }
    
    return web.json_response({
        'market': market,
        'user': user_stats
    })


async def api_achievements(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    
    unlocked = user.achievements if user else []
    all_achievements = achievements.get_all_achievements(unlocked)
    level_info = achievements.get_level_info(user.xp_points if user else 0)
    
    return web.json_response({
        'achievements': all_achievements,
        'level': level_info,
        'unlocked_count': len(unlocked),
        'total_count': len(all_achievements)
    })


# ============ DEALS API ============

async def api_deals_list(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    status = request.query.get('status')
    deals = await Database.get_user_deals(user.id, status)
    
    return web.json_response([{
        'id': d.id,
        'title': d.title,
        'client_name': d.client_name,
        'amount': d.amount,
        'paid_amount': d.paid_amount,
        'status': d.status,
        'deadline': d.deadline.isoformat() if d.deadline else None,
        'created_at': d.created_at.isoformat(),
    } for d in deals])


async def api_deals_create(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    has_access = Config.is_admin(user.telegram_id)
    if not has_access:
        has_access = user.subscription_type == 'pro' and user.has_active_subscription()
    
    if not has_access:
        return web.json_response({'error': 'PRO subscription required', 'upgrade': True}, status=403)
    
    try:
        body = await request.json()
        deal = await Database.create_deal(
            user_id=user.id,
            title=body.get('title', 'Новая сделка'),
            client_name=body.get('client_name'),
            client_contact=body.get('client_contact'),
            amount=body.get('amount', 0),
            status=body.get('status', 'lead'),
            notes=body.get('notes')
        )
        
        # Достижение за первую сделку
        if not 'first_deal' in (user.achievements or []):
            await Database.unlock_achievement(user.telegram_id, 'first_deal')
            await Database.add_xp(user.telegram_id, 50)
        
        return web.json_response({'success': True, 'deal_id': deal.id})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def api_deals_update(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    try:
        body = await request.json()
        deal_id = body.pop('deal_id', None)
        
        if not deal_id:
            return web.json_response({'error': 'deal_id required'}, status=400)
        
        deal = await Database.update_deal(deal_id, **body)
        
        # Если завершена - добавляем доход
        if body.get('status') == 'completed' and deal:
            if deal.amount:
                await Database.add_income(user.id, deal.amount, deal.id, deal.title)
            await Database.increment_stat(user.telegram_id, 'deals_completed')
            await Database.add_xp(user.telegram_id, 25)
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def api_income_add(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    try:
        body = await request.json()
        await Database.add_income(
            user_id=user.id,
            amount=body.get('amount', 0),
            description=body.get('description'),
            source=body.get('source', 'freelance')
        )
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def api_save_settings(request: web.Request) -> web.Response:
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    try:
        body = await request.json()
        
        allowed = ['categories', 'min_budget', 'predator_mode', 'predator_min_budget', 'is_active']
        settings = {k: v for k, v in body.items() if k in allowed}
        
        await Database.update_user_settings(user.telegram_id, **settings)
        
        # Достижение за режим хищник
        if body.get('predator_mode') and 'hunter' not in (user.achievements or []):
            await Database.unlock_achievement(user.telegram_id, 'hunter')
            await Database.add_xp(user.telegram_id, 20)
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


# ============ PAYMENT API ============

async def api_create_payment(request: web.Request) -> web.Response:
    """Создание платежа из Mini App"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    try:
        body = await request.json()
        subscription_type = body.get('type', 'basic')  # basic или pro
        
        from services.yukassa import yukassa_service
        
        payment_id, payment_url = await yukassa_service.create_payment(
            user.id, 
            subscription_type
        )
        
        # Сохраняем платёж
        price = Config.PRO_PRICE if subscription_type == "pro" else Config.BASIC_PRICE
        await Database.create_payment(user.id, payment_id, price, subscription_type)
        
        return web.json_response({
            'success': True,
            'payment_id': payment_id,
            'payment_url': payment_url,
            'amount': price,
            'type': subscription_type
        })
        
    except Exception as e:
        logger.error(f"Payment creation error: {e}")
        return web.json_response({'error': str(e)}, status=500)


async def api_check_payment(request: web.Request) -> web.Response:
    """Проверка статуса платежа"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    try:
        body = await request.json()
        payment_id = body.get('payment_id')
        
        if not payment_id:
            return web.json_response({'error': 'payment_id required'}, status=400)
        
        from services.yukassa import yukassa_service
        
        payment = await yukassa_service.check_payment(payment_id)
        
        if payment and payment.status == "succeeded":
            # Активируем подписку
            confirmed_user = await Database.confirm_payment(payment_id)
            if confirmed_user:
                return web.json_response({
                    'success': True,
                    'status': 'succeeded',
                    'message': 'Подписка активирована!'
                })
        
        return web.json_response({
            'success': False,
            'status': payment.status if payment else 'unknown',
            'message': 'Платёж ещё не получен'
        })
        
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def api_start_trial(request: web.Request) -> web.Response:
    """Активация пробного периода"""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({'error': 'Unauthorized'}, status=401)
    
    try:
        body = await request.json()
        sub_type = body.get('type', 'pro')  # Триал даём PRO
        
        success = await Database.start_user_trial(user.telegram_id, sub_type)
        
        if success:
            return web.json_response({
                'success': True,
                'message': f'Пробный период {Config.TRIAL_DAYS} дня активирован!'
            })
        else:
            return web.json_response({
                'success': False,
                'message': 'Пробный период уже использован'
            })
            
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


# ============ WEB HANDLERS ============

async def handle_index(request):
    return web.Response(text="Freelance Radar Bot is running! 🚀")

async def handle_health(request):
    return web.Response(text="OK")

async def handle_webapp(request):
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', request.host)
    api_base = f"https://{domain}" if domain else ""
    return web.Response(text=get_webapp_html(api_base), content_type='text/html', charset='utf-8')


# ============ MINI APP HTML ============

def get_webapp_html(api_base: str) -> str:
    # Большой HTML - в отдельном сообщении
    return WEBAPP_HTML.replace('{{API_BASE}}', api_base)


# ============ CREATE APP ============

def create_web_app():
    app = web.Application()
    
    # Pages
    app.router.add_get('/', handle_index)
    app.router.add_get('/health', handle_health)
    app.router.add_get('/webapp', handle_webapp)
    
    # User API
    app.router.add_get('/api/user', api_user)
    app.router.add_post('/api/settings', api_save_settings)
    
    # Orders API
    app.router.add_get('/api/orders', api_orders)
    app.router.add_post('/api/turbo-parse', api_turbo_parse)
    app.router.add_post('/api/generate-response', api_generate_response)
    app.router.add_post('/api/scam-check', api_scam_check)
    app.router.add_post('/api/price-calculate', api_price_calculate)
    
    # Stats & Achievements
    app.router.add_get('/api/stats', api_stats)
    app.router.add_get('/api/achievements', api_achievements)
    
    # CRM API
    app.router.add_get('/api/deals', api_deals_list)
    app.router.add_post('/api/deals', api_deals_create)
    app.router.add_put('/api/deals', api_deals_update)
    app.router.add_post('/api/income', api_income_add)
    
    # Payment API - ДОБАВЛЯЕМ
    app.router.add_post('/api/payment/create', api_create_payment)
    app.router.add_post('/api/payment/check', api_check_payment)
    app.router.add_post('/api/trial/start', api_start_trial)
    
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


# ============ WEBAPP HTML ============

WEBAPP_HTML = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Freelance Radar</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root { --bg:#0a0a0f; --bg2:#12121a; --card:rgba(255,255,255,0.05); --border:rgba(255,255,255,0.1);
                --text:#fff; --text2:#888; --accent:#6c5ce7; --accent2:#a29bfe; --success:#00d26a;
                --warning:#ffc107; --danger:#ff4757; --pro:#f39c12; }
        * { margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
        body { font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:var(--bg); color:var(--text); min-height:100vh; padding-bottom:70px; }
        
        .header { background:var(--bg2); padding:12px 16px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid var(--border); position:sticky; top:0; z-index:100; }
        .header-left { display:flex; align-items:center; gap:10px; }
        .logo { font-size:24px; }
        .title { font-size:16px; font-weight:700; background:linear-gradient(135deg,var(--accent),var(--accent2)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
        .pro-badge { background:linear-gradient(135deg,var(--pro),#e67e22); color:#fff; font-size:10px; font-weight:700; padding:3px 8px; border-radius:10px; }
        .level-badge { background:var(--card); border:1px solid var(--border); padding:3px 8px; border-radius:10px; font-size:11px; display:flex; align-items:center; gap:4px; }
        
        .tabs { display:flex; background:var(--bg2); border-bottom:1px solid var(--border); overflow-x:auto; }
        .tab { flex:1; min-width:60px; padding:10px 8px; text-align:center; font-size:11px; color:var(--text2); border-bottom:2px solid transparent; cursor:pointer; white-space:nowrap; }
        .tab.active { color:var(--accent); border-bottom-color:var(--accent); }
        .tab-icon { font-size:18px; display:block; margin-bottom:2px; }
        
        .page { display:none; padding:12px; }
        .page.active { display:block; }
        
        .stats-row { display:flex; gap:8px; margin-bottom:12px; overflow-x:auto; padding-bottom:4px; }
        .stat-mini { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:10px 12px; text-align:center; min-width:80px; flex-shrink:0; }
        .stat-mini-value { font-size:18px; font-weight:700; color:var(--accent); }
        .stat-mini-label { font-size:9px; color:var(--text2); margin-top:2px; }
        
        .btn { width:100%; padding:14px; border:none; border-radius:12px; font-size:14px; font-weight:600; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:8px; margin-bottom:12px; }
        .btn-primary { background:linear-gradient(135deg,var(--accent),var(--accent2)); color:#fff; }
        .btn-pro { background:linear-gradient(135deg,var(--pro),#e67e22); color:#fff; }
        .btn-secondary { background:var(--card); color:#fff; border:1px solid var(--border); }
        .btn-success { background:var(--success); color:#fff; }
        .btn-danger { background:var(--danger); color:#fff; }
        .btn:disabled { opacity:0.6; }
        .btn:active { transform:scale(0.98); }
        .btn-sm { padding:10px 16px; font-size:12px; width:auto; }
        
        .section { margin-bottom:16px; }
        .section-title { font-size:14px; font-weight:600; margin-bottom:10px; display:flex; align-items:center; gap:8px; }
        .badge { background:var(--accent); padding:2px 8px; border-radius:10px; font-size:10px; }
        .badge-pro { background:var(--pro); }
        
        .order-card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:12px; margin-bottom:8px; position:relative; }
        .order-card.hot::after { content:'🔥'; position:absolute; top:8px; right:8px; }
        .order-header { display:flex; gap:10px; margin-bottom:8px; }
        .order-source { width:36px; height:36px; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:14px; font-weight:600; flex-shrink:0; }
        .order-source.hh { background:#d63031; }
        .order-source.kwork { background:#00b894; }
        .order-source.fl { background:#0984e3; }
        .order-source.freelance { background:#6c5ce7; }
        .order-info { flex:1; min-width:0; }
        .order-title { font-size:13px; font-weight:500; line-height:1.3; margin-bottom:4px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
        .order-meta { display:flex; gap:8px; font-size:10px; color:var(--text2); flex-wrap:wrap; }
        .order-actions { display:flex; gap:6px; margin-top:8px; }
        .order-btn { flex:1; padding:8px; border:none; border-radius:8px; font-size:11px; font-weight:600; cursor:pointer; }
        .order-btn.primary { background:var(--accent); color:#fff; }
        .order-btn.secondary { background:var(--card); color:#fff; border:1px solid var(--border); }
        
        .scam-indicator { display:flex; align-items:center; gap:6px; padding:6px 10px; border-radius:8px; font-size:11px; margin:8px 0; }
        .scam-indicator.safe { background:rgba(0,210,106,0.15); color:var(--success); }
        .scam-indicator.warning { background:rgba(255,193,7,0.15); color:var(--warning); }
        .scam-indicator.danger { background:rgba(255,71,87,0.15); color:var(--danger); }
        
        .profile-header { text-align:center; padding:16px 0; }
        .avatar { width:70px; height:70px; border-radius:50%; background:linear-gradient(135deg,var(--accent),var(--accent2)); display:flex; align-items:center; justify-content:center; font-size:28px; margin:0 auto 10px; }
        .profile-name { font-size:18px; font-weight:600; }
        .profile-sub { font-size:12px; color:var(--text2); margin-top:2px; }
        
        .level-card { background:linear-gradient(135deg,var(--accent),var(--accent2)); border-radius:14px; padding:14px; margin:16px 0; }
        .level-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
        .level-name { font-size:14px; font-weight:600; display:flex; align-items:center; gap:6px; }
        .level-xp { font-size:12px; opacity:0.9; }
        .level-bar { height:6px; background:rgba(255,255,255,0.2); border-radius:3px; overflow:hidden; }
        .level-fill { height:100%; background:#fff; border-radius:3px; transition:width 0.3s; }
        
        .achievements-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }
        .achievement { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:10px; text-align:center; opacity:0.4; }
        .achievement.unlocked { opacity:1; border-color:var(--accent); }
        .achievement-icon { font-size:24px; margin-bottom:4px; }
        .achievement-name { font-size:9px; color:var(--text2); }
        
        .deal-card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:12px; margin-bottom:8px; }
        .deal-header { display:flex; justify-content:space-between; align-items:start; margin-bottom:6px; }
        .deal-title { font-size:13px; font-weight:500; }
        .deal-amount { font-size:14px; font-weight:700; color:var(--success); }
        .deal-meta { font-size:11px; color:var(--text2); }
        .deal-status { display:inline-block; padding:3px 8px; border-radius:6px; font-size:10px; font-weight:600; }
        .deal-status.lead { background:rgba(108,92,231,0.2); color:var(--accent); }
        .deal-status.in_progress { background:rgba(255,193,7,0.2); color:var(--warning); }
        .deal-status.completed { background:rgba(0,210,106,0.2); color:var(--success); }
        
        .setting-item { background:var(--card); border-radius:12px; padding:12px 14px; margin-bottom:8px; display:flex; align-items:center; justify-content:space-between; }
        .setting-info { display:flex; align-items:center; gap:10px; }
        .setting-icon { font-size:18px; }
        .setting-text h4 { font-size:13px; font-weight:500; }
        .setting-text p { font-size:10px; color:var(--text2); }
        
        .toggle { position:relative; width:44px; height:24px; }
        .toggle input { opacity:0; width:0; height:0; }
        .toggle-slider { position:absolute; cursor:pointer; top:0; left:0; right:0; bottom:0; background:var(--card); border:1px solid var(--border); transition:0.3s; border-radius:24px; }
        .toggle-slider::before { position:absolute; content:""; height:18px; width:18px; left:2px; bottom:2px; background:#fff; transition:0.3s; border-radius:50%; }
        .toggle input:checked+.toggle-slider { background:var(--accent); border-color:var(--accent); }
        .toggle input:checked+.toggle-slider::before { transform:translateX(20px); }
        
        .sub-card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:14px; margin-bottom:10px; }
        .sub-card.recommended { border-color:var(--pro); }
        .sub-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
        .sub-name { font-size:16px; font-weight:700; }
        .sub-price { font-size:20px; font-weight:700; }
        .sub-price span { font-size:12px; font-weight:400; color:var(--text2); }
        .sub-features { font-size:11px; color:var(--text2); }
        .sub-features li { margin-bottom:4px; list-style:none; }
        
        .analytics-card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px; margin-bottom:10px; }
        .analytics-title { font-size:12px; color:var(--text2); margin-bottom:6px; }
        .analytics-value { font-size:24px; font-weight:700; }
        .analytics-trend { font-size:11px; margin-top:4px; }
        .analytics-trend.up { color:var(--success); }
        .analytics-trend.down { color:var(--danger); }
        
        .empty { text-align:center; padding:30px; }
        .empty-icon { font-size:40px; margin-bottom:10px; }
        .empty-text { font-size:13px; color:var(--text2); }
        
        .loading { text-align:center; padding:30px; }
        .spinner { display:inline-block; width:24px; height:24px; border:3px solid var(--border); border-top-color:var(--accent); border-radius:50%; animation:spin 1s linear infinite; }
        @keyframes spin { to { transform:rotate(360deg); } }
        
        .toast { position:fixed; bottom:80px; left:50%; transform:translateX(-50%) translateY(100px); background:var(--success); color:#fff; padding:10px 20px; border-radius:10px; font-size:13px; opacity:0; transition:all 0.3s; z-index:1000; }
        .toast.error { background:var(--danger); }
        .toast.show { transform:translateX(-50%) translateY(0); opacity:1; }
        
        .modal { position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.85); display:none; align-items:flex-end; justify-content:center; z-index:2000; }
        .modal.show { display:flex; }
        .modal-content { background:var(--bg2); border-radius:20px 20px 0 0; padding:20px; width:100%; max-height:85vh; overflow-y:auto; animation:slideUp 0.3s; }
        @keyframes slideUp { from { transform:translateY(100%); } to { transform:translateY(0); } }
        .modal-handle { width:40px; height:4px; background:var(--border); border-radius:2px; margin:0 auto 16px; }
        .modal-title { font-size:18px; font-weight:600; margin-bottom:16px; }
        .modal-text { font-size:14px; line-height:1.5; white-space:pre-wrap; background:var(--card); padding:12px; border-radius:10px; margin-bottom:16px; }
        
        .input { width:100%; padding:12px 14px; background:var(--card); border:1px solid var(--border); border-radius:10px; color:var(--text); font-size:14px; margin-bottom:10px; }
        .input:focus { outline:none; border-color:var(--accent); }
        .input::placeholder { color:var(--text2); }
        
        .categories-grid { display:flex; flex-wrap:wrap; gap:8px; }
        .category-chip { padding:8px 14px; background:var(--card); border:1px solid var(--border); border-radius:20px; font-size:12px; cursor:pointer; }
        .category-chip.active { background:var(--accent); border-color:var(--accent); }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <span class="logo">📡</span>
            <span class="title">Freelance Radar</span>
        </div>
        <div style="display:flex;gap:6px;">
            <span class="level-badge" id="headerLevel">🌱 Ур.1</span>
            <span class="pro-badge" id="proBadge" style="display:none;">PRO</span>
        </div>
    </div>
    
    <div class="tabs">
        <div class="tab active" onclick="showPage('orders')"><span class="tab-icon">📋</span>Заказы</div>
        <div class="tab" onclick="showPage('deals')"><span class="tab-icon">💼</span>CRM</div>
        <div class="tab" onclick="showPage('analytics')"><span class="tab-icon">📊</span>Аналитика</div>
        <div class="tab" onclick="showPage('profile')"><span class="tab-icon">👤</span>Профиль</div>
    </div>
    
    <!-- ORDERS PAGE -->
    <div class="page active" id="page-orders">
        <div class="stats-row">
            <div class="stat-mini"><div class="stat-mini-value" id="statOrders">—</div><div class="stat-mini-label">Заказов</div></div>
            <div class="stat-mini"><div class="stat-mini-value" id="statAI">—</div><div class="stat-mini-label">AI осталось</div></div>
            <div class="stat-mini"><div class="stat-mini-value" id="statStreak">—</div><div class="stat-mini-label">🔥 Streak</div></div>
        </div>
        
        <button class="btn btn-primary" id="turboBtn" onclick="turboParse()">
            <span id="turboIcon">⚡</span><span id="turboText">НАЙТИ ЗАКАЗЫ</span>
        </button>
        
        <div class="section-title"><span>📋 Заказы</span><span class="badge" id="ordersCount">0</span></div>
        <div id="ordersList"><div class="loading"><div class="spinner"></div></div></div>
    </div>
    
    <!-- DEALS PAGE (CRM) -->
    <div class="page" id="page-deals">
        <div class="stats-row">
            <div class="stat-mini"><div class="stat-mini-value" id="dealActive">0</div><div class="stat-mini-label">Активных</div></div>
            <div class="stat-mini"><div class="stat-mini-value" id="dealDone">0</div><div class="stat-mini-label">Завершено</div></div>
            <div class="stat-mini"><div class="stat-mini-value" id="dealTotal">0₽</div><div class="stat-mini-label">Заработано</div></div>
        </div>
        
        <button class="btn btn-success" onclick="showAddDealModal()">➕ Добавить сделку</button>
        
        <div class="section-title">💼 Мои сделки</div>
        <div id="dealsList"><div class="empty"><div class="empty-icon">📋</div><div class="empty-text">Нет сделок</div></div></div>
    </div>
    
    <!-- ANALYTICS PAGE -->
    <div class="page" id="page-analytics">
        <div class="section-title">📊 Рынок за неделю</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px;">
            <div class="analytics-card">
                <div class="analytics-title">Заказов</div>
                <div class="analytics-value" id="marketOrders">—</div>
            </div>
            <div class="analytics-card">
                <div class="analytics-title">Средний бюджет</div>
                <div class="analytics-value" id="marketBudget">—</div>
            </div>
        </div>
        
        <div class="section-title">💰 Твой заработок</div>
        <div class="analytics-card">
            <div class="analytics-title">За месяц</div>
            <div class="analytics-value" id="userMonthly">0 ₽</div>
        </div>
        <div class="analytics-card">
            <div class="analytics-title">Всего</div>
            <div class="analytics-value" id="userTotal">0 ₽</div>
        </div>
        
        <div class="section-title">🏆 Уровень и достижения</div>
        <div class="level-card" id="levelCard"></div>
        <div class="achievements-grid" id="achievementsGrid"></div>
    </div>
    
    <!-- PROFILE PAGE -->
    <div class="page" id="page-profile">
        <div class="profile-header">
            <div class="avatar" id="userAvatar">👤</div>
            <div class="profile-name" id="userName">Загрузка...</div>
            <div class="profile-sub" id="userSub">Бесплатный аккаунт</div>
        </div>
        
        <div id="subBanner"></div>
        
        <div class="section-title">⚙️ Настройки</div>
        
        <div class="setting-item">
            <div class="setting-info"><div class="setting-icon">🦁</div><div class="setting-text"><h4>Режим Хищник</h4><p>Мгновенные пуши для заказов 50K+</p></div></div>
            <label class="toggle"><input type="checkbox" id="predatorToggle" onchange="saveSetting('predator_mode',this.checked)"><span class="toggle-slider"></span></label>
        </div>
        
        <div class="setting-item">
            <div class="setting-info"><div class="setting-icon">🔔</div><div class="setting-text"><h4>Уведомления</h4><p>Получать новые заказы</p></div></div>
            <label class="toggle"><input type="checkbox" id="notifyToggle" checked onchange="saveSetting('is_active',this.checked)"><span class="toggle-slider"></span></label>
        </div>
        
        <div class="section-title" style="margin-top:16px;">🎯 Категории</div>
        <div class="categories-grid" id="categoriesGrid"></div>
        <button class="btn btn-secondary" style="margin-top:12px;" onclick="saveCategories()">💾 Сохранить категории</button>
        
        <div class="section-title" style="margin-top:16px;">💳 Подписка</div>
        <div id="subscriptionCards"></div>
    </div>
    
    <div class="toast" id="toast"></div>
    
    <!-- Response Modal -->
    <div class="modal" id="modal" onclick="closeModal(event)">
        <div class="modal-content" onclick="event.stopPropagation()">
            <div class="modal-handle"></div>
            <div class="modal-title" id="modalTitle">✨ AI-отклик</div>
            <div class="modal-text" id="modalText">Загрузка...</div>
            <button class="btn btn-success" id="modalBtn" onclick="copyText()">📋 Скопировать</button>
        </div>
    </div>
    
    <!-- Scam Modal -->
    <div class="modal" id="scamModal" onclick="closeScamModal(event)">
        <div class="modal-content" onclick="event.stopPropagation()">
            <div class="modal-handle"></div>
            <div class="modal-title">🕵️ Проверка безопасности</div>
            <div id="scamResult"></div>
            <button class="btn btn-secondary" onclick="closeScamModal()">Закрыть</button>
        </div>
    </div>
    
    <!-- Price Modal -->
    <div class="modal" id="priceModal" onclick="closePriceModal(event)">
        <div class="modal-content" onclick="event.stopPropagation()">
            <div class="modal-handle"></div>
            <div class="modal-title">💰 Рекомендуемая цена</div>
            <div id="priceResult"></div>
            <button class="btn btn-secondary" onclick="closePriceModal()">Закрыть</button>
        </div>
    </div>
    
    <!-- Add Deal Modal -->
    <div class="modal" id="dealModal" onclick="closeDealModal(event)">
        <div class="modal-content" onclick="event.stopPropagation()">
            <div class="modal-handle"></div>
            <div class="modal-title">➕ Новая сделка</div>
            <input class="input" id="dealTitle" placeholder="Название проекта">
            <input class="input" id="dealClient" placeholder="Имя клиента">
            <input class="input" id="dealAmount" type="number" placeholder="Сумма (₽)">
            <button class="btn btn-success" onclick="createDeal()">Добавить</button>
        </div>
    </div>
    
<script>
    const API = '{{API_BASE}}';
    const tg = window.Telegram.WebApp;
    
    let user = null;
    let orders = [];
    let selectedCategories = [];
    let currentPaymentId = null;
    
    const CATEGORIES = [
        {id:'python',name:'🐍 Python'},{id:'design',name:'🎨 Дизайн'},
        {id:'copywriting',name:'✍️ Тексты'},{id:'marketing',name:'📈 Маркетинг'}
    ];
    
    tg.ready();
    tg.expand();
    
    document.addEventListener('DOMContentLoaded',async()=>{
        await loadUser();
        await loadOrders();
        await loadStats();
        await loadAchievements();
        renderCategories();
        haptic('light');
    });
    
    function haptic(t){if(tg.HapticFeedback){if(t==='success')tg.HapticFeedback.notificationOccurred('success');else if(t==='error')tg.HapticFeedback.notificationOccurred('error');else tg.HapticFeedback.impactOccurred(t);}}
    
    function showPage(name){
        document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
        document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
        document.getElementById('page-'+name).classList.add('active');
        event.currentTarget.classList.add('active');
        haptic('light');
        if(name==='deals')loadDeals();
        if(name==='analytics')loadStats();
    }
    
    async function loadUser(){
        try{
            const r=await fetch(API+'/api/user',{headers:{'X-Telegram-Init-Data':tg.initData}});
            user=await r.json();
            
            document.getElementById('userName').textContent=user.full_name||'Пользователь';
            document.getElementById('headerLevel').innerHTML=(user.level?.icon||'🌱')+' Ур.'+(user.level?.level||1);
            
            if(user.is_admin){
                document.getElementById('proBadge').style.display='block';
                document.getElementById('proBadge').textContent='ADMIN';
                document.getElementById('proBadge').style.background='linear-gradient(135deg,#9b59b6,#8e44ad)';
                document.getElementById('userSub').textContent='👑 Админ';
            }else if(user.is_pro){
                document.getElementById('proBadge').style.display='block';
                document.getElementById('userSub').textContent='PRO ⭐ ('+user.subscription_days+' дн.)';
            }else if(user.has_subscription){
                document.getElementById('userSub').textContent='Базовая ('+user.subscription_days+' дн.)';
            }else{
                document.getElementById('userSub').textContent='Бесплатный аккаунт';
            }
            
            document.getElementById('statAI').textContent=user.ai_responses_left===-1?'∞':user.ai_responses_left;
            document.getElementById('statStreak').textContent=user.streak_days||0;
            
            document.getElementById('predatorToggle').checked=user.predator_mode||false;
            selectedCategories=user.categories||[];
            
            renderSubBanner();
            renderSubscriptions();
            
        }catch(e){console.error(e);}
    }
    
    function renderSubBanner(){
        const banner=document.getElementById('subBanner');
        if(user.is_admin){
            banner.innerHTML=`<div class="setting-item" style="background:linear-gradient(135deg,#9b59b6,#8e44ad);"><div class="setting-info"><div class="setting-icon">👑</div><div class="setting-text"><h4 style="color:white;">Режим администратора</h4><p style="color:rgba(255,255,255,0.8);">Полный доступ ко всем функциям</p></div></div></div>`;
        }else if(user.is_pro){
            banner.innerHTML=`<div class="setting-item" style="background:linear-gradient(135deg,var(--pro),#e67e22);"><div class="setting-info"><div class="setting-icon">⭐</div><div class="setting-text"><h4 style="color:white;">PRO подписка</h4><p style="color:rgba(255,255,255,0.8);">Осталось ${user.subscription_days} дней</p></div></div></div>`;
        }else if(user.has_subscription){
            banner.innerHTML=`<div class="setting-item" style="background:linear-gradient(135deg,var(--success),#00b894);"><div class="setting-info"><div class="setting-icon">📦</div><div class="setting-text"><h4 style="color:white;">Базовая подписка</h4><p style="color:rgba(255,255,255,0.8);">Осталось ${user.subscription_days} дней</p></div></div></div>`;
        }else{
            banner.innerHTML=`<div class="sub-card" style="background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;"><h3 style="font-size:15px;margin-bottom:8px;">🚀 Получи полный доступ</h3><p style="font-size:12px;opacity:0.9;margin-bottom:12px;">AI-отклики, детектор кидал, CRM и многое другое</p>${!user.trial_used?'<button class="btn" style="background:white;color:var(--accent);" onclick="startTrial()">🎁 3 дня бесплатно</button>':''}</div>`;
        }
    }
    
    function renderSubscriptions(){
        const trialBtn=!user?.trial_used?`<button class="btn btn-success" style="margin-bottom:12px;" onclick="startTrial()">🎁 Попробовать PRO 3 дня бесплатно</button>`:'';
        const proCard=`<div class="sub-card recommended"><div class="sub-header"><div class="sub-name">PRO ⭐</div><div class="sub-price">1490₽<span>/мес</span></div></div><ul class="sub-features"><li>✅ Безлимит AI-откликов</li><li>✅ Детектор мошенников</li><li>✅ Калькулятор цен</li><li>✅ CRM для сделок</li><li>✅ Аналитика рынка</li><li>✅ Режим Хищник</li></ul><button class="btn btn-pro" onclick="subscribe('pro')">💎 Оформить PRO</button></div>`;
        const basicCard=`<div class="sub-card"><div class="sub-header"><div class="sub-name">Базовая</div><div class="sub-price">690₽<span>/мес</span></div></div><ul class="sub-features"><li>✅ Мониторинг всех бирж</li><li>✅ 50 AI-откликов/мес</li><li>✅ Уведомления</li><li>❌ Детектор мошенников</li><li>❌ CRM</li></ul><button class="btn btn-primary" onclick="subscribe('basic')">📦 Оформить</button></div>`;
        document.getElementById('subscriptionCards').innerHTML=trialBtn+proCard+basicCard;
    }
    
    async function subscribe(type){
        haptic('medium');
        showModal('💳 Создаём платёж...','Подождите...');
        document.getElementById('modalBtn').style.display='none';
        
        try{
            const r=await fetch(API+'/api/payment/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:type,initData:tg.initData})});
            const d=await r.json();
            
            if(d.success&&d.payment_url){
                currentPaymentId=d.payment_id;
                const typeName=type==='pro'?'PRO ⭐':'Базовая';
                showModal('💳 Оплата '+typeName,`Сумма: ${d.amount}₽\n\nНажмите кнопку для перехода к оплате:`);
                document.getElementById('modalBtn').style.display='block';
                document.getElementById('modalBtn').textContent='💳 Перейти к оплате';
                document.getElementById('modalBtn').onclick=()=>{
                    tg.openLink(d.payment_url);
                    setTimeout(()=>{
                        showModal('💳 Оплата','После оплаты нажмите кнопку проверки:');
                        document.getElementById('modalBtn').textContent='✅ Проверить оплату';
                        document.getElementById('modalBtn').onclick=()=>checkPaymentStatus(d.payment_id);
                    },1000);
                };
            }else{
                throw new Error(d.error||'Error');
            }
        }catch(e){
            showModal('❌ Ошибка','Не удалось создать платёж.\n\nПопробуйте через бота @FreelanceRadarBot');
            document.getElementById('modalBtn').style.display='block';
            document.getElementById('modalBtn').textContent='Закрыть';
            document.getElementById('modalBtn').onclick=closeModal;
        }
    }
    
    async function checkPaymentStatus(paymentId){
        haptic('medium');
        document.getElementById('modalText').textContent='Проверяем оплату...';
        
        try{
            const r=await fetch(API+'/api/payment/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({payment_id:paymentId,initData:tg.initData})});
            const d=await r.json();
            
            if(d.success&&d.status==='succeeded'){
                showModal('🎉 Успешно!','Подписка активирована!\n\nТеперь вам доступны все функции.');
                document.getElementById('modalBtn').textContent='🚀 Отлично!';
                document.getElementById('modalBtn').onclick=()=>{closeModal();loadUser();};
                haptic('success');
            }else{
                document.getElementById('modalText').textContent='Платёж ещё обрабатывается.\n\nПопробуйте через минуту.';
                haptic('error');
            }
        }catch(e){
            document.getElementById('modalText').textContent='Ошибка проверки.';
        }
    }
    
    async function startTrial(){
        if(user?.trial_used){toast('Пробный период уже использован',true);return;}
        haptic('medium');
        try{
            const r=await fetch(API+'/api/trial/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'pro',initData:tg.initData})});
            const d=await r.json();
            if(d.success){toast('🎉 '+d.message);haptic('success');await loadUser();}
            else{toast(d.message||'Ошибка',true);}
        }catch(e){toast('Ошибка',true);}
    }
    
    function showModal(title,text){
        document.getElementById('modalTitle').textContent=title;
        document.getElementById('modalText').textContent=text;
        document.getElementById('modal').classList.add('show');
    }
    
    async function loadOrders(){
        const list=document.getElementById('ordersList');
        list.innerHTML='<div class="loading"><div class="spinner"></div></div>';
        try{
            const r=await fetch(API+'/api/orders');
            orders=await r.json();
            document.getElementById('ordersCount').textContent=orders.length;
            document.getElementById('statOrders').textContent=orders.length;
            if(!orders.length){list.innerHTML='<div class="empty"><div class="empty-icon">🔍</div><div class="empty-text">Нажмите "Найти заказы"</div></div>';return;}
            list.innerHTML=orders.map(o=>createOrderCard(o)).join('');
        }catch(e){list.innerHTML='<div class="empty">Ошибка загрузки</div>';}
    }
    
    function createOrderCard(o){
        const srcMap={hh:'🔴',kwork:'🟢','fl.ru':'🔵','freelance.ru':'🟣'};
        const srcClass=o.source.replace('.','').replace('_','');
        const scamClass=o.scam_score>=60?'danger':o.scam_score>=30?'warning':'safe';
        const scamText=o.scam_score>=60?'⚠️ Риск':o.scam_score>=30?'Проверить':'✅ Ок';
        return `<div class="order-card ${o.hot?'hot':''}"><div class="order-header"><div class="order-source ${srcClass}">${srcMap[o.source]||'📋'}</div><div class="order-info"><div class="order-title">${esc(o.title)}</div><div class="order-meta"><span>💰${o.budget}</span><span>⏰${o.time_ago}</span><span>${o.source}</span></div></div></div><div class="order-actions"><button class="order-btn primary" onclick="generateResponse(${o.id})">✨ Отклик</button><button class="order-btn secondary" onclick="checkScam(${o.id})">🕵️</button><button class="order-btn secondary" onclick="calcPrice(${o.id})">💰</button><button class="order-btn secondary" onclick="openUrl('${esc(o.url)}')">🔗</button></div></div>`;
    }
    
    function esc(s){if(!s)return'';const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
    
    async function turboParse(){
        const btn=document.getElementById('turboBtn');
        btn.disabled=true;
        document.getElementById('turboText').textContent='ИЩЕМ...';
        haptic('heavy');
        try{
            const r=await fetch(API+'/api/turbo-parse',{method:'POST'});
            const d=await r.json();
            toast('✅ Найдено '+d.new_orders+' заказов!');
            haptic('success');
            await loadOrders();
        }catch(e){toast('Ошибка',true);haptic('error');}
        document.getElementById('turboText').textContent='НАЙТИ ЗАКАЗЫ';
        btn.disabled=false;
    }
    
    async function generateResponse(id){
        haptic('medium');
        showModal('✨ AI-отклик','Генерирую отклик...');
        document.getElementById('modalBtn').style.display='none';
        try{
            const r=await fetch(API+'/api/generate-response',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:id,initData:tg.initData})});
            const d=await r.json();
            if(d.error==='limit_reached'){
                showModal('⚠️ Лимит исчерпан',d.message+'\n\nОформите PRO для безлимита!');
                document.getElementById('modalBtn').style.display='block';
                document.getElementById('modalBtn').textContent='💎 Оформить PRO';
                document.getElementById('modalBtn').onclick=()=>{closeModal();showPage('profile');};
            }else{
                document.getElementById('modalText').textContent=d.response;
                document.getElementById('modalBtn').style.display='block';
                document.getElementById('modalBtn').textContent='📋 Скопировать';
                document.getElementById('modalBtn').onclick=copyModalText;
                if(d.xp_earned)toast('+'+d.xp_earned+' XP');
            }
            haptic('success');
        }catch(e){document.getElementById('modalText').textContent='Ошибка';}
    }
    
    async function checkScam(id){
        if(!user?.is_pro&&!user?.is_admin){toast('Только для PRO',true);showPage('profile');return;}
        haptic('medium');
        document.getElementById('scamModal').classList.add('show');
        document.getElementById('scamResult').innerHTML='<div class="loading"><div class="spinner"></div></div>';
        try{
            const r=await fetch(API+'/api/scam-check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:id,initData:tg.initData})});
            const d=await r.json();
            if(d.error){document.getElementById('scamResult').innerHTML=`<p>${d.error}</p>`;return;}
            document.getElementById('scamResult').innerHTML=`<div class="scam-indicator ${d.risk_level}" style="justify-content:center;font-size:14px;">${d.risk_emoji} ${d.risk_text} (${d.risk_score}%)</div><p style="margin:12px 0;font-size:13px;">${d.recommendation}</p>${d.warnings?.length?'<p style="font-size:12px;color:var(--danger);">⚠️ '+d.warnings.join('<br>⚠️ ')+'</p>':''}${d.green_signs?.length?'<p style="font-size:12px;color:var(--success);margin-top:8px;">✅ '+d.green_signs.join('<br>✅ ')+'</p>':''}`;
        }catch(e){document.getElementById('scamResult').textContent='Ошибка';}
    }
    
    async function calcPrice(id){
        if(!user?.is_pro&&!user?.is_admin){toast('Только для PRO',true);showPage('profile');return;}
        haptic('medium');
        document.getElementById('priceModal').classList.add('show');
        document.getElementById('priceResult').innerHTML='<div class="loading"><div class="spinner"></div></div>';
        try{
            const r=await fetch(API+'/api/price-calculate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:id,initData:tg.initData})});
            const d=await r.json();
            if(d.error){document.getElementById('priceResult').innerHTML=`<p>${d.error}</p>`;return;}
            document.getElementById('priceResult').innerHTML=`<div class="analytics-card"><div class="analytics-title">Рекомендуемая цена</div><div class="analytics-value">${d.sweet_spot}</div></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0;"><div class="analytics-card"><div class="analytics-title">Минимум</div><div class="analytics-value" style="font-size:16px;">${d.recommended_min?.toLocaleString()}₽</div></div><div class="analytics-card"><div class="analytics-title">Максимум</div><div class="analytics-value" style="font-size:16px;">${d.recommended_max?.toLocaleString()}₽</div></div></div><p style="font-size:12px;color:var(--text2);">Сложность: ${d.complexity_text}</p><p style="font-size:13px;margin-top:10px;">${d.tip}</p>`;
        }catch(e){document.getElementById('priceResult').textContent='Ошибка';}
    }
    
    async function loadStats(){
        try{
            const r=await fetch(API+'/api/stats',{headers:{'X-Telegram-Init-Data':tg.initData}});
            const d=await r.json();
            document.getElementById('marketOrders').textContent=d.market?.weekly_orders||0;
            document.getElementById('marketBudget').textContent=(d.market?.avg_budget||0).toLocaleString()+'₽';
            document.getElementById('userMonthly').textContent=(d.user?.monthly_earnings||0).toLocaleString()+' ₽';
            document.getElementById('userTotal').textContent=(d.user?.total_earnings||0).toLocaleString()+' ₽';
        }catch(e){}
    }
    
    async function loadAchievements(){
        try{
            const r=await fetch(API+'/api/achievements',{headers:{'X-Telegram-Init-Data':tg.initData}});
            const d=await r.json();
            document.getElementById('levelCard').innerHTML=`<div class="level-header"><div class="level-name">${d.level.current.icon} ${d.level.current.name}</div><div class="level-xp">${d.level.xp} XP</div></div><div class="level-bar"><div class="level-fill" style="width:${d.level.progress_percent}%"></div></div>${d.level.next?`<div style="font-size:10px;margin-top:6px;opacity:0.8;">До ${d.level.next.name}: ${d.level.needed_xp-d.level.progress_xp} XP</div>`:''}`;
            document.getElementById('achievementsGrid').innerHTML=d.achievements.slice(0,8).map(a=>`<div class="achievement ${a.unlocked?'unlocked':''}"><div class="achievement-icon">${a.icon}</div><div class="achievement-name">${a.name}</div></div>`).join('');
        }catch(e){}
    }
    
    async function loadDeals(){
        if(!user?.is_pro&&!user?.is_admin){document.getElementById('dealsList').innerHTML='<div class="empty"><div class="empty-icon">🔒</div><div class="empty-text">CRM доступна в PRO</div><button class="btn btn-pro btn-sm" style="margin-top:12px;" onclick="showPage(\'profile\')">Оформить PRO</button></div>';return;}
        try{
            const r=await fetch(API+'/api/deals',{headers:{'X-Telegram-Init-Data':tg.initData}});
            const deals=await r.json();
            const active=deals.filter(d=>d.status!=='completed'&&d.status!=='cancelled').length;
            const done=deals.filter(d=>d.status==='completed').length;
            const total=deals.filter(d=>d.status==='completed').reduce((s,d)=>s+d.amount,0);
            document.getElementById('dealActive').textContent=active;
            document.getElementById('dealDone').textContent=done;
            document.getElementById('dealTotal').textContent=total.toLocaleString()+'₽';
            if(!deals.length){document.getElementById('dealsList').innerHTML='<div class="empty"><div class="empty-icon">📋</div><div class="empty-text">Добавь первую сделку</div></div>';return;}
            document.getElementById('dealsList').innerHTML=deals.map(d=>`<div class="deal-card"><div class="deal-header"><div><div class="deal-title">${esc(d.title)}</div><div class="deal-meta">${d.client_name||'—'}</div></div><div class="deal-amount">${d.amount?.toLocaleString()||0}₽</div></div><span class="deal-status ${d.status}">${{lead:'Лид',negotiation:'Переговоры',in_progress:'В работе',review:'На проверке',completed:'Завершён',cancelled:'Отменён'}[d.status]||d.status}</span></div>`).join('');
        }catch(e){}
    }
    
    function showAddDealModal(){if(!user?.is_pro&&!user?.is_admin){toast('Только для PRO',true);return;}document.getElementById('dealModal').classList.add('show');}
    function closeDealModal(e){if(!e||e.target.id==='dealModal')document.getElementById('dealModal').classList.remove('show');}
    
    async function createDeal(){
        const title=document.getElementById('dealTitle').value;
        const client=document.getElementById('dealClient').value;
        const amount=parseInt(document.getElementById('dealAmount').value)||0;
        if(!title){toast('Введи название',true);return;}
        try{await fetch(API+'/api/deals',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,client_name:client,amount,initData:tg.initData})});toast('✅ Сделка добавлена!');closeDealModal();loadDeals();}catch(e){toast('Ошибка',true);}
    }
    
    function renderCategories(){document.getElementById('categoriesGrid').innerHTML=CATEGORIES.map(c=>`<div class="category-chip ${selectedCategories.includes(c.id)?'active':''}" onclick="toggleCat('${c.id}',this)">${c.name}</div>`).join('');}
    function toggleCat(id,el){haptic('light');if(selectedCategories.includes(id)){selectedCategories=selectedCategories.filter(c=>c!==id);el.classList.remove('active');}else{selectedCategories.push(id);el.classList.add('active');}}
    async function saveCategories(){try{await fetch(API+'/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({categories:selectedCategories,initData:tg.initData})});toast('✅ Сохранено!');haptic('success');}catch(e){toast('Ошибка',true);}}
    async function saveSetting(key,val){try{await fetch(API+'/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:val,initData:tg.initData})});toast('✅ Сохранено!');haptic('success');}catch(e){toast('Ошибка',true);}}
    
    function copyModalText(){navigator.clipboard.writeText(document.getElementById('modalText').textContent).then(()=>{toast('📋 Скопировано!');haptic('success');closeModal();});}
    function closeModal(e){if(!e||e.target.id==='modal'){document.getElementById('modal').classList.remove('show');document.getElementById('modalBtn').style.display='block';document.getElementById('modalBtn').textContent='📋 Скопировать';document.getElementById('modalBtn').onclick=copyModalText;}}
    function closeScamModal(e){if(!e||e.target.id==='scamModal')document.getElementById('scamModal').classList.remove('show');}
    function closePriceModal(e){if(!e||e.target.id==='priceModal')document.getElementById('priceModal').classList.remove('show');}
    function openUrl(u){haptic('light');tg.openLink(u);}
    function toast(m,err=false){const t=document.getElementById('toast');t.textContent=m;t.className='toast'+(err?' error':'');t.classList.add('show');setTimeout(()=>t.classList.remove('show'),3000);}
</script>
</body>
</html>'''


if __name__ == "__main__":
    asyncio.run(main())


