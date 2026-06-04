"""
CRYPTONITA TRADING BOT V4
==========================
Main trading bot implementation with:
- Market scanning every 12 hours
- Position monitoring every 15 minutes
- Automatic trade execution
- Risk management
- Database logging
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from loguru import logger
import numpy as np
import pandas as pd

from config import settings
from src.services.binance_service import BinanceService
from src.services.binance_data_service import BinanceDataService
from src.data.storage.db_manager import DatabaseManager
from src.data.macro_data import MacroDataFetcher
from src.trading.dynamic_risk_manager import DynamicRiskManager
from src.services.telegram_notifier import TelegramNotifier
from src.models.correlation_engine import CorrelationEngine
from src.models.hold_time_estimator import HoldTimeEstimator
from src.trading.position_lifecycle import PositionLifecycleManager
from src.trading.signal_queue import SignalQueue
from src.bot.health_monitor import HealthMonitor


class TradingBot:
    """
    Main trading bot for automated cryptocurrency trading
    """

    def __init__(self):
        """Initialize trading bot"""
        logger.info("=" * 60)
        logger.info("🤖 INITIALIZING CRYPTONITA TRADING BOT V5")
        logger.info("=" * 60)

        # Load configuration from defaults
        self.config = self._default_config()

        # Initialize services
        self.binance = BinanceService()  # For trading (testnet)
        self.binance_data = BinanceDataService()  # For historical data (production, read-only)

        # V5 Ternary Predictor (LONG / SHORT / HOLD)
        from src.models.predictor_v5 import TradingPredictorV5
        from src.services.binance_futures_service import BinanceFuturesService
        self.predictor = TradingPredictorV5()
        self.binance_futures = BinanceFuturesService()  # For SHORT execution
        logger.info("Using V5 Ternary Predictor (LONG/SHORT/HOLD)")

        self.db = DatabaseManager(settings.get_database_url())
        self.macro_fetcher = MacroDataFetcher()
        self.risk_manager = DynamicRiskManager()  # Dynamic TP/SL management
        self.notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID)
        self.correlation_engine = CorrelationEngine()

        # Position Lifecycle System
        self.hold_estimator = HoldTimeEstimator()
        self.lifecycle_manager = PositionLifecycleManager(self.hold_estimator)
        self.signal_queue = SignalQueue()
        self.health_monitor = HealthMonitor()

        logger.info("💡 Using Binance PRODUCTION for data, TESTNET for trading")

        # Bot state
        self.is_running = False
        self._binance_connected = False  # set after connectivity check in start()
        self.cycle_number = 0
        self.daily_loss = 0.0
        self.last_scan_time = None
        self.positions: Dict[str, Dict] = {}
        self._current_regime: Dict = {}
        self._regime_max_positions: int = settings.MAX_POSITIONS
        self._regime_threshold_offset: float = 0.0

        # Trading parameters from config
        self.scan_interval_hours = self.config['trading']['scan_interval_hours']
        self.position_monitoring_minutes = self.config['trading']['position_monitoring_minutes']
        self.auto_trading = self.config['trading']['auto_trading_enabled']

        # Load existing positions from DB (survive restarts)
        self._load_positions_from_db()

        logger.success("✅ Trading Bot initialized successfully")
        self._log_configuration()

    def _default_config(self) -> dict:
        """Return default configuration"""
        return {
            "trading": {
                "scan_interval_hours": 6,
                "position_monitoring_minutes": 5,  # Reduced from 15: faster SL/TP checks
                "auto_trading_enabled": True,
                "require_manual_approval": False
            },
            "risk_management": {
                "max_positions": 10,
                "max_daily_loss_usd": 200
            }
        }

    def _load_positions_from_db(self):
        """Load existing positions from database so bot survives restarts.
        Automatically cleans up dust positions (remaining_qty too small to trade)."""
        try:
            positions_df = self.db.get_positions()
            if len(positions_df) == 0:
                logger.info("No existing positions in DB")
                return

            dust_cleaned = 0
            for _, pos in positions_df.iterrows():
                ticker = pos['ticker']
                entry_price = float(pos['avg_buy_price'])
                _max_qty = float(pos['quantity'])
                _raw_remaining = pos.get('remaining_quantity')
                if pd.notna(_raw_remaining):
                    remaining_qty = max(0.0, min(float(_raw_remaining), _max_qty))
                else:
                    remaining_qty = _max_qty
                current_price = float(pos['current_price']) if pd.notna(pos.get('current_price')) else entry_price

                # Skip and clean up dust positions (too small to trade)
                if remaining_qty <= 0 or self.binance.is_dust_position(ticker, abs(remaining_qty), current_price):
                    logger.warning(f"🧹 Cleaning dust position: {ticker} (remaining: {remaining_qty})")
                    self.db.delete_position(ticker)
                    dust_cleaned += 1
                    continue

                self.positions[ticker] = {
                    'quantity': float(pos['quantity']),
                    'remaining_quantity': remaining_qty,
                    'entry_price': entry_price,
                    'current_price': current_price,
                    'stop_loss': float(pos['stop_loss']) if pd.notna(pos.get('stop_loss')) else entry_price * (1 - settings.STOP_LOSS_PCT),
                    'tp1': float(pos['tp1']) if pd.notna(pos.get('tp1')) else None,
                    'tp1_hit': bool(pos.get('tp1_hit', False)),
                    'tp2': float(pos['tp2']) if pd.notna(pos.get('tp2')) else None,
                    'tp2_hit': bool(pos.get('tp2_hit', False)),
                    'tp3': float(pos['tp3']) if pd.notna(pos.get('tp3')) else None,
                    'tp3_hit': bool(pos.get('tp3_hit', False)),
                    'tp1_size': float(pos['tp1_size']) if pd.notna(pos.get('tp1_size')) else 0.30,
                    'tp2_size': float(pos['tp2_size']) if pd.notna(pos.get('tp2_size')) else 0.35,
                    'tp3_size': float(pos['tp3_size']) if pd.notna(pos.get('tp3_size')) else 1.0,
                    'atr_pct': float(pos['atr_pct']) if pd.notna(pos.get('atr_pct')) else 0.05,
                    'trailing_stop_enabled': bool(pos.get('trailing_stop_enabled', False)),
                    'trailing_stop_active': bool(pos.get('trailing_stop_active', False)),
                    'trailing_activation': 0.05,
                    'trailing_atr_mult': 1.5,
                    'tier': 3,
                    'entry_features': {},
                    'trade_id': int(pos['trade_id']) if pd.notna(pos.get('trade_id')) else None,
                    # Lifecycle fields (loaded from DB)
                    'lifecycle_state': pos.get('lifecycle_state', 'INCUBATING') if pd.notna(pos.get('lifecycle_state')) else 'INCUBATING',
                    'predicted_hold_days': float(pos['predicted_hold_days']) if pd.notna(pos.get('predicted_hold_days')) else 7.0,
                    'expected_max_gain_pct': float(pos['expected_max_gain_pct']) if pd.notna(pos.get('expected_max_gain_pct')) else 0.15,
                    'last_momentum_3d': float(pos['last_momentum_3d']) if pd.notna(pos.get('last_momentum_3d')) else 0.0,
                    'exit_cooldowns': pos.get('exit_cooldowns', {}) if pd.notna(pos.get('exit_cooldowns')) else {},
                    'entry_probability': 0.30,
                }

            if dust_cleaned > 0:
                logger.success(f"🧹 Cleaned {dust_cleaned} dust positions from DB")
            logger.success(f"✅ Loaded {len(self.positions)} active positions from DB")

            # Assign emergency SL to positions that had none
            sl_fixed = 0
            for ticker, p in self.positions.items():
                if p['stop_loss'] is None or p.get('tp1') is None:
                    entry = p['entry_price']
                    p['stop_loss'] = entry * (1 - settings.STOP_LOSS_PCT)
                    p['tp1'] = entry * 1.12
                    p['tp2'] = entry * 1.25
                    p['tp3'] = entry * 1.50
                    p['tp1_size'] = 0.30
                    p['tp2_size'] = 0.35
                    p['tp3_size'] = 1.0
                    # Also persist to DB
                    self.db.upsert_position(
                        ticker=ticker,
                        quantity=p['quantity'],
                        avg_buy_price=entry,
                        current_price=p['current_price'],
                        remaining_quantity=p['remaining_quantity'],
                        stop_loss=p['stop_loss'],
                        tp1=p['tp1'], tp1_hit=p['tp1_hit'], tp1_size=p['tp1_size'],
                        tp2=p['tp2'], tp2_hit=p['tp2_hit'], tp2_size=p['tp2_size'],
                        tp3=p['tp3'], tp3_hit=p['tp3_hit'], tp3_size=p['tp3_size'],
                        atr_pct=p['atr_pct'],
                        trailing_stop_enabled=p['trailing_stop_enabled'],
                        trade_id=p['trade_id'],
                    )
                    sl_fixed += 1

            if sl_fixed > 0:
                logger.warning(f"⚠️ Assigned emergency TP/SL to {sl_fixed} unprotected positions")

        except Exception as e:
            logger.error(f"❌ Failed to load positions from DB: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _log_configuration(self):
        """Log current configuration"""
        logger.info("⚙️ BOT CONFIGURATION:")
        logger.info(f"  - Scan Interval: {self.scan_interval_hours} hours")
        logger.info(f"  - Position Monitoring: {self.position_monitoring_minutes} minutes")
        logger.info(f"  - Auto Trading: {self.auto_trading}")
        logger.info(f"  - Trading Mode: {settings.TRADING_MODE}")
        logger.info(f"  - Max Positions: {settings.MAX_POSITIONS}")
        logger.info(f"  - Prediction Threshold: {settings.PREDICTION_THRESHOLD}")
        logger.info(f"  - Position Size: {settings.POSITION_SIZE_PCT * 100}%")
        logger.info(f"  - Take Profit: {settings.TAKE_PROFIT_PCT * 100}%")
        logger.info(f"  - Stop Loss: {settings.STOP_LOSS_PCT * 100}%")

    def _save_prices_to_db(self, tickers_data: Dict[str, pd.DataFrame]):
        """
        Mantiene la BD con exactamente 1 año de datos:
        1. Borra el día más antiguo (cola)
        2. Añade el día nuevo (cabeza)
        """
        try:
            # 1. Borrar el día más antiguo
            self.db.execute_command("""
                DELETE FROM crypto_prices
                WHERE timestamp = (SELECT MIN(timestamp) FROM crypto_prices)
            """, {})
            logger.debug("🗑️ Eliminado día más antiguo de crypto_prices")

            # 2. Extraer solo el último día de cada ticker
            all_data = []
            for ticker, df in tickers_data.items():
                if df is None or len(df) == 0:
                    continue

                ticker_df = df.copy()
                ticker_df['timestamp'] = pd.to_datetime(ticker_df['timestamp'])

                # Solo el último registro (día más reciente)
                latest = ticker_df.iloc[[-1]].copy()
                latest['ticker'] = ticker
                latest = latest[['timestamp', 'ticker', 'open', 'high', 'low', 'close', 'volume']]
                all_data.append(latest)

            if not all_data:
                return

            combined_df = pd.concat(all_data, ignore_index=True)

            # 3. Insertar el día nuevo
            self.db.save_crypto_prices(combined_df)
            logger.info(f"💾 Añadido día nuevo: {len(combined_df)} tickers")

        except Exception as e:
            logger.warning(f"⚠️ Error actualizando crypto_prices: {e}")

    # ============================================
    # MAIN BOT LOOP
    # ============================================

    async def start(self):
        """Start the trading bot"""
        logger.info("🚀 Starting trading bot...")

        # Test Binance connection (retry for testnet 502s)
        MAX_ATTEMPTS = 3
        RETRY_DELAY = 60  # seconds
        connected = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self.binance.test_connectivity():
                connected = True
                break
            if attempt < MAX_ATTEMPTS:
                logger.warning(
                    f"⚠️ Binance connection attempt {attempt}/{MAX_ATTEMPTS} failed. "
                    f"Retrying in {RETRY_DELAY}s..."
                )
                await asyncio.sleep(RETRY_DELAY)

        self._binance_connected = connected
        if not connected:
            logger.warning(
                "⚠️ Binance testnet unreachable after 3 attempts — "
                "running in scan-only mode (trade execution disabled)"
            )

        # Update bot status
        self.db.update_bot_status(
            status='running',
            total_signals=0,
            buy_signals=0,
            cycle_number=0,
            last_error=None
        )

        self.is_running = True

        # Start background tasks
        tasks = [
            asyncio.create_task(self._market_scan_loop()),
            asyncio.create_task(self._position_monitoring_loop()),
            asyncio.create_task(self._binance_sync_loop()),
            asyncio.create_task(self._binance_reconnect_loop()),
        ]

        # Add auto-training loop if enabled (works for both V4 and V5)
        if getattr(settings, 'AUTO_TRAIN_ENABLED', True):
            tasks.append(asyncio.create_task(self._auto_training_loop()))
            logger.info("Auto-training loop enabled")

        logger.success("✅ Trading bot started successfully")

        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("⏸️ Keyboard interrupt received")
            await self.stop()
        except Exception as e:
            logger.error(f"❌ Bot error: {e}")
            await self.stop()

    async def stop(self):
        """Stop the trading bot"""
        logger.info("🛑 Stopping trading bot...")

        self.is_running = False

        # Update bot status
        self.db.update_bot_status(
            status='stopped',
            total_signals=0,
            buy_signals=0,
            cycle_number=self.cycle_number,
            last_error=None
        )

        logger.success("✅ Trading bot stopped")

    # ============================================
    # MARKET SCANNING (every 12 hours)
    # ============================================

    async def _market_scan_loop(self):
        """Main loop for scanning market and finding new opportunities"""
        logger.info(f"🔍 Market scan loop started (interval: {self.scan_interval_hours}h)")

        while self.is_running:
            try:
                # Run market scan
                await self._scan_market()

                # Snapshot daily performance metrics for equity curve
                try:
                    balance = self.binance.get_account_balance()
                    usdt = float(balance.get('USDT', {}).get('free', 0)) + float(balance.get('USDT', {}).get('locked', 0))
                    positions_df = self.db.get_positions()
                    pos_value = float(positions_df['total_value'].sum()) if not positions_df.empty and 'total_value' in positions_df.columns else 0.0
                    portfolio_value = usdt + pos_value
                    self.db.snapshot_daily_performance(portfolio_value)
                    logger.info(f"📊 Daily performance snapshot saved (portfolio: ${portfolio_value:.2f})")
                except Exception as snap_err:
                    logger.warning(f"⚠️ Performance snapshot failed: {snap_err}")

                # Daily health summary
                try:
                    self.health_monitor.daily_summary(self.db, self.positions)
                except Exception:
                    pass

                # Wait for next scan interval
                wait_seconds = self.scan_interval_hours * 3600
                logger.info(f"Next scan in {self.scan_interval_hours} hours...")

                # Sleep in small chunks to allow for shutdown
                for _ in range(int(wait_seconds / 60)):
                    if not self.is_running:
                        break
                    await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"❌ Error in market scan loop: {e}")
                await self.notifier.notify_error(str(e), context="Market scan loop")
                await asyncio.sleep(300)  # Wait 5 minutes on error

    async def _scan_market(self):
        """Scan market for new trading opportunities"""
        self.cycle_number += 1
        logger.info("=" * 60)
        logger.info(f"MARKET SCAN - CYCLE #{self.cycle_number}")
        logger.info("=" * 60)

        # Health check: trade rate limit
        if not self.health_monitor.check_trade_rate(self.db):
            logger.warning("Trade rate limit exceeded, skipping scan")
            await self.notifier.notify_error("Trade rate limit exceeded", context="Health Monitor")
            return

        # Check signal queue for deferred signals before scanning
        await self._process_signal_queue()

        try:
            # 1. Get macro data
            logger.info("📊 Fetching macro data...")
            macro_data = await self.macro_fetcher.get_all_macro_data()

            # 2. Get BTC data for correlation features (from production)
            logger.info("📊 Fetching BTC data from production...")
            btc_data = self.binance_data.get_historical_klines('BTCUSDT', '1d', 250)

            # 3. Fetch data for all tickers (from production)
            logger.info(f"📊 Fetching data for {len(settings.TICKERS)} tickers from production...")
            tickers_data = {}

            for i, ticker in enumerate(settings.TICKERS):
                try:
                    df = self.binance_data.get_historical_klines(ticker, '1d', 250)
                    if len(df) >= 200:
                        tickers_data[ticker] = df
                    else:
                        logger.warning(f"⚠️ Insufficient data for {ticker}: {len(df)} rows")
                except Exception as e:
                    logger.error(f"❌ Failed to fetch {ticker}: {e}")
                # Rate limit: pause every 10 tickers to stay under 6000 weight/min
                if (i + 1) % 10 == 0:
                    await asyncio.sleep(5)

            logger.info(f"✅ Fetched data for {len(tickers_data)} tickers")

            # 3b. Save latest data to database for historical analysis
            # Incluir BTCUSDT para features de correlación
            tickers_data_with_btc = {'BTCUSDT': btc_data, **tickers_data}
            self._save_prices_to_db(tickers_data_with_btc)

            # 3c. Update correlation engine with latest returns
            self.correlation_engine.update_returns(tickers_data_with_btc)

            # 3d. Detect market regime and apply adjustments
            from src.models.regime_detector import RegimeDetector
            regime_detector = RegimeDetector()
            regime_result = regime_detector.get_composite_regime(btc_data)
            regime_name = regime_result.get('regime_name', 'Sideways')
            self._current_regime = regime_result
            logger.info(f"📊 Market regime: {regime_name} (method: {regime_result.get('detection_method', 'N/A')})")

            # Apply regime-based parameter adjustments
            regime_adj = settings.REGIME_ADJUSTMENTS.get(regime_name, settings.REGIME_ADJUSTMENTS['Sideways'])
            self._regime_max_positions = regime_adj['max_positions']
            self._regime_threshold_offset = regime_adj['threshold_offset']
            logger.info(f"📊 Regime overrides: max_positions={self._regime_max_positions}, threshold_offset={self._regime_threshold_offset:+.2f}")

            # 4. Make predictions
            logger.info("🔮 Making predictions...")
            predictions_df = self.predictor.predict_multiple(
                tickers_data=tickers_data,
                btc_data=btc_data,
                macro_data=macro_data
            )

            # 5. Save all signals to database
            total_signals = len(predictions_df)
            # V5: signal_class 0=HOLD, 1=LONG, 2=SHORT
            long_signals = (predictions_df['signal_class'] == 1).sum()
            short_signals = (predictions_df['signal_class'] == 2).sum()
            buy_signals = long_signals + short_signals  # Keep for DB compat

            for _, row in predictions_df.iterrows():
                features = row['features']
                # Extract rejection_reason injected by predictor, keep features clean
                rejection_reason = None
                if isinstance(features, dict):
                    rejection_reason = features.pop('_rejection_reason', None)
                # V5 uses signal_name instead of signal_type; probability = max(p_long, p_short)
                signal_name = row.get('signal_name', 'HOLD')
                probability = max(row.get('p_long', 0.0), row.get('p_short', 0.0)) if signal_name != 'HOLD' else 0.0
                self.db.save_signal(
                    ticker=row['ticker'],
                    signal_type=signal_name,
                    probability=probability,
                    features=features,
                    rejection_reason=rejection_reason,
                )

            logger.info(
                f"📊 Signals: {long_signals} LONG / {short_signals} SHORT / "
                f"{total_signals - long_signals - short_signals} HOLD / {total_signals} total"
            )

            # 6. Update bot status (convert numpy types to Python types)
            self.db.update_bot_status(
                status='running',
                total_signals=int(total_signals),  # Convert from numpy.int64 to int
                buy_signals=int(buy_signals),      # Convert from numpy.int64 to int
                cycle_number=self.cycle_number,
                last_error=None
            )

            # 7. Get top signals (LONG + SHORT, V5 compatible)
            top_signals = self.predictor.get_top_signals(predictions_df, top_n=10)

            # 8. Execute trades if auto-trading enabled
            if self.auto_trading and len(top_signals) > 0:
                await self._execute_signals(top_signals)
            else:
                logger.info("ℹ️ Auto-trading disabled. Signals logged only.")

            self.last_scan_time = datetime.utcnow()
            logger.success(f"✅ Market scan complete - Cycle #{self.cycle_number}")

            # Healthcheck ping (if configured)
            if settings.HEALTHCHECK_PING_URL:
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=10) as hc:
                        await hc.get(settings.HEALTHCHECK_PING_URL)
                except Exception:
                    pass  # Non-critical

        except Exception as e:
            logger.error(f"❌ Market scan failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await self.notifier.notify_error(str(e), context="Market scan")

            # Update bot status with error
            self.db.update_bot_status(
                status='error',
                total_signals=0,
                buy_signals=0,
                cycle_number=self.cycle_number,
                last_error=str(e)
            )

    # ============================================
    # SMART ROTATION SYSTEM
    # ============================================

    # Binance commission: 0.1% per trade; rotation = sell + buy = 0.2%
    ROTATION_COMMISSION_PCT = 0.002

    def _calculate_signal_ev(self, probability: float, ticker: str) -> float:
        """
        Calculate expected value of a new buy signal.
        EV = P(win) * avg_gain - P(loss) * avg_loss
        """
        # Weighted TP: TP1 hit ~60%, TP2 ~25%, TP3 ~10%
        avg_gain_pct = 0.12 * 0.60 + 0.25 * 0.25 + 0.50 * 0.10  # ~0.185
        avg_loss_pct = settings.STOP_LOSS_PCT  # 0.05

        ev = probability * avg_gain_pct - (1 - probability) * avg_loss_pct
        return ev

    def _calculate_position_score(self, ticker: str, position: dict) -> float:
        """
        Score an open position's remaining value (v2 — no time decay).
        Lower score = weaker = better rotation candidate.
        Factors: current PnL (50%), remaining upside (30%), momentum (20%).
        """
        entry_price = position['entry_price']
        current_price = position.get('current_price', entry_price)

        # 1. Current unrealized PnL % — inverted for SHORT
        if position.get('position_type', 'long') == 'short':
            pnl_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0
        else:
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0

        # 2. Remaining upside to next unfilled TP
        remaining_upside = 0
        if not position.get('tp1_hit') and position.get('tp1'):
            remaining_upside = (position['tp1'] - current_price) / current_price
        elif not position.get('tp2_hit') and position.get('tp2'):
            remaining_upside = (position['tp2'] - current_price) / current_price
        elif not position.get('tp3_hit') and position.get('tp3'):
            remaining_upside = (position['tp3'] - current_price) / current_price
        else:
            remaining_upside = 0.02
        remaining_upside = max(remaining_upside, 0)

        # 3. Momentum (no time decay — age does NOT penalize)
        momentum = position.get('last_momentum_3d', 0.0)

        # Score: PnL(50%) + upside(30%) + momentum(20%)
        score = pnl_pct * 0.5 + remaining_upside * 0.3 + momentum * 0.2
        return score

    async def _attempt_smart_rotation(
        self, new_signal: pd.Series, new_price: float, portfolio_value: float
    ) -> bool:
        """
        Sell weakest ROTATABLE position if new signal has higher EV.
        Only DECAYING and ZOMBIE positions are eligible for rotation.
        Returns True if a position was sold (freeing capital + slot).
        """
        if not self.positions:
            return False

        new_ticker = new_signal['ticker']
        new_prob = new_signal['probability']

        # Calculate EV of new signal
        new_ev = self._calculate_signal_ev(new_prob, new_ticker)

        # Filter only rotatable positions (DECAYING, ZOMBIE)
        rotatable_positions = {
            t: p for t, p in self.positions.items()
            if self.lifecycle_manager.is_rotatable(p)
        }

        if not rotatable_positions:
            # No rotatable positions -> queue signal instead
            logger.info(f"Rotation rejected: no rotatable positions for {new_ticker}, queuing signal")
            self.signal_queue.enqueue(new_ticker, new_prob, new_signal.get('features', {}))
            return False

        # Find weakest rotatable position
        weakest_ticker = None
        weakest_score = float('inf')
        weakest_pos = None

        for ticker, pos in rotatable_positions.items():
            score = self._calculate_position_score(ticker, pos)
            if score < weakest_score:
                weakest_score = score
                weakest_ticker = ticker
                weakest_pos = pos

        if weakest_ticker is None:
            return False

        # More exigent threshold: new_ev must be 1.5x weakest + minimum absolute threshold
        threshold = weakest_score * settings.ROTATION_EV_MULTIPLIER + settings.ROTATION_MIN_THRESHOLD
        if new_ev <= threshold:
            logger.info(
                f"Rotation rejected: {new_ticker} EV={new_ev:.4f} vs "
                f"{weakest_ticker} threshold={threshold:.4f} (score={weakest_score:.4f} x {settings.ROTATION_EV_MULTIPLIER})"
            )
            self.signal_queue.enqueue(new_ticker, new_prob, new_signal.get('features', {}))
            return False

        # Execute rotation: sell weakest
        logger.info(
            f"SMART ROTATION: Selling {weakest_ticker} (score={weakest_score:.4f}, state={weakest_pos.get('lifecycle_state', '?')}) "
            f"for {new_ticker} (EV={new_ev:.4f})"
        )

        # Notify lifecycle of close
        self.lifecycle_manager.on_close(weakest_pos, weakest_ticker)

        await self._execute_exit(
            weakest_ticker,
            weakest_pos['remaining_quantity'],
            weakest_pos['current_price'],
            f"rotation_for_{new_ticker}"
        )

        # Clean up
        if weakest_ticker in self.positions:
            del self.positions[weakest_ticker]
        self.db.delete_position(weakest_ticker)

        logger.success(f"Rotated out {weakest_ticker} -- slot and capital freed for {new_ticker}")
        return True

    # ============================================
    # RISK MANAGEMENT: Circuit Breaker + Holding Period + Exposure
    # ============================================

    def _get_portfolio_drawdown(self) -> float:
        """Calculate current portfolio drawdown from initial capital. Returns negative pct."""
        portfolio = self.db.get_portfolio()
        initial = portfolio['initial_capital']
        current = portfolio['total_value']
        if initial <= 0:
            return 0.0
        return (current - initial) / initial  # negative = drawdown

    def _check_circuit_breaker(self) -> tuple:
        """
        Check portfolio-level circuit breaker.
        Returns (can_trade, size_multiplier, reason).
        """
        drawdown = self._get_portfolio_drawdown()

        if drawdown <= -settings.CIRCUIT_BREAKER_PAUSE_PCT:
            return False, 0.0, f"CIRCUIT BREAKER: drawdown {drawdown*100:.1f}% exceeds -{settings.CIRCUIT_BREAKER_PAUSE_PCT*100:.0f}% limit — all new entries paused"

        if drawdown <= -settings.CIRCUIT_BREAKER_REDUCE_PCT:
            return True, 0.5, f"CIRCUIT BREAKER: drawdown {drawdown*100:.1f}% — position sizes reduced 50%"

        return True, 1.0, ""

    def _check_ticker_exposure(self, ticker: str, new_usd_value: float) -> tuple:
        """Check per-ticker exposure limit. Returns (allowed, reason)."""
        portfolio = self.db.get_portfolio()
        portfolio_value = portfolio['total_value']
        if portfolio_value <= 0:
            return False, "Portfolio value is zero"

        # Calculate current exposure for this ticker
        current_exposure = 0.0
        if ticker in self.positions:
            pos = self.positions[ticker]
            current_exposure = pos.get('current_price', pos['entry_price']) * pos['remaining_quantity']

        total_exposure = current_exposure + new_usd_value
        exposure_pct = total_exposure / portfolio_value

        if exposure_pct > settings.MAX_TICKER_EXPOSURE_PCT:
            return False, f"Ticker exposure {exposure_pct*100:.1f}% exceeds {settings.MAX_TICKER_EXPOSURE_PCT*100:.0f}% limit"

        return True, ""

    async def _enforce_holding_period(self):
        """Check underwater positions and enforce max holding periods."""
        now = datetime.utcnow()
        for ticker, pos in list(self.positions.items()):
            entry_time = pos.get('entry_time')
            if not entry_time:
                continue
            if isinstance(entry_time, str):
                entry_time = datetime.fromisoformat(entry_time)

            days_held = (now - entry_time).total_seconds() / 86400

            # Fetch fresh price (fix: was using stale current_price)
            fresh_price = self.binance.get_current_price(ticker)
            if fresh_price:
                pos['current_price'] = fresh_price
            _cp = pos.get('current_price', pos['entry_price'])
            _ep = pos['entry_price']
            if pos.get('position_type', 'long') == 'short':
                pnl_pct = (_ep - _cp) / _ep if _ep > 0 else 0
            else:
                pnl_pct = (_cp - _ep) / _ep if _ep > 0 else 0

            # Only apply to underwater positions (negative PnL)
            if pnl_pct >= 0:
                continue

            if days_held >= settings.MAX_HOLD_DAYS_FORCE:
                logger.warning(f"⏰ {ticker} underwater {pnl_pct*100:.1f}% for {days_held:.0f} days — FORCE CLOSE")
                await self._execute_exit(ticker, pos['remaining_quantity'], pos['current_price'], 'time_exit_force')
                del self.positions[ticker]
                self.db.delete_position(ticker)

            elif days_held >= settings.MAX_HOLD_DAYS_REVIEW:
                # Reduce position by 50%
                reduce_qty = pos['remaining_quantity'] * 0.5
                if reduce_qty > 0:
                    logger.warning(f"⏰ {ticker} underwater {pnl_pct*100:.1f}% for {days_held:.0f} days — reducing 50%")
                    await self._execute_exit(ticker, reduce_qty, pos['current_price'], 'time_exit_partial')
                    pos['remaining_quantity'] -= reduce_qty

    async def _enforce_single_position_limit(self):
        """Force close any single position down more than MAX_LOSS without recovery."""
        for ticker, pos in list(self.positions.items()):
            current_price = pos.get('current_price', pos['entry_price'])
            _ep = pos['entry_price']
            if pos.get('position_type', 'long') == 'short':
                pnl_pct = (_ep - current_price) / _ep if _ep > 0 else 0
            else:
                pnl_pct = (current_price - _ep) / _ep if _ep > 0 else 0

            if pnl_pct <= -settings.SINGLE_POSITION_MAX_LOSS_PCT:
                logger.warning(f"🛑 {ticker} down {pnl_pct*100:.1f}% — exceeds max single loss, FORCE CLOSE")
                await self._execute_exit(ticker, pos['remaining_quantity'], current_price, 'circuit_breaker')
                del self.positions[ticker]
                self.db.delete_position(ticker)

    # ============================================
    # TRADE EXECUTION
    # ============================================

    async def _execute_signals(self, signals_df: pd.DataFrame):
        """Execute trades for buy signals"""
        logger.info(f"💰 Executing trades for {len(signals_df)} signals...")

        for _, signal in signals_df.iterrows():
            try:
                await self._execute_trade(signal)
                await asyncio.sleep(2)  # Small delay between trades
            except Exception as e:
                logger.error(f"❌ Failed to execute trade for {signal['ticker']}: {e}")

    async def _binance_reconnect_loop(self):
        """Periodically retry Binance connection when in scan-only mode."""
        RECONNECT_INTERVAL = 30 * 60  # check every 30 minutes
        while self.is_running:
            await asyncio.sleep(RECONNECT_INTERVAL)
            if self._binance_connected:
                continue
            logger.info("🔄 Attempting Binance reconnection...")
            if self.binance.test_connectivity():
                self._binance_connected = True
                logger.success("✅ Binance reconnected — trading re-enabled")
            else:
                logger.warning("⚠️ Binance still unreachable, staying in scan-only mode")

    async def _execute_trade(self, signal: pd.Series):
        """Execute a single trade"""
        ticker = signal['ticker']
        probability = signal['probability']

        if not self._binance_connected:
            logger.warning(f"⚠️ Trade skipped ({ticker}): Binance not connected (scan-only mode)")
            return

        logger.info(f"💵 Evaluating trade: {ticker} (p={probability:.4f})")

        # 0. Block duplicate: already have position in this ticker
        if ticker in self.positions:
            logger.warning(f"⚠️ Trade blocked: already holding {ticker}")
            return

        # 0b. Circuit breaker check
        can_trade, size_mult, cb_reason = self._check_circuit_breaker()
        if not can_trade:
            logger.warning(f"🚨 {cb_reason}")
            await self.notifier.notify_circuit_breaker(self.daily_loss, cb_reason)
            return
        if size_mult < 1.0:
            logger.warning(f"⚠️ {cb_reason}")

        # 0c. Sector allocation check
        sector = settings.COIN_SECTORS.get(ticker)
        if sector:
            sector_limit = settings.SECTOR_LIMITS.get(sector, 3)
            sector_count = sum(
                1 for t in self.positions
                if settings.COIN_SECTORS.get(t) == sector
            )
            if sector_count >= sector_limit:
                logger.warning(f"⚠️ Trade blocked: sector '{sector}' at capacity ({sector_count}/{sector_limit})")
                return

        # 0d. Regime max positions check
        regime_max = getattr(self, '_regime_max_positions', settings.MAX_POSITIONS)
        if len(self.positions) >= regime_max:
            logger.warning(f"⚠️ Trade blocked: regime limit {regime_max} positions reached")
            # Still allow smart rotation below

        # 1. Get current price
        current_price = self.binance.get_current_price(ticker)
        if current_price is None:
            logger.error(f"❌ Could not get price for {ticker}")
            return

        # 2. Get portfolio value from our managed portfolio (NOT Binance)
        portfolio = self.db.get_portfolio()
        portfolio_value = portfolio['total_value']
        available_balance = portfolio['available_balance']

        logger.info(f"💰 Portfolio: ${portfolio_value:.2f} total, ${available_balance:.2f} available")

        # 3. Check if we should trade
        current_positions = len(self.positions)
        rotation_attempted = False

        # V5: extract signal_class + build proba_3 array
        signal_class = signal.get('signal_class', 1)  # Default to LONG if missing (backward compat)
        signal_name = signal.get('signal_name', 'LONG')
        proba_3 = np.array([
            signal.get('p_hold', 0.0),
            signal.get('p_long', 0.0),
            signal.get('p_short', 0.0),
        ])

        should_trade, reason = self.predictor.should_trade(
            ticker=ticker,
            signal_class=signal_class,
            proba_3=proba_3,
            current_positions=current_positions,
            daily_loss=self.daily_loss,
        )

        # 3b. If blocked by max positions, attempt smart rotation
        if not should_trade and "Max positions" in reason and len(self.positions) > 0:
            rotated = await self._attempt_smart_rotation(signal, current_price, portfolio_value)
            rotation_attempted = True
            if rotated:
                # Re-check with updated position count
                portfolio = self.db.get_portfolio()
                available_balance = portfolio['available_balance']
                should_trade, reason = self.predictor.should_trade(
                    ticker=ticker,
                    signal_class=signal_class,
                    proba_3=proba_3,
                    current_positions=len(self.positions),
                    daily_loss=self.daily_loss,
                )

        if not should_trade:
            logger.warning(f"⚠️ Trade blocked: {reason}")
            return

        # 4. Calculate position size (V5 uses signal_class + proba_3)
        position_info = self.predictor.calculate_position_size(
            current_price=current_price,
            portfolio_value=portfolio_value,
            signal_class=signal_class,
            proba_3=proba_3,
            ticker=ticker,
        )

        quantity = position_info['quantity']
        usd_value = position_info['usd_value']
        confidence = position_info.get('confidence', 'exploratory')

        # 4.1b Apply correlation penalty
        held_tickers = list(self.positions.keys())
        corr_penalty = self.correlation_engine.get_correlation_penalty(ticker, held_tickers)
        if corr_penalty < 1.0:
            quantity *= corr_penalty
            usd_value *= corr_penalty
            logger.info(f"📊 Correlation penalty: {corr_penalty:.2f}x — ${usd_value:.2f}")

        # 4.2 Apply circuit breaker size reduction if active
        if size_mult < 1.0:
            quantity *= size_mult
            usd_value *= size_mult
            logger.info(f"📉 Circuit breaker: position reduced to {size_mult*100:.0f}% — ${usd_value:.2f}")

        # 4.3 Check per-ticker exposure limit
        exposure_ok, exposure_reason = self._check_ticker_exposure(ticker, usd_value)
        if not exposure_ok:
            logger.warning(f"⚠️ Trade blocked: {exposure_reason}")
            return

        # 4.5 Check if we can afford this trade
        can_afford, afford_reason = self.db.can_afford_trade(usd_value)

        # 4.6 If can't afford and rotation not yet tried, attempt it
        if not can_afford and not rotation_attempted and len(self.positions) > 0:
            rotated = await self._attempt_smart_rotation(signal, current_price, portfolio_value)
            if rotated:
                portfolio = self.db.get_portfolio()
                available_balance = portfolio['available_balance']
                can_afford, afford_reason = self.db.can_afford_trade(usd_value)

        if not can_afford:
            logger.warning(f"⚠️ Trade blocked: {afford_reason}")
            return

        # Round quantity to Binance precision
        quantity = self.binance.round_quantity(ticker, quantity)

        logger.info(f"💰 Position: {quantity} {ticker} = ${usd_value:.2f}")

        # 5. Execute order — branch on signal_class (1=LONG spot, 2=SHORT futures)
        if signal_class == 2:  # SHORT via Binance Futures
            logger.info(f"🔻 Executing SHORT (Futures): {ticker}")
            order = self.binance_futures.open_short(ticker, quantity)
            position_type = 'short'
        else:  # LONG via Spot (default, preserves original V4 flow)
            logger.info(f"🛒 Executing BUY (Spot): {ticker}")
            order = self.binance.create_market_buy_order(ticker, quantity)
            position_type = 'long'

        if order is None:
            logger.error(f"❌ Order failed for {ticker} ({signal_name})")
            return

        # 6. Get actual executed price
        executed_price = float(order.get('fills', [{}])[0].get('price', current_price))
        executed_qty = float(order['executedQty'])
        executed_value = executed_price * executed_qty

        logger.success(f"✅ {signal_name} executed: {executed_qty} {ticker} @ ${executed_price:.2f}")

        # 6.5 Deduct from available balance
        if not self.db.deduct_from_balance(executed_value, ticker):
            logger.error(f"❌ Failed to deduct ${executed_value:.2f} from balance for {ticker}")
            # Note: The trade was already executed on Binance, so we continue but log the error

        # 7. Calculate DYNAMIC TP/SL levels using risk manager
        # Get macro data for market conditions
        macro_data_dict = {
            'fear_greed': signal.get('features', {}).get('fear_greed_value', 50),
            'vix': signal.get('features', {}).get('vix', 20)
        }

        tp_sl = self.risk_manager.calculate_dynamic_tp_sl(
            entry_price=executed_price,
            ticker=ticker,
            features=signal.get('features', {}),
            market_conditions=macro_data_dict,
            confidence=confidence,
        )

        # 8. TP/SL levels — for SHORT, invert the percentages
        if position_type == 'short':
            # SHORT: TP is below entry, SL is above entry
            tp1_price = executed_price * (1 - tp_sl['tp1_pct'])
            tp2_price = executed_price * (1 - tp_sl['tp2_pct'])
            tp3_price = executed_price * (1 - tp_sl['tp3_pct'])
            sl_price_raw = executed_price * (1 + tp_sl['stop_loss_pct'])
            logger.info(
                f"🎯 SHORT TP/SL: SL=${sl_price_raw:.4f} (+{tp_sl['stop_loss_pct']*100:.1f}%) | "
                f"TP1=${tp1_price:.4f} (-{tp_sl['tp1_pct']*100:.1f}%) | "
                f"TP2=${tp2_price:.4f} (-{tp_sl['tp2_pct']*100:.1f}%) | "
                f"TP3=${tp3_price:.4f} (-{tp_sl['tp3_pct']*100:.1f}%)"
            )
            # Override tp_sl dict with correct SHORT levels
            tp_sl = {
                **tp_sl,
                'tp1': tp1_price,
                'tp2': tp2_price,
                'tp3': tp3_price,
                'stop_loss': sl_price_raw,
            }
            # SHORT: SL management handled by monitoring loop (Futures doesn't use Spot OCO)
            logger.info(f"ℹ️ SHORT position: SL/TP will be managed via monitoring loop (no Spot OCO)")
        else:
            # LONG: original OCO + SL flow
            logger.info(
                f"🎯 Dynamic TP/SL: SL=${tp_sl['stop_loss']:.4f} (-{tp_sl['stop_loss_pct']*100:.1f}%) | "
                f"TP1=${tp_sl['tp1']:.4f} (+{tp_sl['tp1_pct']*100:.1f}%) | "
                f"TP2=${tp_sl['tp2']:.4f} (+{tp_sl['tp2_pct']*100:.1f}%) | "
                f"TP3=${tp_sl['tp3']:.4f} (+{tp_sl['tp3_pct']*100:.1f}%)"
            )

            # Place OCO for first TP level (30% of position)
            oco_quantity = executed_qty * tp_sl['tp1_size']
            oco_quantity = self.binance.round_quantity(ticker, oco_quantity)

            # Round prices to avoid Binance precision errors
            tp_price = self.binance.round_price(ticker, tp_sl['tp1'])
            sl_price = self.binance.round_price(ticker, tp_sl['stop_loss'])
            sl_limit_price = self.binance.round_price(ticker, tp_sl['stop_loss'] * 0.99)

            oco_order = self.binance.create_oco_order(
                symbol=ticker,
                quantity=oco_quantity,
                price=tp_price,
                stop_price=sl_price,
                stop_limit_price=sl_limit_price
            )

            if oco_order:
                logger.success(f"✅ OCO order placed for {ticker} (TP1: 30% position)")

            # 8b. Place STOP_LOSS_LIMIT for remaining 70% (server-side protection)
            remaining_qty = executed_qty - oco_quantity
            remaining_qty = self.binance.round_quantity(ticker, remaining_qty)
            if remaining_qty > 0:
                sl_order = self.binance.create_stop_limit_order(
                    symbol=ticker,
                    side='SELL',
                    quantity=remaining_qty,
                    stop_price=sl_price,
                    limit_price=sl_limit_price,
                )
                if sl_order:
                    logger.success(f"✅ SL order placed for {ticker} remaining 70% ({remaining_qty})")

        # 9. Log trade to database
        # Get signal_id from the most recent signal for this ticker
        recent_signals = self.db.get_recent_signals(limit=100, min_probability=0.0)
        signal_id = None
        for _, sig in recent_signals.iterrows():
            if sig['ticker'] == ticker:
                signal_id = int(sig['id'])
                break

        trade_id = self.db.save_trade(
            signal_id=signal_id,
            ticker=ticker,
            action=signal_name,  # 'LONG' or 'SHORT' (V5), replaces always-'BUY'
            quantity=executed_qty,
            price=executed_price,
            total_value=executed_value,
            status='executed',
            probability=probability  # Save model confidence
        )

        # Update positions table in database (full state)
        self.db.upsert_position(
            ticker=ticker,
            quantity=executed_qty,
            avg_buy_price=executed_price,
            current_price=executed_price,
            remaining_quantity=executed_qty,
            stop_loss=tp_sl['stop_loss'],
            tp1=tp_sl['tp1'],
            tp1_hit=False,
            tp1_size=tp_sl['tp1_size'],
            tp2=tp_sl['tp2'],
            tp2_hit=False,
            tp2_size=tp_sl['tp2_size'],
            tp3=tp_sl['tp3'],
            tp3_hit=False,
            tp3_size=tp_sl['tp3_size'],
            atr_pct=tp_sl['atr_pct'],
            trailing_stop_enabled=tp_sl['trailing_stop_enabled'],
            trade_id=trade_id,
        )

        # 10. Update position tracking with dynamic TP/SL data
        self.positions[ticker] = {
            'quantity': executed_qty,
            'remaining_quantity': executed_qty,
            'entry_price': executed_price,
            'current_price': executed_price,
            'stop_loss': tp_sl['stop_loss'],
            'tp1': tp_sl['tp1'],
            'tp1_hit': False,
            'tp2': tp_sl['tp2'],
            'tp2_hit': False,
            'tp3': tp_sl['tp3'],
            'tp3_hit': False,
            'tp1_size': tp_sl['tp1_size'],
            'tp2_size': tp_sl['tp2_size'],
            'tp3_size': tp_sl['tp3_size'],
            'atr_pct': tp_sl['atr_pct'],
            'trailing_stop_enabled': tp_sl['trailing_stop_enabled'],
            'trailing_activation': tp_sl.get('trailing_activation', 0.05),
            'trailing_atr_mult': tp_sl.get('trailing_atr_mult', 1.5),
            'tier': tp_sl.get('tier', 3),
            'trailing_stop_active': False,
            'entry_features': signal.get('features', {}),
            'trade_id': trade_id,
            'entry_time': datetime.utcnow(),
            'entry_probability': probability,
            'position_type': position_type,  # 'long' or 'short'
        }

        # 10b. Initialize lifecycle state
        self.lifecycle_manager.on_entry(
            self.positions[ticker], ticker, probability, tp_sl.get('tier', 3)
        )
        # Remove ticker from signal queue if it was queued
        self.signal_queue.remove_ticker(ticker)

        logger.success(f"✅ Trade complete: {ticker} position opened with dynamic TP/SL")

        # 11. Telegram notification
        await self.notifier.notify_trade(
            action=signal_name, ticker=ticker, price=executed_price,
            quantity=executed_qty, usd_value=executed_value,
            confidence=confidence, probability=probability,
        )

    # ============================================
    # POSITION MONITORING (every 5 minutes)
    # ============================================

    async def _position_monitoring_loop(self):
        """Monitor open positions and check TP/SL"""
        logger.info(f"👀 Position monitoring started (interval: {self.position_monitoring_minutes}min)")

        while self.is_running:
            try:
                if len(self.positions) > 0:
                    await self._monitor_positions()

                # Wait for next monitoring interval
                await asyncio.sleep(self.position_monitoring_minutes * 60)

            except Exception as e:
                logger.error(f"❌ Error in position monitoring: {e}")
                await asyncio.sleep(60)

    async def _monitor_positions(self):
        """Check all open positions with intelligent exit strategy"""
        logger.debug(f"👀 Monitoring {len(self.positions)} positions...")

        # Pre-check: enforce risk limits before individual position checks
        await self._enforce_single_position_limit()
        await self._enforce_holding_period()

        # Pre-fetch shared data ONCE (avoid per-position API spam)
        try:
            btc_data_shared = self.binance_data.get_historical_klines('BTCUSDT', '1d', 250)
        except Exception:
            btc_data_shared = None
        try:
            macro_data_shared = await self.macro_fetcher.get_all_macro_data()
        except Exception:
            macro_data_shared = {}

        from src.data.features_v4 import FeatureEngineerV4
        feature_engineer_shared = FeatureEngineerV4()

        for ticker, position in list(self.positions.items()):
            try:
                # 1. Get current price
                current_price = self.binance.get_current_price(ticker)
                if current_price is None:
                    continue

                # Update position
                position['current_price'] = current_price

                # 2. Calculate P&L — inverted for SHORT positions
                pos_type = position.get('position_type', 'long')
                entry_price_pos = position['entry_price']
                if pos_type == 'short':
                    pnl_pct_raw = (entry_price_pos - current_price) / entry_price_pos
                else:
                    pnl_pct_raw = (current_price - entry_price_pos) / entry_price_pos
                pnl = pnl_pct_raw * position['remaining_quantity'] * entry_price_pos
                pnl_pct = pnl_pct_raw * 100

                logger.debug(f"  {ticker} ({pos_type}): ${current_price:.2f} | P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")

                # 3. Get current market features for intelligent exit
                try:
                    df = self.binance_data.get_historical_klines(ticker, '1d', 250)
                    await asyncio.sleep(0.5)  # Rate limit: avoid Binance ban

                    df_with_features = feature_engineer_shared.calculate_features(df, btc_data_shared, macro_data_shared)
                    feature_vector = feature_engineer_shared.get_feature_vector(df_with_features)

                    if len(feature_vector) > 0:
                        current_features = feature_vector.iloc[-1].to_dict()
                    else:
                        current_features = {}

                except Exception as e:
                    logger.warning(f"⚠️ Could not get current features for {ticker}: {e}")
                    current_features = {}

                # 4. Build tp_levels dict (used by both trailing stop and exit logic)
                tp_levels = {
                    'tp1': position['tp1'],
                    'tp1_hit': position['tp1_hit'],
                    'tp1_size': position['tp1_size'],
                    'tp2': position['tp2'],
                    'tp2_hit': position['tp2_hit'],
                    'tp2_size': position['tp2_size'],
                    'tp3': position['tp3'],
                    'tp3_hit': position['tp3_hit'],
                    'tp3_size': position['tp3_size'],
                    # Tier-aware trailing params (from position or defaults)
                    'trailing_activation': position.get('trailing_activation', 0.05),
                    'trailing_atr_mult': position.get('trailing_atr_mult', 1.5),
                }

                # 5. Apply Trailing Stop Loss (tier-aware)
                if position['trailing_stop_enabled']:
                    new_stop_loss, activated = self.risk_manager.calculate_trailing_stop(
                        entry_price=position['entry_price'],
                        current_price=current_price,
                        current_stop_loss=position['stop_loss'],
                        atr_pct=position.get('atr_pct', 0.03),
                        tp_levels=tp_levels,
                    )

                    if activated:
                        old_sl = position['stop_loss']
                        position['stop_loss'] = new_stop_loss
                        position['trailing_stop_active'] = True
                        logger.info(f"Trailing SL {ticker}: ${old_sl:.4f} -> ${new_stop_loss:.4f}")

                # 5b. Update momentum and lifecycle state
                position['last_momentum_3d'] = current_features.get('momentum_3d', 0.0)
                lifecycle_state = self.lifecycle_manager.update_state(position, ticker)

                # 5c. Force close zombies past MAX_ZOMBIE_DAYS
                if self.lifecycle_manager.should_force_close(position):
                    logger.warning(f"FORCE CLOSE zombie: {ticker}")
                    self.lifecycle_manager.on_close(position, ticker)
                    await self._execute_exit(ticker, position['remaining_quantity'], current_price, 'zombie_force_close')
                    del self.positions[ticker]
                    self.db.delete_position(ticker)
                    continue

                exit_decision = self.risk_manager.check_exit_conditions(
                    ticker=ticker,
                    entry_price=position['entry_price'],
                    current_price=current_price,
                    position_size=position['remaining_quantity'],
                    tp_levels=tp_levels,
                    stop_loss=position['stop_loss'],
                    features=current_features,
                    entry_features=position.get('entry_features', {}),
                    lifecycle_state=lifecycle_state,
                )

                # 6. Execute exit if needed
                if exit_decision['action'] == 'exit_full':
                    logger.warning(f"{ticker} FULL EXIT: {exit_decision['reason']}")
                    self.lifecycle_manager.on_close(position, ticker)
                    await self._execute_exit(ticker, position['remaining_quantity'], current_price, exit_decision['reason'])
                    del self.positions[ticker]
                    self.db.delete_position(ticker)
                    continue

                elif exit_decision['action'] == 'exit_partial':
                    exit_qty = position['remaining_quantity'] * exit_decision['quantity']
                    logger.info(f"{ticker} PARTIAL EXIT: {exit_decision['reason']} ({exit_decision['quantity']*100:.0f}%)")
                    await self._execute_exit(ticker, exit_qty, current_price, exit_decision['reason'])

                    position['remaining_quantity'] = max(0.0, position['remaining_quantity'] - exit_qty)

                    # Mark TP level as hit if applicable
                    if 'level' in exit_decision:
                        level_key = f"{exit_decision['level'].lower()}_hit"
                        position[level_key] = True

                elif exit_decision['action'] == 'tighten_trailing':
                    # Check cooldown before tightening
                    cooldown_key = exit_decision.get('cooldown_key', exit_decision['reason'])
                    cooldowns = position.get('exit_cooldowns', {})
                    last_tighten = cooldowns.get(cooldown_key)

                    can_tighten = True
                    if last_tighten:
                        if isinstance(last_tighten, str):
                            last_tighten = datetime.fromisoformat(last_tighten)
                        hours_since = (datetime.utcnow() - last_tighten).total_seconds() / 3600
                        if hours_since < settings.EXIT_COOLDOWN_HOURS:
                            can_tighten = False

                    if can_tighten:
                        factor = exit_decision.get('tighten_factor', 0.5)
                        old_sl = position['stop_loss']
                        distance = current_price - old_sl
                        if distance > 0:
                            new_distance = distance * factor
                            new_sl = current_price - new_distance
                            position['stop_loss'] = max(old_sl, new_sl)
                            # Record cooldown
                            if 'exit_cooldowns' not in position:
                                position['exit_cooldowns'] = {}
                            position['exit_cooldowns'][cooldown_key] = datetime.utcnow().isoformat()
                            logger.info(
                                f"Trailing tightened for {ticker}: SL ${old_sl:.4f} -> ${position['stop_loss']:.4f} "
                                f"(reason={exit_decision['reason']})"
                            )

                # 7. Check basic TP/SL (in case OCO failed / for SHORT monitoring)
                pos_type_mon = position.get('position_type', 'long')
                sl_triggered = False
                if pos_type_mon == 'short':
                    # SHORT SL: price rose above stop-loss level
                    if current_price >= position['stop_loss']:
                        logger.warning(f"🛑 {ticker} SHORT STOP LOSS hit: ${current_price:.2f} >= ${position['stop_loss']:.2f}")
                        sl_triggered = True
                    # SHORT TP1: price fell below tp1
                    elif not position.get('tp1_hit') and position.get('tp1') and current_price <= position['tp1']:
                        logger.info(f"🎯 {ticker} SHORT TP1 hit: ${current_price:.2f} <= ${position['tp1']:.2f}")
                        exit_qty = position['remaining_quantity'] * position.get('tp1_size', 0.30)
                        await self._execute_exit(ticker, exit_qty, current_price, 'tp1_short')
                        position['remaining_quantity'] = max(0.0, position['remaining_quantity'] - exit_qty)
                        position['tp1_hit'] = True
                else:
                    # LONG SL: price fell below stop-loss level
                    if current_price <= position['stop_loss']:
                        logger.warning(f"🛑 {ticker} STOP LOSS hit: ${current_price:.2f} <= ${position['stop_loss']:.2f}")
                        sl_triggered = True

                if sl_triggered:
                    await self._execute_exit(ticker, position['remaining_quantity'], current_price, 'stop_loss')
                    del self.positions[ticker]
                    self.db.delete_position(ticker)
                    continue

                # 8. Sync full position state to database (including lifecycle)
                import json as _json
                self.db.execute_command(
                    """
                    UPDATE positions
                    SET current_price = :current_price,
                        total_value = :total_value,
                        pnl = :pnl,
                        pnl_percentage = :pnl_pct,
                        remaining_quantity = :remaining_quantity,
                        stop_loss = :stop_loss,
                        tp1_hit = :tp1_hit,
                        tp2_hit = :tp2_hit,
                        tp3_hit = :tp3_hit,
                        trailing_stop_active = :trailing_stop_active,
                        lifecycle_state = :lifecycle_state,
                        predicted_hold_days = :predicted_hold_days,
                        last_momentum_3d = :last_momentum_3d,
                        exit_cooldowns = :exit_cooldowns,
                        last_update = :last_update
                    WHERE ticker = :ticker
                    """,
                    {
                        'ticker': ticker,
                        'current_price': current_price,
                        'total_value': current_price * position['remaining_quantity'],
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'remaining_quantity': position['remaining_quantity'],
                        'stop_loss': position['stop_loss'],
                        'tp1_hit': position.get('tp1_hit', False),
                        'tp2_hit': position.get('tp2_hit', False),
                        'tp3_hit': position.get('tp3_hit', False),
                        'trailing_stop_active': position.get('trailing_stop_active', False),
                        'lifecycle_state': position.get('lifecycle_state', 'INCUBATING'),
                        'predicted_hold_days': position.get('predicted_hold_days', 7.0),
                        'last_momentum_3d': position.get('last_momentum_3d', 0.0),
                        'exit_cooldowns': _json.dumps(position.get('exit_cooldowns', {})),
                        'last_update': datetime.utcnow()
                    }
                )

            except Exception as e:
                logger.error(f"❌ Error monitoring {ticker}: {e}")
                import traceback
                logger.error(traceback.format_exc())

    async def _execute_exit(self, ticker: str, quantity: float, price: float, reason: str):
        """Execute exit (sell) for a position or partial position"""
        try:
            # Guard: skip dust positions that are too small to trade
            if self.binance.is_dust_position(ticker, abs(quantity), price):
                logger.info(f"🧹 Skipping dust sell for {ticker} (qty={quantity:.2e}, ~${abs(quantity)*price:.4f})")
                # Clean up: delete position entirely to avoid zombie PnL
                self.db.delete_position(ticker)
                return

            # Determine position type (default to 'long' for backward compat)
            pos_type = 'long'
            if ticker in self.positions:
                pos_type = self.positions[ticker].get('position_type', 'long')

            logger.info(f"💰 Executing EXIT ({pos_type.upper()}): {quantity} {ticker} @ ${price:.4f}")

            # Get entry price for P&L calculation
            entry_price = price  # Default
            if ticker in self.positions:
                entry_price = self.positions[ticker].get('entry_price', price)

            # Cancel all open spot orders before exit (only relevant for LONG)
            if pos_type == 'long':
                cancelled = self.binance.cancel_all_open_orders(ticker)
                if cancelled > 0:
                    logger.info(f"🗑️ Cancelled {cancelled} open orders for {ticker}")

            # Round quantity
            quantity = self.binance.round_quantity(ticker, quantity)

            # Final check: rounded quantity could be 0
            if quantity <= 0:
                logger.info(f"🧹 Rounded qty is 0 for {ticker}, deleting position")
                self.db.delete_position(ticker)
                return

            # Execute market close — Spot sell for LONG, Futures close_short for SHORT
            if pos_type == 'short':
                order = self.binance_futures.close_short(ticker, quantity)
            else:
                order = self.binance.create_market_sell_order(ticker, quantity)

            if order:
                executed_price = float(order.get('fills', [{}])[0].get('price', price))
                executed_qty = float(order['executedQty'])
                executed_value = executed_price * executed_qty

                # Calculate P&L — inverted for SHORT (profit when price falls)
                if pos_type == 'short':
                    sale_pnl = (entry_price - executed_price) * executed_qty
                else:
                    sale_pnl = (executed_price - entry_price) * executed_qty

                logger.success(f"✅ EXIT executed ({pos_type.upper()}): {executed_qty} {ticker} @ ${executed_price:.2f} | P&L: ${sale_pnl:+.2f} | Reason: {reason}")

                # Telegram notification
                await self.notifier.notify_trade(
                    action="SELL", ticker=ticker, price=executed_price,
                    quantity=executed_qty, usd_value=executed_value,
                    pnl=sale_pnl, reason=reason,
                )

                # Add proceeds to available balance
                self.db.add_to_balance(
                    amount=executed_value,
                    pnl=sale_pnl,
                    ticker=ticker
                )

                # Log to database with exit reason
                self.db.save_trade(
                    signal_id=None,
                    ticker=ticker,
                    action='SELL',
                    quantity=executed_qty,
                    price=executed_price,
                    total_value=executed_value,
                    status='executed',
                    probability=None,
                    exit_reason=reason.upper() if reason else None
                )

        except Exception as e:
            logger.error(f"❌ Exit failed for {ticker}: {e}")

    # ============================================
    # BINANCE SYNC (every 60 minutes)
    # ============================================

    async def _binance_sync_loop(self):
        """Sync positions with Binance every 60 minutes"""
        logger.info("🔄 Binance sync started (interval: 60min)")

        while self.is_running:
            try:
                await self._sync_positions_with_binance()

                # Wait for next sync interval (60 minutes)
                await asyncio.sleep(60 * 60)

            except Exception as e:
                logger.error(f"❌ Error in Binance sync: {e}")
                await asyncio.sleep(60)

    async def _sync_positions_with_binance(self):
        """Fetch real positions from Binance and update database (optimized)"""
        try:
            logger.info("🔄 Syncing positions with Binance...")

            # Get positions that the bot has opened (from DB)
            db_positions = self.db.get_positions()

            if len(db_positions) == 0:
                logger.info("📊 No bot positions to sync")
                return

            # Get all balances from Binance ONCE
            logger.debug("📊 Fetching account balances from Binance...")
            balances = self.binance.get_account_balance()

            # Get all tickers we need prices for
            tickers = [row['ticker'] for _, row in db_positions.iterrows()]

            # Fetch ALL prices in ONE API call
            all_prices = self.binance.get_multiple_prices(tickers)

            # Update each position
            synced_count = 0
            for _, db_pos in db_positions.iterrows():
                ticker = db_pos['ticker']

                try:
                    # Get current price from batch
                    current_price = all_prices.get(ticker)
                    if current_price is None:
                        logger.warning(f"⚠️ Could not get price for {ticker}")
                        continue

                    # Check if position still exists in Binance balances
                    asset = ticker.replace('USDT', '')

                    if asset not in balances or balances[asset]['total'] < 0.0001:
                        # Position was closed outside the bot
                        self.db.delete_position(ticker)
                        logger.info(f"🗑️ Removed closed position: {ticker}")
                        continue

                    # Get actual quantity from Binance — Binance is the source of truth
                    actual_quantity = balances[asset]['total']

                    # remaining_qty = min(Binance actual, DB value)
                    # Binance can only go DOWN (OCO/SL partial fills reduce actual holdings)
                    # The DB value is preserved for partial exits the bot executed explicitly.
                    # If they diverge, Binance wins — it reflects reality.
                    db_remaining = float(db_pos['remaining_quantity']) if (
                        'remaining_quantity' in db_pos
                        and pd.notna(db_pos['remaining_quantity'])
                        and float(db_pos.get('remaining_quantity', 0)) > 0
                    ) else actual_quantity
                    remaining_qty = min(actual_quantity, db_remaining)

                    avg_price = float(db_pos['avg_buy_price'])
                    total_val = remaining_qty * current_price
                    pnl = (current_price - avg_price) * remaining_qty
                    pnl_pct = ((current_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0

                    self.db.execute_command(
                        """UPDATE positions
                           SET quantity = :qty,
                               remaining_quantity = :remaining_qty,
                               current_price = :price,
                               total_value = :total_val, pnl = :pnl,
                               pnl_percentage = :pnl_pct, last_update = NOW()
                           WHERE ticker = :ticker""",
                        {
                            'qty': actual_quantity,
                            'remaining_qty': remaining_qty,
                            'price': current_price,
                            'total_val': total_val,
                            'pnl': pnl,
                            'pnl_pct': pnl_pct,
                            'ticker': ticker,
                        }
                    )

                    logger.debug(f"  ✅ Synced {ticker}: {actual_quantity:.4f} @ ${current_price:.4f}")
                    synced_count += 1

                except Exception as e:
                    logger.error(f"❌ Failed to sync {ticker}: {e}")
                    continue

            logger.success(f"✅ Synced {synced_count} bot positions with Binance")

        except Exception as e:
            logger.error(f"❌ Failed to sync with Binance: {e}")

    # ============================================
    # SIGNAL QUEUE PROCESSING
    # ============================================

    async def _process_signal_queue(self):
        """Process deferred signals from the queue if slots are available."""
        if not self.signal_queue.has_signals():
            return

        current_positions = len(self.positions)
        regime_max = getattr(self, '_regime_max_positions', settings.MAX_POSITIONS)

        if current_positions >= regime_max:
            return

        # Process up to (available slots) signals
        available_slots = regime_max - current_positions
        processed = 0

        while available_slots > 0 and self.signal_queue.has_signals():
            signal_data = self.signal_queue.dequeue_best()
            if signal_data is None:
                break

            ticker = signal_data['ticker']
            if ticker in self.positions:
                continue

            # Create a signal-like Series for _execute_trade
            signal_series = pd.Series({
                'ticker': ticker,
                'probability': signal_data['probability'],
                'features': signal_data.get('features', {}),
                'signal_type': 'BUY',
                'prediction': 1,
            })

            try:
                await self._execute_trade(signal_series)
                processed += 1
                available_slots -= 1
            except Exception as e:
                logger.error(f"Failed to execute queued signal {ticker}: {e}")

        if processed > 0:
            logger.info(f"Queued signal executed: {processed} signals processed from queue")

    # ============================================
    # AUTO-TRAINING LOOP (weekly, DB-aware)
    # ============================================

    async def _auto_training_loop(self):
        """Periodically retrain V4 model. Uses DB to survive restarts."""
        interval_days = getattr(settings, 'AUTO_TRAIN_INTERVAL_DAYS', 7)

        logger.info(f"Auto-training loop started (interval: {interval_days}d)")

        # Wait 5 min warmup
        await asyncio.sleep(300)

        while self.is_running:
            try:
                # Determine trainer version from active predictor
                use_v5 = hasattr(self.predictor, '_load_global_model')
                mv_filter = "V5" if use_v5 else "V4"

                # Check DB for last training date (survives restarts)
                last_trained = self.db.get_last_training_date(model_version=mv_filter)
                if last_trained:
                    if isinstance(last_trained, str):
                        last_trained = datetime.fromisoformat(last_trained)
                    if last_trained.tzinfo is not None:
                        now = datetime.now(timezone.utc)
                    else:
                        now = datetime.utcnow()
                    days_since = (now - last_trained).total_seconds() / 86400
                    if days_since < interval_days:
                        # V5: bypass interval if model is missing from disk (e.g. after redeploy)
                        if use_v5 and getattr(self.predictor, '_global_model', None) is None:
                            logger.info(
                                f"[V5] Global model missing despite recent training ({days_since:.1f}d ago) "
                                "— triggering immediate re-training"
                            )
                        else:
                            logger.info(f"Auto-training: last trained {days_since:.1f}d ago, next in {interval_days - days_since:.1f}d")
                            await asyncio.sleep(3600)  # Check again in 1h
                            continue

                if use_v5:
                    from src.models.auto_trainer_v5 import AutoTrainerV5
                    trainer = AutoTrainerV5()
                    logger.info("Starting V5 auto-training cycle (global model)...")
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, trainer.train_global_model)
                    model_version = "V5"
                    if result is not None and hasattr(self.predictor, '_load_global_model'):
                        self.predictor._load_global_model()
                        logger.success("V5 global model reloaded after training")
                else:
                    from src.models.auto_trainer import AutoTrainer
                    trainer = AutoTrainer()
                    logger.info("Starting V4 auto-training cycle...")
                    result = await trainer.run_auto_training()
                    model_version = "V4"
                    if result and result.get("promoted"):
                        if hasattr(self.predictor, 'request_reload'):
                            self.predictor.request_reload()
                            logger.success(f"Model v{result.get('version')} promoted")

                # Log training event to DB
                self.db.save_training_log(
                    model_version=model_version,
                    metrics=result or {}
                )

                logger.info(f"Auto-training result: {(result or {}).get('status', 'completed')}")

            except Exception as e:
                logger.error(f"Auto-training loop error: {e}")
                import traceback
                logger.error(traceback.format_exc())

            # Wait before next check
            await asyncio.sleep(3600)

    # ============================================
    # UTILITIES
    # ============================================

    def get_status(self) -> Dict:
        """Get current bot status"""
        return {
            'is_running': self.is_running,
            'cycle_number': self.cycle_number,
            'positions_count': len(self.positions),
            'daily_loss': self.daily_loss,
            'last_scan_time': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'auto_trading': self.auto_trading
        }


# ============================================
# STANDALONE EXECUTION
# ============================================

async def main():
    """Main entry point"""
    # Setup logging
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        settings.LOG_FILE,
        rotation="1 day",
        retention="30 days",
        level="DEBUG"
    )

    # Create and start bot
    bot = TradingBot()
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
