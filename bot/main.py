# bot/main.py
import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import Config
from database.db import init_db

from bot.handlers import start, categories, subscription, generate_response, profile, orders

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ===== WEBAPP HTML =====
WEBAPP_HTML = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Freelance Radar</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 100%);
            color: #fff; min-height: 100vh; padding: 20px;
        }
        .container { max-width: 400px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .logo { font-size: 48px; margin-bottom: 10px; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.1); } }
        h1 { font-size: 24px; background: linear-gradient(135deg, #6c5ce7, #a29bfe);
             -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { color: #888; font-size: 14px; margin-top: 5px; }
        
        .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 20px; }
        .stat-card { background: rgba(255,255,255,0.05); border-radius: 16px; padding: 16px; 
                     text-align: center; border: 1px solid rgba(255,255,255,0.1); }
        .stat-value { font-size: 24px; font-weight: 700; color: #6c5ce7; }
        .stat-label { font-size: 11px; color: #888; text-transform: uppercase; }
        
        .turbo-btn {
            width: 100%; padding: 18px; background: linear-gradient(135deg, #6c5ce7, #a29bfe);
            border: none; border-radius: 16px; color: white; font-size: 16px; font-weight: 600;
            cursor: pointer; margin-bottom: 20px; display: flex; align-items: center;
            justify-content: center; gap: 10px; position: relative; overflow: hidden;
        }
        .turbo-btn::before {
            content: ''; position: absolute; top: 0; left: -100%; width: 100%; height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            animation: shimmer 2s infinite;
        }
        @keyframes shimmer { 100% { left: 100%; } }
        .turbo-btn:active { transform: scale(0.98); }
        .turbo-btn:disabled { opacity: 0.7; }
        
        .predator-card {
            background: linear-gradient(135deg, rgba(255, 71, 87, 0.1), rgba(255, 165, 0, 0.1));
            border: 1px solid rgba(255, 71, 87, 0.3); border-radius: 16px; padding: 16px;
            display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;
        }
        .predator-info { display: flex; align-items: center; gap: 12px; }
        .predator-icon { font-size: 32px; }
        .predator-text h3 { font-size: 14px; font-weight: 600; }
        .predator-text p { font-size: 12px; color: #888; }
        
        .toggle { position: relative; width: 52px; height: 28px; }
        .toggle input { opacity: 0; width: 0; height: 0; }
        .toggle-slider {
            position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(255, 255, 255, 0.1); transition: 0.3s; border-radius: 28px;
        }
        .toggle-slider::before {
            position: absolute; content: ""; height: 22px; width: 22px; left: 3px; bottom: 3px;
            background: white; transition: 0.3s; border-radius: 50%;
        }
        .toggle input:checked + .toggle-slider { background: linear-gradient(135deg, #ff4757, #ff6b81); }
        .toggle input:checked + .toggle-slider::before { transform: translateX(24px); }
        
        .section-title { font-size: 16px; font-weight: 600; margin-bottom: 12px; display: flex;
                         align-items: center; gap: 8px; }
        .badge { background: #6c5ce7; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
        
        .order-card {
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px; padding: 16px; margin-bottom: 12px; position: relative;
        }
        .order-card.hot::before {
            content: '🔥 HOT'; position: absolute; top: 12px; right: 12px;
            background: linear-gradient(135deg, #ff4757, #ff6b81); color: white;
            font-size: 10px; font-weight: 700; padding: 4px 8px; border-radius: 8px;
        }
        .order-header { display: flex; gap: 12px; margin-bottom: 12px; }
        .order-source {
            width: 44px; height: 44px; border-radius: 12px; display: flex;
            align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0;
        }
        .order-source.kwork { background: linear-gradient(135deg, #00d26a, #00b894); }
        .order-source.fl { background: linear-gradient(135deg, #0984e3, #74b9ff); }
        .order-source.habr { background: linear-gradient(135deg, #6c5ce7, #a29bfe); }
        .order-source.hh { background: linear-gradient(135deg, #d63031, #ff7675); }
        .order-info { flex: 1; min-width: 0; }
        .order-title { font-size: 14px; font-weight: 600; line-height: 1.3; margin-bottom: 6px;
                       display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .order-meta { display: flex; gap: 12px; font-size: 12px; color: #888; }
        
        .ai-score { display: flex; align-items: center; gap: 8px; margin: 12px 0; padding: 10px;
                    background: rgba(108, 92, 231, 0.1); border-radius: 12px; }
        .score-bar { flex: 1; height: 6px; background: rgba(255, 255, 255, 0.1); border-radius: 3px; overflow: hidden; }
        .score-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, #00d26a, #00b894); }
        .score-value { font-size: 14px; font-weight: 700; color: #00d26a; min-width: 40px; text-align: right; }
        
        .order-actions { display: flex; gap: 10px; }
        .order-btn {
            flex: 1; padding: 12px; border: none; border-radius: 12px;
            font-size: 13px; font-weight: 600; cursor: pointer; display: flex;
            align-items: center; justify-content: center; gap: 6px;
        }
        .order-btn.primary { background: linear-gradient(135deg, #6c5ce7, #a29bfe); color: white; }
        .order-btn.secondary { background: rgba(255, 255, 255, 0.1); color: white; }
        .order-btn:active { transform: scale(0.95); }
        
        .toast {
            position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%) translateY(100px);
            background: #00d26a; color: white; padding: 12px 24px; border-radius: 12px;
            font-size: 14px; font-weight: 500; opacity: 0; transition: all 0.3s; z-index: 1000;
        }
        .toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }
        
        .empty-state { text-align: center; padding: 40px; }
        .empty-icon { font-size: 64px; margin-bottom: 16px; }
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
            <span>⚡</span>
            <span id="turboText">ТУРБО-ПАРСИНГ</span>
        </button>
        
        <div class="predator-card">
            <div class="predator-info">
                <div class="predator-icon">🦁</div>
                <div class="predator-text">
                    <h3>Режим «Хищник»</h3>
                    <p>Пуши для заказов от 50K₽</p>
                </div>
            </div>
            <label class="toggle">
                <input type="checkbox" id="predatorMode" onchange="togglePredator()">
                <span class="toggle-slider"></span>
            </label>
        </div>
        
        <div class="section-title">
            <span>🔥 Горячие заказы</span>
            <span class="badge" id="hotCount">0</span>
        </div>
        
        <div id="ordersList"></div>
    </div>
    
    <div class="toast" id="toast"></div>
    
    <script>
        const tg = window.Telegram.WebApp;
        tg.ready();
        tg.expand();
        
        document.addEventListener('DOMContentLoaded', () => {
            loadData();
            tg.HapticFeedback.impactOccurred('light');
        });
        
        function loadData() {
            document.getElementById('ordersCount').textContent = '47';
            document.getElementById('responsesCount').textContent = '12';
            document.getElementById('earnings').textContent = '89K';
            document.getElementById('hotCount').textContent = '3';
            
            const orders = [
                { title: 'Разработка Telegram бота для интернет-магазина', budget: '45 000 ₽', source: 'kwork', hot: true, score: 92 },
                { title: 'Дизайн лендинга для IT-стартапа', budget: '30 000 ₽', source: 'fl', hot: false, score: 78 },
                { title: 'Парсер данных на Python + анализ', budget: '60 000 ₽', source: 'habr', hot: true, score: 95 },
            ];
            
            document.getElementById('ordersList').innerHTML = orders.map(o => `
                <div class="order-card ${o.hot ? 'hot' : ''}">
                    <div class="order-header">
                        <div class="order-source ${o.source}">${getEmoji(o.source)}</div>
                        <div class="order-info">
                            <div class="order-title">${o.title}</div>
                            <div class="order-meta">
                                <span>💰 ${o.budget}</span>
                                <span>⏰ 5 мин назад</span>
                            </div>
                        </div>
                    </div>
                    <div class="ai-score">
                        <span>🎯 AI Match</span>
                        <div class="score-bar"><div class="score-fill" style="width: ${o.score}%"></div></div>
                        <span class="score-value">${o.score}%</span>
                    </div>
                    <div class="order-actions">
                        <button class="order-btn primary" onclick="generateResponse()">✨ AI-отклик</button>
                        <button class="order-btn secondary" onclick="openOrder()">🔗 Открыть</button>
                    </div>
                </div>
            `).join('');
        }
        
        function getEmoji(source) {
            return { kwork: '🟢', fl: '🔵', habr: '🟣', hh: '🔴' }[source] || '📋';
        }
        
        function turboParse() {
            const btn = document.getElementById('turboBtn');
            const text = document.getElementById('turboText');
            btn.disabled = true;
            text.textContent = 'СКАНИРУЮ БИРЖИ...';
            tg.HapticFeedback.impactOccurred('heavy');
            
            // Отправляем данные боту
            tg.sendData(JSON.stringify({ action: 'turbo_parse' }));
            
            setTimeout(() => {
                text.textContent = 'НАЙДЕНО 7 ЗАКАЗОВ!';
                showToast('✅ Найдено 7 новых заказов!');
                tg.HapticFeedback.notificationOccurred('success');
                setTimeout(() => { text.textContent = 'ТУРБО-ПАРСИНГ'; btn.disabled = false; }, 2000);
            }, 2000);
        }
        
        function togglePredator() {
            const enabled = document.getElementById('predatorMode').checked;
            tg.HapticFeedback.impactOccurred(enabled ? 'heavy' : 'light');
            showToast(enabled ? '🦁 Режим Хищник активирован!' : 'Режим Хищник отключён');
            tg.sendData(JSON.stringify({ action: 'predator_mode', enabled }));
        }
        
        function generateResponse() {
            tg.HapticFeedback.impactOccurred('medium');
            tg.showAlert('✨ Генерирую AI-отклик...\\n\\nЗдравствуйте! Заинтересовал ваш проект. Имею опыт в данной области — успешно завершил 50+ похожих задач. Готов обсудить детали!');
        }
        
        function openOrder() {
            tg.HapticFeedback.impactOccurred('light');
            tg.openLink('https://kwork.ru');
        }
        
        function showToast(msg) {
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 3000);
        }
    </script>
</body>
</html>'''


# ===== WEB HANDLERS =====
async def handle_health(request):
    return web.Response(text="OK")

async def handle_webapp(request):
    return web.Response(text=WEBAPP_HTML, content_type='text/html', charset='utf-8')

async def handle_api_orders(request):
    return web.json_response([
        {'id': 1, 'title': 'Test order', 'budget': '10000', 'source': 'kwork'}
    ])


# ===== MAIN =====
async def main():
    # 1. Init database
    await init_db()
    logger.info("Database initialized")
    
    # 2. Create bot
    bot = Bot(
        token=Config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # 3. Register handlers
    dp.include_router(start.router)
    dp.include_router(categories.router)
    dp.include_router(subscription.router)
    dp.include_router(generate_response.router)
    dp.include_router(profile.router)
    dp.include_router(orders.router)
    
    # 4. Create web app
    app = web.Application()
    app.router.add_get('/', handle_health)
    app.router.add_get('/health', handle_health)
    app.router.add_get('/webapp', handle_webapp)
    app.router.add_get('/api/orders', handle_api_orders)
    
    # 5. Setup webhook or polling
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '')
    
    if domain:
        # Webhook mode
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        
        webhook_url = f"https://{domain}/webhook"
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(webhook_url)
        logger.info(f"Webhook set: {webhook_url}")
        logger.info(f"WebApp URL: https://{domain}/webapp")
        
        webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_handler.register(app, path='/webhook')
        setup_application(app, dp, bot=bot)
        
        # Start web server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', Config.WEBAPP_PORT)
        await site.start()
        
        logger.info(f"Server started on port {Config.WEBAPP_PORT}")
        
        # Keep running
        await asyncio.Event().wait()
    else:
        # Polling mode + web server
        logger.info("No RAILWAY_PUBLIC_DOMAIN, starting polling + web server")
        
        # Start web server in background
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', Config.WEBAPP_PORT)
        await site.start()
        logger.info(f"Web server started on port {Config.WEBAPP_PORT}")
        
        # Start polling
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting bot polling...")
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
