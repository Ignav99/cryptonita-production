"""
CRYPTONITA PRODUCTION - CONFIGURATION
======================================
Centralized configuration management using Pydantic Settings
"""

import os
from pathlib import Path
from typing import Optional, List, Dict
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

    # Circuit breaker: portfolio-level drawdown protection
    CIRCUIT_BREAKER_REDUCE_PCT: float = 0.10   # -10% drawdown = reduce position sizes 50%
    CIRCUIT_BREAKER_PAUSE_PCT: float = 0.15    # -15% drawdown = pause all new entries
    SINGLE_POSITION_MAX_LOSS_PCT: float = 0.10 # Force close any position down >10%

    # Maximum holding period for underwater positions
    MAX_HOLD_DAYS_REVIEW: int = 5   # Underwater >5 days = reduce 50%
    MAX_HOLD_DAYS_FORCE: int = 10   # Underwater >10 days = force close

    # Per-ticker exposure limit
    MAX_TICKER_EXPOSURE_PCT: float = 0.08  # Max 8% portfolio in one ticker

    # Prediction threshold — now uses 3-level confidence system per tier.
    # This is the global fallback; actual thresholds are in COIN_RISK_PROFILES.
    PREDICTION_THRESHOLD: float = 0.15  # Lowest exploratory threshold (overridden per tier)
    POSITION_SIZE_PCT: float = 0.10  # 10% of capital per position
    MAX_POSITION_SIZE_PCT: float = 0.15  # Max 15% per position
    # TP/SL optimized by Monte Carlo simulation (2000 paths × 30yr):
    # - SL 5% / TP 20% (ratio 4:1) = best median outcome
    # - Multi-level TP in DynamicRiskManager: TP1=12%, TP2=25%, TP3=50%
    TAKE_PROFIT_PCT: float = 0.20  # 20% base take profit (was 15%)
    STOP_LOSS_PCT: float = 0.05  # 5% stop loss
    MAX_PORTFOLIO_RISK_PCT: float = 0.30  # 30% max portfolio risk
    MAX_POSITIONS: int = 10  # Smart rotation will handle overflow

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
    # Full 39-coin universe — maximize opportunity detection
    # Smart rotation system will manage capital allocation
    TICKERS: List[str] = [
        # Layer 1 / Layer 2
        "SOLUSDT", "AVAXUSDT", "NEARUSDT", "APTUSDT", "SUIUSDT",
        "SEIUSDT", "ARBUSDT", "OPUSDT", "INJUSDT",
        # DeFi
        "UNIUSDT", "AAVEUSDT", "LDOUSDT", "RUNEUSDT",
        "CRVUSDT", "GMXUSDT", "DYDXUSDT",
        # Gaming / Metaverse
        "SANDUSDT", "MANAUSDT", "AXSUSDT", "IMXUSDT", "GALAUSDT",
        # AI / Compute
        "FETUSDT", "WLDUSDT", "RENDERUSDT",
        # Memecoins
        "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "BONKUSDT",
        # Solid altcoins
        "DOTUSDT", "ATOMUSDT", "ADAUSDT", "POLUSDT", "LINKUSDT",
        "ICPUSDT", "FILUSDT", "HBARUSDT", "VETUSDT", "ALGOUSDT",
        # --- Phase 5 expansion (8 new coins) ---
        # AI expansion
        "TAOUSDT", "ARKMUSDT",
        # RWA
        "ONDOUSDT",
        # Infra/DePIN
        "ARUSDT", "IOTAUSDT",
        # New L2
        "STXUSDT", "TIAUSDT", "MANTAUSDT",
    ]

    # ============================================
    # COIN RISK PROFILES (Tier-based dynamic thresholds)
    # ============================================
    # Tier 1 (Blue Chip): lower threshold, bigger positions
    # Tier 4 (Meme/Small): higher threshold, smaller positions
    #
    # BAND-PASS THRESHOLD SYSTEM (calibrated Apr 13, 2026)
    # Key insight: prob 0.30-0.35 = 94.7% WR, prob >0.42 = 0% WR
    # threshold = CEILING (reject overfit signals above this)
    # threshold_medium = FLOOR (minimum to enter)
    # Smart rotation handles capital: swap weak positions for stronger signals
    COIN_RISK_PROFILES: Dict[str, Dict] = {
        # TIER 1 — Blue Chip (band-pass lowered to match model output range)
        "LINKUSDT": {"tier": 1, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.15, "kelly_mult": 1.2},
        "DOTUSDT":  {"tier": 1, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.15, "kelly_mult": 1.2},
        "ADAUSDT":  {"tier": 1, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.15, "kelly_mult": 1.2},
        "ATOMUSDT": {"tier": 1, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.15, "kelly_mult": 1.2},
        "POLUSDT":  {"tier": 1, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.15, "kelly_mult": 1.2},
        # TIER 2 — Large Cap
        "SOLUSDT":  {"tier": 2, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.12, "kelly_mult": 1.0},
        "AVAXUSDT": {"tier": 2, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.12, "kelly_mult": 1.0},
        "NEARUSDT": {"tier": 2, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.12, "kelly_mult": 1.0},
        "UNIUSDT":  {"tier": 2, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.12, "kelly_mult": 1.0},
        "AAVEUSDT": {"tier": 2, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.12, "kelly_mult": 1.0},
        "ICPUSDT":  {"tier": 2, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.12, "kelly_mult": 1.0},
        "HBARUSDT": {"tier": 2, "threshold": 0.42, "threshold_medium": 0.25, "threshold_low": 0.25, "max_position_pct": 0.12, "kelly_mult": 1.0},
        # TIER 3 — Mid Cap
        "ARBUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "OPUSDT":     {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "INJUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "SUIUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "SEIUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "APTUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "LDOUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "RUNEUSDT":   {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "CRVUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "GMXUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "DYDXUSDT":   {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "SANDUSDT":   {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "MANAUSDT":   {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "AXSUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "IMXUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "GALAUSDT":   {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "FETUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "WLDUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "RENDERUSDT": {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "FILUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "VETUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "ALGOUSDT":   {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        # TIER 4 — Meme (same band-pass, smaller positions)
        "DOGEUSDT":  {"tier": 4, "threshold": 0.42, "threshold_medium": 0.30, "threshold_low": 0.30, "max_position_pct": 0.06, "kelly_mult": 0.5},
        "SHIBUSDT":  {"tier": 4, "threshold": 0.42, "threshold_medium": 0.30, "threshold_low": 0.30, "max_position_pct": 0.06, "kelly_mult": 0.5},
        "PEPEUSDT":  {"tier": 4, "threshold": 0.42, "threshold_medium": 0.30, "threshold_low": 0.30, "max_position_pct": 0.06, "kelly_mult": 0.5},
        "FLOKIUSDT": {"tier": 4, "threshold": 0.42, "threshold_medium": 0.30, "threshold_low": 0.30, "max_position_pct": 0.06, "kelly_mult": 0.5},
        "BONKUSDT":  {"tier": 4, "threshold": 0.42, "threshold_medium": 0.30, "threshold_low": 0.30, "max_position_pct": 0.06, "kelly_mult": 0.5},
        # --- Phase 5 expansion risk profiles ---
        # AI (Tier 3)
        "TAOUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "ARKMUSDT":   {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        # RWA (Tier 2 - institutional narrative)
        "ONDOUSDT":   {"tier": 2, "threshold": 0.80, "threshold_medium": 0.60, "threshold_low": 0.60, "max_position_pct": 0.12, "kelly_mult": 1.0},
        # Infra/DePIN (Tier 3)
        "ARUSDT":     {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "IOTAUSDT":   {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        # New L2 (Tier 3)
        "STXUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "TIAUSDT":    {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
        "MANTAUSDT":  {"tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28, "max_position_pct": 0.10, "kelly_mult": 0.8},
    }

    # Default profile for tickers not in the map
    DEFAULT_RISK_PROFILE: Dict = {
        "tier": 3, "threshold": 0.42, "threshold_medium": 0.28, "threshold_low": 0.28,
        "max_position_pct": 0.10, "kelly_mult": 0.8
    }

    # ============================================
    # SIGNAL CONFIDENCE LEVELS
    # ============================================
    # Only 2 active levels: HIGH and MEDIUM.
    # EXPLORATORY disabled (threshold_low = threshold_medium) — was 48.7% WR.
    # Testing phase: slightly reduced position sizing until we have 30 days of data.
    CONFIDENCE_LEVELS: Dict[str, Dict] = {
        "high": {
            "position_mult": 0.75,  # 75% of Kelly (testing phase)
            "tp_mult": 1.0,         # Standard TP/SL
            "sl_mult": 1.0,
            "max_positions": 8,     # Conservative during testing
        },
        "medium": {
            "position_mult": 0.40,  # 40% of Kelly (testing phase)
            "tp_mult": 0.70,        # Tighter TP (TP1~8%, TP2~18%, TP3~35%)
            "sl_mult": 0.75,        # Tighter SL (~3.75%)
            "max_positions": 5,     # Limit concurrent medium positions
        },
        "exploratory": {
            "position_mult": 0.0,   # DISABLED — do not trade
            "tp_mult": 0.0,
            "sl_mult": 0.0,
            "max_positions": 0,
        },
    }

    # ============================================
    # TICKER DISPLAY NAMES (for news/social matching)
    # ============================================
    TICKER_DISPLAY_NAMES: Dict[str, str] = {
        "SOLUSDT": "Solana", "AVAXUSDT": "Avalanche", "NEARUSDT": "NEAR",
        "APTUSDT": "Aptos", "SUIUSDT": "Sui", "SEIUSDT": "Sei",
        "ARBUSDT": "Arbitrum", "OPUSDT": "Optimism", "INJUSDT": "Injective",
        "UNIUSDT": "Uniswap", "AAVEUSDT": "Aave", "LDOUSDT": "Lido",
        "RUNEUSDT": "THORChain", "CRVUSDT": "Curve", "GMXUSDT": "GMX",
        "DYDXUSDT": "dYdX", "SANDUSDT": "Sandbox", "MANAUSDT": "Decentraland",
        "AXSUSDT": "Axie", "IMXUSDT": "Immutable", "GALAUSDT": "Gala",
        "FETUSDT": "Fetch.ai", "WLDUSDT": "Worldcoin", "RENDERUSDT": "Render",
        "DOGEUSDT": "Dogecoin", "SHIBUSDT": "Shiba", "PEPEUSDT": "Pepe",
        "FLOKIUSDT": "Floki", "BONKUSDT": "Bonk",
        "DOTUSDT": "Polkadot", "ATOMUSDT": "Cosmos", "ADAUSDT": "Cardano",
        "POLUSDT": "Polygon", "LINKUSDT": "Chainlink", "ICPUSDT": "Internet Computer",
        "FILUSDT": "Filecoin", "HBARUSDT": "Hedera", "VETUSDT": "VeChain",
        "ALGOUSDT": "Algorand",
        "TAOUSDT": "Bittensor", "ARKMUSDT": "Arkham", "ONDOUSDT": "Ondo",
        "ARUSDT": "Arweave", "IOTAUSDT": "IOTA", "STXUSDT": "Stacks",
        "TIAUSDT": "Celestia", "MANTAUSDT": "Manta",
    }

    # ============================================
    # MODEL CONFIGURATION
    # ============================================
    MODEL_VERSION: str = "V4"

    # V4 Ensemble Model (XGB+LGBM+CatBoost + LogisticRegression meta-learner)
    USE_V4_MODEL: bool = Field(default=True, env="USE_V4_MODEL")
    V4_MODEL_DIR: str = str(PROJECT_ROOT / "PRODUCTION_SYSTEM/models/v4")
    KELLY_FRACTION: float = Field(default=0.25, env="KELLY_FRACTION")

    # Auto-Training Configuration
    AUTO_TRAIN_ENABLED: bool = Field(default=True, env="AUTO_TRAIN_ENABLED")  # Enabled: 2GB Render Standard
    AUTO_TRAIN_INTERVAL_DAYS: int = Field(default=7, env="AUTO_TRAIN_INTERVAL_DAYS")
    AUTO_TRAIN_MODE: str = Field(default="quick", env="AUTO_TRAIN_MODE")
    AUTO_TRAIN_MIN_SHARPE: float = Field(default=0.5, env="AUTO_TRAIN_MIN_SHARPE")

    # ============================================
    # LOGGING
    # ============================================
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FILE: str = Field(default="logs/cryptonita.log", env="LOG_FILE")

    # ============================================
    # TELEGRAM NOTIFICATIONS
    # ============================================
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: Optional[str] = Field(default=None, env="TELEGRAM_CHAT_ID")
    HEALTHCHECK_PING_URL: Optional[str] = Field(default=None, env="HEALTHCHECK_PING_URL")

    # ============================================
    # ENGINE UPGRADE — External Intelligence APIs
    # ============================================
    # Claude Haiku for news sentiment analysis (~$0.03-0.05/day)
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    # CoinGecko for social/developer data (free tier, optional pro key)
    COINGECKO_API_KEY: Optional[str] = Field(default=None, env="COINGECKO_API_KEY")
    # Enable Amazon Chronos probabilistic forecasting (requires 2GB+ RAM on Render)
    USE_CHRONOS: bool = Field(default=False, env="USE_CHRONOS")

    # ============================================
    # SECTOR ALLOCATION (max simultaneous positions per sector)
    # ============================================
    COIN_SECTORS: Dict[str, str] = {
        # L1/L2
        "SOLUSDT": "L1", "AVAXUSDT": "L1", "NEARUSDT": "L1", "APTUSDT": "L1",
        "SUIUSDT": "L2", "SEIUSDT": "L2", "ARBUSDT": "L2", "OPUSDT": "L2", "INJUSDT": "L1",
        # DeFi
        "UNIUSDT": "DeFi", "AAVEUSDT": "DeFi", "LDOUSDT": "DeFi", "RUNEUSDT": "DeFi",
        "CRVUSDT": "DeFi", "GMXUSDT": "DeFi", "DYDXUSDT": "DeFi",
        # Gaming
        "SANDUSDT": "Gaming", "MANAUSDT": "Gaming", "AXSUSDT": "Gaming",
        "IMXUSDT": "Gaming", "GALAUSDT": "Gaming",
        # AI
        "FETUSDT": "AI", "WLDUSDT": "AI", "RENDERUSDT": "AI",
        # Meme
        "DOGEUSDT": "Meme", "SHIBUSDT": "Meme", "PEPEUSDT": "Meme",
        "FLOKIUSDT": "Meme", "BONKUSDT": "Meme",
        # Solid Alts
        "DOTUSDT": "L1", "ATOMUSDT": "L1", "ADAUSDT": "L1", "POLUSDT": "L2",
        "LINKUSDT": "L1", "ICPUSDT": "L1", "FILUSDT": "Infra",
        "HBARUSDT": "L1", "VETUSDT": "L1", "ALGOUSDT": "L1",
        # New: AI expansion
        "TAOUSDT": "AI", "ARKMUSDT": "AI",
        # New: RWA
        "ONDOUSDT": "RWA",
        # New: Infra/DePIN
        "ARUSDT": "Infra", "IOTAUSDT": "Infra",
        # New: L2
        "STXUSDT": "L2", "TIAUSDT": "L1", "MANTAUSDT": "L2",
        "ZKUSDT": "L2", "STRKUSDT": "L2",
        # New: Gaming
        "BEAMUSDT": "Gaming",
    }

    SECTOR_LIMITS: Dict[str, int] = {
        "L1": 4, "L2": 3, "DeFi": 3, "AI": 3,
        "Gaming": 2, "Meme": 2, "RWA": 2, "Infra": 2,
    }

    # ============================================
    # REGIME-BASED PARAMETER ADJUSTMENTS
    # ============================================
    REGIME_ADJUSTMENTS: Dict[str, Dict] = {
        "Bull": {
            "max_positions": 10,
            "threshold_offset": -0.02,
            "position_size_mult": 1.0,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.25,
        },
        "Sideways": {
            "max_positions": 7,
            "threshold_offset": 0.0,
            "position_size_mult": 0.7,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.20,
        },
        "Bear": {
            "max_positions": 4,
            "threshold_offset": 0.05,
            "position_size_mult": 0.4,
            "stop_loss_pct": 0.04,
            "take_profit_pct": 0.12,
        },
    }

    # ============================================
    # POSITION LIFECYCLE
    # ============================================
    INCUBATION_PCT: float = 0.25          # First 25% of predicted_hold = protected
    ROTATION_EV_MULTIPLIER: float = 1.5   # new_ev must be 1.5x weakest to rotate
    ROTATION_MIN_THRESHOLD: float = 0.005 # Minimum absolute improvement to rotate
    MAX_ZOMBIE_DAYS: int = 14             # Force close zombies at 14 days

    # ============================================
    # SIGNAL QUEUE
    # ============================================
    SIGNAL_QUEUE_MAX_AGE_HOURS: float = 12.0
    SIGNAL_QUEUE_MAX_SIZE: int = 5

    # ============================================
    # EXIT OPTIMIZER
    # ============================================
    EXIT_COOLDOWN_HOURS: int = 24         # Cooldown between exits for same reason
    TIGHTEN_FACTOR_BEARISH: float = 0.5   # Reduce SL distance 50% on bearish
    TIGHTEN_FACTOR_VOLUME: float = 0.6    # Reduce SL distance 40% on volume collapse

    # ============================================
    # HEALTH MONITOR
    # ============================================
    MAX_TRADES_PER_DAY: int = 20          # Circuit breaker
    STALE_PRICE_ALERT_HOURS: int = 2

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
