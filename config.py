"""
CRYPTONITA PRODUCTION - CONFIGURATION
======================================
Centralized configuration management using Pydantic Settings
"""

import os
from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from dotenv import load_dotenv

# Load .env file
load_dotenv()

PROJECT_ROOT = Path(__file__).parent


class Settings(BaseSettings):
    """Application Settings"""

    # ============================================
    # APPLICATION
    # ============================================
    APP_NAME: str = "Cryptonita Production"
    APP_VERSION: str = "3.0"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=True)

    # ============================================
    # DATABASE
    # ============================================
    DB_USER: str = Field(..., env="DB_USER")
    DB_PASSWORD: str = Field(..., env="DB_PASSWORD")
    DB_HOST: str = Field(default="localhost", env="DB_HOST")
    DB_PORT: int = Field(default=5432, env="DB_PORT")
    DB_NAME: str = Field(..., env="DB_NAME")

    # ============================================
    # REDIS
    # ============================================
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")

    # ============================================
    # BINANCE API
    # ============================================
    TRADING_MODE: str = Field(default="testnet", env="TRADING_MODE")  # testnet or production

    # Production API
    BINANCE_API_KEY: Optional[str] = Field(default=None, env="BINANCE_API_KEY")
    BINANCE_API_SECRET: Optional[str] = Field(default=None, env="BINANCE_API_SECRET")

    # Testnet API
    BINANCE_TESTNET_API_KEY: str = Field(..., env="BINANCE_TESTNET_API_KEY")
    BINANCE_TESTNET_API_SECRET: str = Field(..., env="BINANCE_TESTNET_API_SECRET")

    # ============================================
    # TRADING CONFIGURATION
    # ============================================
    INITIAL_CAPITAL: float = Field(default=10000.0, env="INITIAL_CAPITAL")
    MAX_POSITION_SIZE_USD: float = Field(default=500.0, env="MAX_POSITION_SIZE_USD")
    MAX_DAILY_LOSS_USD: float = Field(default=200.0, env="MAX_DAILY_LOSS_USD")
    MAX_TOTAL_RISK_PERCENT: float = Field(default=2.0, env="MAX_TOTAL_RISK_PERCENT")
    REQUIRE_MANUAL_APPROVAL: bool = Field(default=True, env="REQUIRE_MANUAL_APPROVAL")

    # Model thresholds from V3 config
    PREDICTION_THRESHOLD: float = 0.95  # 95% confidence threshold (conservative trading)
    POSITION_SIZE_PCT: float = 0.10  # 10% of capital per position
    MAX_POSITION_SIZE_PCT: float = 0.15  # Max 15% per position
    TAKE_PROFIT_PCT: float = 0.15  # 15% take profit
    STOP_LOSS_PCT: float = 0.05  # 5% stop loss
    MAX_PORTFOLIO_RISK_PCT: float = 0.30  # 30% max portfolio risk
    MAX_POSITIONS: int = 10  # Max 10 simultaneous positions

    # ============================================
    # SUPPORTED TICKERS (Altcoins volátiles para pumps +20%)
    # ============================================
    # Criterios de selección:
    # - Alta volatilidad (>5% movimiento diario típico)
    # - Volumen >$20M USD/día
    # - Market cap: $100M - $15B (excluye top 5 muy estables)
    # - EXCLUYE: BTC, ETH, BNB (volatilidad <3%, no generan pumps +20%)
    #
    # Total: 40 monedas organizadas por categoría
    TICKERS: List[str] = [
        # Layer 1 / Layer 2 (Alta volatilidad, buen volumen)
        "SOLUSDT", "AVAXUSDT", "NEARUSDT", "APTUSDT", "SUIUSDT",
        "SEIUSDT", "ARBUSDT", "OPUSDT", "INJUSDT",
        # FTMUSDT removed - symbol changed

        # DeFi (Alto potencial de pumps por noticias)
        "UNIUSDT", "AAVEUSDT", "LDOUSDT", "RUNEUSDT",
        "CRVUSDT", "GMXUSDT", "DYDXUSDT",
        # MKRUSDT removed - not available on Binance

        # Gaming / Metaverse (Muy volátiles, eventos frecuentes)
        "SANDUSDT", "MANAUSDT", "AXSUSDT", "IMXUSDT", "GALAUSDT",

        # AI / Compute (Tendencia 2024-2025, alta volatilidad)
        "FETUSDT", "WLDUSDT", "RENDERUSDT",
        # AGIXUSDT removed - merged with other tokens

        # Memecoins (Alto volumen y volatilidad extrema)
        "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "BONKUSDT",

        # Otros altcoins sólidos (volatilidad media-alta)
        "DOTUSDT", "ATOMUSDT", "ADAUSDT", "POLUSDT", "LINKUSDT",  # POL is MATIC rebranded
        "ICPUSDT", "FILUSDT", "HBARUSDT", "VETUSDT", "ALGOUSDT"
    ]

    # ============================================
    # MODEL CONFIGURATION
    # ============================================
    MODEL_VERSION: str = "V3"
    MODEL_FILE: str = str(PROJECT_ROOT / "PRODUCTION_SYSTEM/models/production_model_v3.json")
    FEATURES_CONFIG_FILE: str = str(PROJECT_ROOT / "PRODUCTION_SYSTEM/configs/production_features_config_v3.json")
    MASTER_CONFIG_FILE: str = str(PROJECT_ROOT / "PRODUCTION_SYSTEM/configs/PRODUCTION_MASTER_CONFIG.json")

    # ============================================
    # LOGGING
    # ============================================
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FILE: str = Field(default="logs/cryptonita.log", env="LOG_FILE")

    # ============================================
    # SYSTEM
    # ============================================
    TIMEZONE: str = Field(default="UTC", env="TIMEZONE")

    # ============================================
    # API CONFIGURATION
    # ============================================
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_WORKERS: int = 4

    # JWT Authentication
    SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production-please-use-strong-key-here",
        env="SECRET_KEY"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra variables in .env

    # ============================================
    # COMPUTED PROPERTIES
    # ============================================

    def get_database_url(self) -> str:
        """Get database connection URL"""
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    def get_binance_credentials(self) -> tuple[str, str]:
        """Get appropriate Binance credentials based on trading mode"""
        if self.TRADING_MODE == "testnet":
            return self.BINANCE_TESTNET_API_KEY, self.BINANCE_TESTNET_API_SECRET
        else:
            if not self.BINANCE_API_KEY or not self.BINANCE_API_SECRET:
                raise ValueError("Production Binance API credentials not set!")
            return self.BINANCE_API_KEY, self.BINANCE_API_SECRET

    def is_testnet(self) -> bool:
        """Check if running in testnet mode"""
        return self.TRADING_MODE == "testnet"

    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.ENVIRONMENT == "production"


# Global settings instance
settings = Settings()


# Setup logging paths
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
