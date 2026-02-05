# parsers/__init__.py (обновлённый)
from .base import BaseParser
from .kwork import KworkParser
from .fl_ru import FLRuParser
from .habr_freelance import HabrFreelanceParser
from .hh_ru import HHParser
from .telegram_channels import TelegramChannelsParser

ALL_PARSERS = [
    KworkParser(),
    FLRuParser(),
    HabrFreelanceParser(),
    HHParser(),
]

__all__ = [
    'BaseParser',
    'KworkParser', 
    'FLRuParser',
    'HabrFreelanceParser',
    'HHParser',
    'TelegramChannelsParser',
    'ALL_PARSERS'
]