# bot/utils/helpers.py
import re
import html
from typing import Optional


def format_budget(budget_value: Optional[int], budget_text: str = None) -> str:
    """
    Форматирует бюджет для отображения.
    
    Args:
        budget_value: Числовое значение бюджета
        budget_text: Текстовое представление (если есть)
    
    Returns:
        Отформатированная строка бюджета
    """
    if budget_text:
        return budget_text
    
    if not budget_value or budget_value == 0:
        return "Не указан"
    
    if budget_value >= 1000000:
        return f"{budget_value / 1000000:.1f}M ₽"
    elif budget_value >= 1000:
        return f"{budget_value / 1000:.0f}K ₽"
    else:
        return f"{budget_value:,} ₽".replace(",", " ")


def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """
    Обрезает текст до указанной длины.
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина
        suffix: Суффикс при обрезке
    
    Returns:
        Обрезанный текст
    """
    if not text:
        return ""
    
    text = text.strip()
    
    if len(text) <= max_length:
        return text
    
    # Обрезаем по последнему пробелу, чтобы не резать слова
    truncated = text[:max_length - len(suffix)]
    last_space = truncated.rfind(" ")
    
    if last_space > max_length * 0.7:  # Если пробел не слишком далеко
        truncated = truncated[:last_space]
    
    return truncated + suffix


def escape_html(text: str) -> str:
    """
    Экранирует HTML символы для безопасного отображения в Telegram.
    
    Args:
        text: Исходный текст
    
    Returns:
        Экранированный текст
    """
    if not text:
        return ""
    return html.escape(text)


def extract_budget_value(text: str) -> int:
    """
    Извлекает числовое значение бюджета из текста.
    
    Args:
        text: Текст с бюджетом (например: "50 000 руб", "15к", "от 100$")
    
    Returns:
        Числовое значение бюджета в рублях
    """
    if not text:
        return 0
    
    text = text.lower().replace(" ", "")
    
    # Ищем числа
    numbers = re.findall(r'(\d+(?:\.\d+)?)', text)
    if not numbers:
        return 0
    
    value = float(numbers[0])
    
    # Проверяем множители
    if 'к' in text or 'k' in text:
        value *= 1000
    elif 'м' in text or 'm' in text:
        value *= 1000000
    
    # Конвертация валют (примерно)
    if '$' in text or 'usd' in text or 'долл' in text:
        value *= 90  # Примерный курс
    elif '€' in text or 'eur' in text or 'евро' in text:
        value *= 100  # Примерный курс
    
    return int(value)


def clean_description(text: str) -> str:
    """
    Очищает описание заказа от лишних символов.
    
    Args:
        text: Исходное описание
    
    Returns:
        Очищенное описание
    """
    if not text:
        return ""
    
    # Убираем множественные пробелы и переносы
    text = re.sub(r'\s+', ' ', text)
    
    # Убираем HTML теги
    text = re.sub(r'<[^>]+>', '', text)
    
    # Убираем ссылки
    text = re.sub(r'http[s]?://\S+', '[ссылка]', text)
    
    return text.strip()


def format_order_message(order) -> str:
    """
    Форматирует сообщение о заказе.
    
    Args:
        order: Объект заказа
    
    Returns:
        Отформатированное сообщение
    """
    source_emoji = {
        "kwork": "🟢 Kwork",
        "fl.ru": "🔵 FL.ru",
        "habr_freelance": "🟣 Habr Freelance",
        "hh": "🔴 HH.ru",
        "telegram": "📱 Telegram"
    }
    
    source = source_emoji.get(order.source, f"📋 {order.source}")
    title = escape_html(order.title)
    description = escape_html(truncate_text(order.description, 500))
    budget = format_budget(order.budget_value, order.budget)
    
    return f"""
{source}

📌 <b>{title}</b>

{description}

💰 Бюджет: {budget}

🔗 <a href="{order.url}">Открыть заказ</a>
"""


def time_ago(dt) -> str:
    """
    Возвращает относительное время (например: "5 минут назад").
    
    Args:
        dt: datetime объект
    
    Returns:
        Строка с относительным временем
    """
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
        return f"{minutes} мин. назад"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} ч. назад"
    else:
        days = int(seconds // 86400)
        return f"{days} дн. назад"