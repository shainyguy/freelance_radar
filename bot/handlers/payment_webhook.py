# bot/handlers/payment_webhook.py
from aiohttp import web
from yookassa.domain.notification import WebhookNotification
from database.db import Database
import logging

logger = logging.getLogger(__name__)


async def yukassa_webhook(request: web.Request) -> web.Response:
    """Обработка webhook от ЮKassa"""
    try:
        body = await request.json()
        notification = WebhookNotification(body)
        
        payment = notification.object
        
        if payment.status == "succeeded":
            # Подтверждаем платёж и продлеваем подписку
            await Database.confirm_payment(payment.id)
            logger.info(f"Payment {payment.id} confirmed")
        
        return web.Response(status=200)
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=500)


def setup_payment_routes(app: web.Application):
    app.router.add_post("/yukassa/webhook", yukassa_webhook)