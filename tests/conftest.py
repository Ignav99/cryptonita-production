"""
Test configuration and fixtures.
Mock external dependencies before any imports.
"""

import sys
from unittest.mock import MagicMock

# Pre-mock all external dependencies that would fail imports
external_mocks = {
    'loguru': MagicMock(),
    'pydantic_settings': MagicMock(),
    'pydantic': MagicMock(),
    'dotenv': MagicMock(),
    'ccxt': MagicMock(),
    'ccxt.async_support': MagicMock(),
    'ta': MagicMock(),
    'pandas_ta': MagicMock(),
    'sklearn': MagicMock(),
    'sklearn.ensemble': MagicMock(),
    'sklearn.preprocessing': MagicMock(),
    'sklearn.model_selection': MagicMock(),
    'sklearn.metrics': MagicMock(),
    'sklearn.neural_network': MagicMock(),
    'joblib': MagicMock(),
    'requests': MagicMock(),
    'aiohttp': MagicMock(),
    'binance': MagicMock(),
    'binance.client': MagicMock(),
    'binance.exceptions': MagicMock(),
    'binance.enums': MagicMock(),
    'pymongo': MagicMock(),
    'pymongo.errors': MagicMock(),
    'telegram': MagicMock(),
    'telegram.ext': MagicMock(),
    'newsapi': MagicMock(),
    'yfinance': MagicMock(),
    'sqlalchemy': MagicMock(),
    'sqlalchemy.orm': MagicMock(),
    'sqlalchemy.pool': MagicMock(),
}

for module_name, mock in external_mocks.items():
    sys.modules[module_name] = mock
