# parsers/__init__.py
from .base import BaseParser
from .kwork import KworkParser
from .fl_ru import FLRuParser
from .habr_freelance import HabrFreelanceParser
from .hh_ru import HHParser
from .freelanceru import FreelanceRuParser

ALL_PARSERS = [
    HHParser(),          # Работает стабильно (API)
    KworkParser(),       # Kwork
    FLRuParser(),        # FL.ru
    FreelanceRuParser(), # Freelance.ru
    # HabrFreelanceParser(),  # Закрыт
]

__all__ = [
    'BaseParser',
    'KworkParser', 
    'FLRuParser',
    'HabrFreelanceParser',
    'HHParser',
    'FreelanceRuParser',
    'ALL_PARSERS'
]
