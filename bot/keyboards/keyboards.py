# bot/keyboards/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

CATEGORIES = {
    "design": "🎨 Дизайн",
    "python": "🐍 Python/Программирование",
    "copywriting": "✍️ Копирайтинг",
    "marketing": "📈 Маркетинг",
    "video": "🎬 Видео",
    "audio": "🎵 Аудио",
}


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Мои категории"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="💳 Подписка"), KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True
    )


def get_categories_keyboard(selected: list = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора категорий"""
    selected = selected or []
    
    buttons = []
    for cat_id, cat_name in CATEGORIES.items():
        check = "✅ " if cat_id in selected else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{check}{cat_name}",
                callback_data=f"toggle_cat:{cat_id}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(text="💾 Сохранить", callback_data="save_categories")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_order_keyboard(order_id: int, order_url: str) -> InlineKeyboardMarkup:
    """Клавиатура для заказа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✨ Сгенерировать отклик", callback_data=f"generate:{order_id}")
        ],
        [
            InlineKeyboardButton(text="🔗 Открыть заказ", url=order_url),
            InlineKeyboardButton(text="❌ Скрыть", callback_data=f"hide:{order_id}")
        ]
    ])


def get_subscription_keyboard(payment_url: str = None) -> InlineKeyboardMarkup:
    """Клавиатура подписки"""
    buttons = []
    
    if payment_url:
        buttons.append([
            InlineKeyboardButton(text="💳 Оплатить 690₽/мес", url=payment_url)
        ])
        buttons.append([
            InlineKeyboardButton(text="✅ Я оплатил", callback_data="check_payment")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_trial_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для старта пробного периода"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать бесплатно (3 дня)", callback_data="start_trial")],
        [InlineKeyboardButton(text="💳 Сразу купить подписку", callback_data="buy_subscription")]
    ])


def get_settings_keyboard(user) -> InlineKeyboardMarkup:
    """Настройки пользователя"""
    pause_text = "⏸ Приостановить" if user.is_active else "▶️ Возобновить"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Мин. бюджет", callback_data="set_min_budget")],
        [InlineKeyboardButton(text=pause_text, callback_data="toggle_active")],
    ])