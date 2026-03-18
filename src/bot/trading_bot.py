"""
CRYPTONITA TRADING BOT V3
==========================
Main trading bot implementation with:
- Market scanning every 12 hours
- Position monitoring every 5 minutes
- Automatic trade execution
- Risk management with dynamic TP/SL
- Full position persistence and recovery
- Daily loss tracking
"""

import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone, date, timedelta
from typing import Dict, List, Optional, Tuple
from loguru import logger
import pandas as pd

from config import settings
from src.services.binance_service import BinanceService
from src.services.binance_data_service import BinanceDataService
from src.data.storage.db_manager import DatabaseManager
from src.data.macro_data import MacroDataFetcher
from src.trading.dynamic_risk_manager import DynamicRiskManager


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TradingBot:
    """Main trading bot for automated cryptocurrency trading"""

    def __init__(self, config_path: str = "bot_config.json"):
        logger.info("=" * 60)
        logger.info("INITIALIZING CRYPTONITA TRADING BOT V3")
        logger.info("=" * 60)

        # Load configuration
        self.config = self._load_config(config_path)

        # Initialize services
        self.binance = BinanceService()
        self.binance_data = BinanceDataService()

        # Select predictor based on V4 flag
        if getattr(settings, 'USE_V4_MODEL', False):
            from src.models.predictor_v4 import TradingPredictorV4
            self.predictor = TradingPredictorV4()
            logger.info("Using V4 Ensemble Predictor")
        else:
            from src.models.predictor import TradingPredictor
            self.predictor = TradingPredictor()
            logger.info("Using V3 XGBoost Predictor")

        self.db = DatabaseManager(settings.get_database_url())
        self.macro_fetcher = MacroDataFetcher()
        self.risk_manager = DynamicRiskManager()

        logger.info("Using Binance PRODUCTION for data, TESTNET for trading")

        # Bot state
        self.is_running = False
        self.cycle_number = 0
        self.last_scan_time = None

        # Daily loss tracking
        self.daily_loss = 0.0
        self._daily_loss_date = _utcnow().date()

        # Positions - will be loaded from DB on start
        self.positions: Dict[str, Dict] = {}

        # Trading parameters from config
        self.scan_interval_hours = self.config['trading']['scan_interval_hours']
        self.position_monitoring_minutes = self.config['trading']['position_monitoring_minutes']
        self.auto_trading = self.config['trading']['auto_trading_enabled']

        logger.success("Trading Bot initialized successfully")
        self._log_configuration()

    def _load_config(self, config_path: str) -> dict:
        """Load bot configuration"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Bot config loaded from {config_path}")
            return config
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return self._default_config()

    def _default_config(self) -> dict:
        return {
            "trading": {
                "scan_interval_hours": 12,
                "position_monitoring_minutes": 5,
                "auto_trading_enabled": True,
            },
            "risk_management": {
                "max_positions": 10,
                "max_daily_loss_usd": 200
            }
        }

    def _log_configuration(self):
        logger.info("BOT CONFIGURATION:")
        logger.info(f"  Scan Interval: {self.scan_interval_hours}h")
        logger.info(f"  Position Monitoring: {self.position_monitoring_minutes}min")
        logger.info(f"  Auto Trading: {self.auto_trading}")
        logger.info(f"  Trading Mode: {settings.TRADING_MODE}")
        logger.info(f"  Max Positions: {settings.MAX_POSITIONS}")
        logger.info(f"  Threshold: {settings.PREDICTION_THRESHOLD}")
        logger.info(f"  Position Size: {settings.POSITION_SIZE_PCT * 100}%")
        logger.info(f"  Max Daily Loss: ${settings.MAX_DAILY_LOSS_USD}")

    # ============================================
    # DAILY LOSS TRACKING
    # ============================================

    def _check_daily_reset(self):
        """Reset daily loss counter if a new day has started"""
        today = _utcnow().date()
        if today != self._daily_loss_date:
            logger.info(f"New trading day. Previous day loss: ${self.daily_loss:.2f}")
            self.daily_loss = 0.0
            self._daily_loss_date = today

    def _record_loss(self, loss_amount: float):
        """Record a loss (positive number = loss amount)"""
        if loss_amount > 0:
            self.daily_loss += loss_amount
            logger.warning(f"Daily loss updated: ${self.daily_loss:.2f} / ${settings.MAX_DAILY_LOSS_USD}")

    def _can_trade(self) -> bool:
        """Check if daily loss limit allows trading"""
        self._check_daily_reset()
        if self.daily_loss >= settings.MAX_DAILY_LOSS_USD:
            logger.warning(f"Daily loss limit reached: ${self.daily_loss:.2f} >= ${settings.MAX_DAILY_LOSS_USD}")
            return False
        return True

    # ============================================
    # POSITION RECOVERY
    # ============================================

    def _recover_positions(self):
        """Load open positions from database on startup"""
        try:
            recovered = self.db.get_all_positions_as_dict()
            if recovered:
                self.positions = recovered
                logger.success(f"Recovered {len(recovered)} positions from database: {list(recovered.keys())}")
            else:
                logger.info("No open positions to recover")
        except Exception as e:
            logger.error(f"Failed to recover positions: {e}")
            self.positions = {}

    # ============================================
    # MAIN BOT LOOP
    # ============================================

    async def start(self):
        """Start the trading bot"""
        logger.info("Starting trading bot...")

        # Test Binance connection
        if not self.binance.test_connectivity():
            logger.error("Failed to connect to Binance. Aborting.")
            return

        # Recover positions from DB
        self._recover_positions()

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
            asyncio.create_task(self._position_monitoring_loop())
        ]

        logger.success("Trading bot started successfully")

        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            await self.stop()
        except Exception as e:
            logger.error(f"Bot error: {e}")
            await self.stop()

    async def stop(self):
        """Stop the trading bot gracefully"""
        logger.info("Stopping trading bot...")
        self.is_running = False

        self.db.update_bot_status(
            status='stopped',
            total_signals=0,
            buy_signals=0,
            cycle_number=self.cycle_number,
            last_error=None
        )

        logger.success("Trading bot stopped")

    # ============================================
    # MARKET SCANNING (every 12 hours)
    # ============================================

    def _is_paused(self) -> bool:
        """Check if bot is paused via DB status"""
        try:
            status = self.db.get_bot_status()
            return status.get('status') == 'paused'
        except Exception:
            return False

    async def _market_scan_loop(self):
        """Main loop for scanning market and finding new opportunities"""
        logger.info(f"Market scan loop started (interval: {self.scan_interval_hours}h)")

        while self.is_running:
            try:
                if self._is_paused():
                    logger.info("Bot is paused - skipping market scan")
                    await asyncio.sleep(60)
                    continue

                await self._scan_market()

                wait_seconds = self.scan_interval_hours * 3600
                logger.info(f"Next scan in {self.scan_interval_hours} hours...")

                for _ in range(int(wait_seconds / 60)):
                    if not self.is_running:
                        break
                    await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in market scan loop: {e}")
                await asyncio.sleep(300)

    async def _scan_market(self):
        """Scan market for new trading opportunities"""
        self.cycle_number += 1
        self._check_daily_reset()

        logger.info("=" * 60)
        logger.info(f"MARKET SCAN - CYCLE #{self.cycle_number}")
        logger.info("=" * 60)

        try:
            # 1. Get macro data
            logger.info("Fetching macro data...")
            macro_data = await self.macro_fetcher.get_all_macro_data()

            # 2. Get BTC data for correlation features (from production)
            logger.info("Fetching BTC data from production...")
            btc_data = self.binance_data.get_historical_klines('BTCUSDT', '1d', 250)

            # 3. Fetch data for all tickers (from production)
            logger.info(f"Fetching data for {len(settings.TICKERS)} tickers...")
            tickers_data = {}

            for ticker in settings.TICKERS:
                try:
                    df = self.binance_data.get_historical_klines(ticker, '1d', 250)
                    if len(df) >= 200:
                        tickers_data[ticker] = df
                    else:
                        logger.warning(f"Insufficient data for {ticker}: {len(df)} rows")
                except Exception as e:
                    logger.error(f"Failed to fetch {ticker}: {e}")

            logger.info(f"Fetched data for {len(tickers_data)} tickers")

            # 4. Make predictions
            logger.info("Making predictions...")
            predictions_df = self.predictor.predict_multiple(
                tickers_data=tickers_data,
                btc_data=btc_data,
                macro_data=macro_data
            )

            # 5. Save all signals to database
            total_signals = len(predictions_df)
            buy_signals = int((predictions_df['prediction'] == 1).sum())

            for _, row in predictions_df.iterrows():
                self.db.save_signal(
                    ticker=row['ticker'],
                    signal_type=row['signal_type'],
                    probability=row['probability'],
                    features=row['features']
                )

            logger.info(f"Signals: {buy_signals} BUY / {total_signals} total")

            # 6. Update bot status
            self.db.update_bot_status(
                status='running',
                total_signals=int(total_signals),
                buy_signals=buy_signals,
                cycle_number=self.cycle_number,
                last_error=None
            )

            # 7. Get top buy signals
            top_signals = self.predictor.get_top_signals(predictions_df, top_n=10)

            # 8. Execute trades if auto-trading enabled and daily loss allows
            if self.auto_trading and len(top_signals) > 0 and self._can_trade():
                await self._execute_signals(top_signals)
            elif not self._can_trade():
                logger.warning("Trading halted: daily loss limit reached")
            elif not self.auto_trading:
                logger.info("Auto-trading disabled. Signals logged only.")

            self.last_scan_time = _utcnow()
            logger.success(f"Market scan complete - Cycle #{self.cycle_number}")

        except Exception as e:
            logger.error(f"Market scan failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

            self.db.update_bot_status(
                status='error',
                total_signals=0,
                buy_signals=0,
                cycle_number=self.cycle_number,
                last_error=str(e)
            )

    # ============================================
    # TRADE EXECUTION
    # ============================================

    async def _execute_signals(self, signals_df: pd.DataFrame):
        """Execute trades for buy signals"""
        logger.info(f"Executing trades for {len(signals_df)} signals...")

        for _, signal in signals_df.iterrows():
            try:
                await self._execute_trade(signal)
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Failed to execute trade for {signal['ticker']}: {e}")

    async def _execute_trade(self, signal: pd.Series):
        """Execute a single trade"""
        ticker = signal['ticker']
        probability = signal['probability']

        # Duplicate position check
        if ticker in self.positions:
            logger.warning(f"Position already open for {ticker}, skipping")
            return

        # Daily loss check
        if not self._can_trade():
            return

        logger.info(f"Evaluating trade: {ticker} (p={probability:.4f})")

        # 1. Get current price
        current_price = self.binance.get_current_price(ticker)
        if current_price is None:
            logger.error(f"Could not get price for {ticker}")
            return

        # 2. Get portfolio value
        usdt_balance = self.binance.get_usdt_balance()
        portfolio_value = usdt_balance

        # 3. Check if we should trade
        current_positions = len(self.positions)
        should_trade, reason = self.predictor.should_trade(
            ticker=ticker,
            probability=probability,
            current_positions=current_positions,
            daily_loss=self.daily_loss
        )

        if not should_trade:
            logger.warning(f"Trade blocked: {reason}")
            return

        # 4. Calculate position size
        position_info = self.predictor.calculate_position_size(
            current_price=current_price,
            portfolio_value=portfolio_value,
            probability=probability
        )

        quantity = position_info['quantity']
        usd_value = position_info['usd_value']

        # Round quantity to Binance precision
        quantity = self.binance.round_quantity(ticker, quantity)

        if quantity <= 0:
            logger.warning(f"Quantity too small for {ticker} after rounding")
            return

        logger.info(f"Position: {quantity} {ticker} = ${usd_value:.2f}")

        # 5. Execute buy order
        logger.info(f"Executing BUY order: {ticker}")
        order = self.binance.create_market_buy_order(ticker, quantity)

        if order is None:
            logger.error(f"Buy order failed for {ticker}")
            return

        # 6. Get actual executed price (weighted average of all fills)
        fills = order.get('fills', [])
        if fills:
            total_qty = sum(float(f['qty']) for f in fills)
            total_cost = sum(float(f['price']) * float(f['qty']) for f in fills)
            executed_price = total_cost / total_qty if total_qty > 0 else current_price
        else:
            executed_price = current_price

        executed_qty = float(order['executedQty'])
        executed_value = executed_price * executed_qty

        logger.success(f"BUY executed: {executed_qty} {ticker} @ ${executed_price:.2f}")

        # 7. Calculate DYNAMIC TP/SL levels
        macro_data_dict = {
            'fear_greed': signal.get('features', {}).get('fear_greed_value', 50),
            'vix': signal.get('features', {}).get('vix', 20)
        }

        tp_sl = self.risk_manager.calculate_dynamic_tp_sl(
            entry_price=executed_price,
            ticker=ticker,
            features=signal.get('features', {}),
            market_conditions=macro_data_dict
        )

        logger.info(
            f"Dynamic TP/SL: SL=${tp_sl['stop_loss']:.4f} (-{tp_sl['stop_loss_pct']*100:.1f}%) | "
            f"TP1=${tp_sl['tp1']:.4f} (+{tp_sl['tp1_pct']*100:.1f}%) | "
            f"TP2=${tp_sl['tp2']:.4f} (+{tp_sl['tp2_pct']*100:.1f}%) | "
            f"TP3=${tp_sl['tp3']:.4f} (+{tp_sl['tp3_pct']*100:.1f}%)"
        )

        # 8. Place OCO for first TP level (30% of position)
        oco_quantity = executed_qty * tp_sl['tp1_size']
        oco_quantity = self.binance.round_quantity(ticker, oco_quantity)

        oco_order_id = None
        if oco_quantity > 0:
            # Round prices to tick size
            tp_price = self.binance.round_price(ticker, tp_sl['tp1'])
            sl_price = self.binance.round_price(ticker, tp_sl['stop_loss'])
            sl_limit_price = self.binance.round_price(ticker, tp_sl['stop_loss'] * 0.99)

            if tp_price and sl_price and sl_limit_price:
                oco_order = self.binance.create_oco_order(
                    symbol=ticker,
                    quantity=oco_quantity,
                    price=tp_price,
                    stop_price=sl_price,
                    stop_limit_price=sl_limit_price
                )
                if oco_order:
                    oco_order_id = str(oco_order.get('orderListId', ''))
                    logger.success(f"OCO order placed for {ticker} (ID: {oco_order_id})")

        # 9. Log trade to database
        recent_signals = self.db.get_recent_signals(limit=100)
        signal_id = None
        for _, sig in recent_signals.iterrows():
            if sig['ticker'] == ticker:
                signal_id = sig['id']
                break

        trade_id = self.db.save_trade(
            signal_id=signal_id or 0,
            ticker=ticker,
            action='BUY',
            quantity=executed_qty,
            price=executed_price,
            total_value=executed_value,
            status='executed'
        )

        # 10. Store position in memory AND database
        position_data = {
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
            'trailing_stop_active': False,
            'oco_order_id': oco_order_id,
            'entry_features': signal.get('features', {}),
            'trade_id': trade_id,
            'entry_time': _utcnow()
        }

        self.positions[ticker] = position_data

        # Persist to database
        self.db.save_position({
            'ticker': ticker,
            'quantity': executed_qty,
            'remaining_quantity': executed_qty,
            'avg_buy_price': executed_price,
            'current_price': executed_price,
            'total_value': executed_value,
            'pnl': 0,
            'pnl_percentage': 0,
            'stop_loss': tp_sl['stop_loss'],
            'tp1': tp_sl['tp1'], 'tp1_hit': False, 'tp1_size': tp_sl['tp1_size'],
            'tp2': tp_sl['tp2'], 'tp2_hit': False, 'tp2_size': tp_sl['tp2_size'],
            'tp3': tp_sl['tp3'], 'tp3_hit': False, 'tp3_size': tp_sl['tp3_size'],
            'atr_pct': tp_sl['atr_pct'],
            'trailing_stop_enabled': tp_sl['trailing_stop_enabled'],
            'trailing_stop_active': False,
            'oco_order_id': oco_order_id,
            'trade_id': trade_id,
            'entry_time': _utcnow()
        })

        logger.success(f"Trade complete: {ticker} position opened with dynamic TP/SL")

    # ============================================
    # POSITION MONITORING (every 5 minutes)
    # ============================================

    async def _position_monitoring_loop(self):
        """Monitor open positions and check TP/SL"""
        logger.info(f"Position monitoring started (interval: {self.position_monitoring_minutes}min)")

        while self.is_running:
            try:
                if len(self.positions) > 0:
                    await self._monitor_positions()

                await asyncio.sleep(self.position_monitoring_minutes * 60)

            except Exception as e:
                logger.error(f"Error in position monitoring: {e}")
                await asyncio.sleep(60)

    async def _monitor_positions(self):
        """Check all open positions with intelligent exit strategy"""
        logger.debug(f"Monitoring {len(self.positions)} positions...")
        self._check_daily_reset()

        for ticker, position in list(self.positions.items()):
            try:
                # 1. Get current price
                current_price = self.binance.get_current_price(ticker)
                if current_price is None:
                    continue

                position['current_price'] = current_price

                # 2. Calculate P&L
                pnl = (current_price - position['entry_price']) * position['remaining_quantity']
                pnl_pct = ((current_price - position['entry_price']) / position['entry_price']) * 100

                logger.debug(f"  {ticker}: ${current_price:.2f} | P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")

                # 3. Get current market features for intelligent exit
                current_features = await self._get_current_features(ticker)

                # 4. Apply Trailing Stop Loss
                if position.get('trailing_stop_enabled'):
                    new_stop_loss, activated = self.risk_manager.calculate_trailing_stop(
                        entry_price=position['entry_price'],
                        current_price=current_price,
                        current_stop_loss=position['stop_loss'],
                        atr_pct=position.get('atr_pct', 0.03)
                    )

                    if activated:
                        old_sl = position['stop_loss']
                        position['stop_loss'] = new_stop_loss
                        position['trailing_stop_active'] = True
                        logger.info(f"Trailing SL {ticker}: ${old_sl:.4f} -> ${new_stop_loss:.4f}")

                        # Cancel old OCO and place new one with updated SL
                        await self._update_oco_stop_loss(ticker, position, new_stop_loss)

                # 5. Check intelligent exit conditions
                tp_levels = {
                    'tp1': position['tp1'], 'tp1_hit': position['tp1_hit'], 'tp1_size': position['tp1_size'],
                    'tp2': position['tp2'], 'tp2_hit': position['tp2_hit'], 'tp2_size': position['tp2_size'],
                    'tp3': position['tp3'], 'tp3_hit': position['tp3_hit'], 'tp3_size': position['tp3_size']
                }

                exit_decision = self.risk_manager.check_exit_conditions(
                    ticker=ticker,
                    entry_price=position['entry_price'],
                    current_price=current_price,
                    position_size=position['remaining_quantity'],
                    tp_levels=tp_levels,
                    stop_loss=position['stop_loss'],
                    features=current_features,
                    entry_features=position.get('entry_features', {})
                )

                # 6. Execute exit if needed
                if exit_decision['action'] == 'exit_full':
                    logger.warning(f"{ticker} FULL EXIT: {exit_decision['reason']}")
                    await self._cancel_oco_if_exists(ticker, position)
                    sell_pnl = await self._execute_exit(ticker, position['remaining_quantity'], current_price, exit_decision['reason'])
                    if sell_pnl is not None and sell_pnl < 0:
                        self._record_loss(abs(sell_pnl))
                    self.db.delete_position(ticker)
                    del self.positions[ticker]
                    continue

                elif exit_decision['action'] == 'exit_partial':
                    exit_qty = position['remaining_quantity'] * exit_decision['quantity']
                    logger.info(f"{ticker} PARTIAL EXIT: {exit_decision['reason']} ({exit_decision['quantity']*100:.0f}%)")
                    await self._execute_exit(ticker, exit_qty, current_price, exit_decision['reason'])

                    position['remaining_quantity'] -= exit_qty

                    # Mark TP level as hit
                    if 'level' in exit_decision:
                        level_key = f"{exit_decision['level'].lower()}_hit"
                        position[level_key] = True

                # 7. Check basic SL (safety net if OCO missed)
                if current_price <= position['stop_loss']:
                    logger.warning(f"{ticker} STOP LOSS: ${current_price:.2f} <= ${position['stop_loss']:.2f}")
                    await self._cancel_oco_if_exists(ticker, position)
                    sell_pnl = await self._execute_exit(ticker, position['remaining_quantity'], current_price, 'stop_loss')
                    if sell_pnl is not None and sell_pnl < 0:
                        self._record_loss(abs(sell_pnl))
                    self.db.delete_position(ticker)
                    del self.positions[ticker]
                    continue

                # 8. Update position in database
                self.db.update_position(ticker, {
                    'current_price': current_price,
                    'total_value': current_price * position['remaining_quantity'],
                    'pnl': pnl,
                    'pnl_percentage': pnl_pct / 100,
                    'remaining_quantity': position['remaining_quantity'],
                    'stop_loss': position['stop_loss'],
                    'tp1_hit': position['tp1_hit'],
                    'tp2_hit': position['tp2_hit'],
                    'tp3_hit': position['tp3_hit'],
                    'trailing_stop_active': position.get('trailing_stop_active', False),
                })

            except Exception as e:
                logger.error(f"Error monitoring {ticker}: {e}")
                import traceback
                logger.error(traceback.format_exc())

    async def _get_current_features(self, ticker: str) -> dict:
        """Get current features for a ticker (reuses predictor's feature engineer)"""
        try:
            df = self.binance_data.get_historical_klines(ticker, '1d', 250)
            btc_data = self.binance_data.get_historical_klines('BTCUSDT', '1d', 250)

            # Get macro data (async-safe)
            macro_data = await self.macro_fetcher.get_all_macro_data()

            # Use the predictor's feature engineer (not a new instance)
            df_with_features = self.predictor.feature_engineer.calculate_features(df, btc_data, macro_data)
            feature_vector = self.predictor.feature_engineer.get_feature_vector(df_with_features)

            if len(feature_vector) > 0:
                return feature_vector.iloc[-1].to_dict()
        except Exception as e:
            logger.warning(f"Could not get current features for {ticker}: {e}")

        return {}

    async def _cancel_oco_if_exists(self, ticker: str, position: dict):
        """Cancel existing OCO order before placing new one or closing position"""
        oco_id = position.get('oco_order_id')
        if oco_id:
            try:
                self.binance.cancel_order(ticker, oco_id)
                logger.info(f"Cancelled OCO order for {ticker}")
            except Exception as e:
                logger.warning(f"Could not cancel OCO for {ticker}: {e}")

    async def _update_oco_stop_loss(self, ticker: str, position: dict, new_stop_loss: float):
        """Cancel old OCO and place new one with updated stop loss"""
        await self._cancel_oco_if_exists(ticker, position)

        remaining = position['remaining_quantity']
        oco_qty = self.binance.round_quantity(ticker, remaining * position.get('tp1_size', 0.3))

        if oco_qty > 0 and not position.get('tp1_hit', False):
            tp_price = self.binance.round_price(ticker, position['tp1'])
            sl_price = self.binance.round_price(ticker, new_stop_loss)
            sl_limit = self.binance.round_price(ticker, new_stop_loss * 0.99)

            if tp_price and sl_price and sl_limit:
                oco = self.binance.create_oco_order(
                    symbol=ticker,
                    quantity=oco_qty,
                    price=tp_price,
                    stop_price=sl_price,
                    stop_limit_price=sl_limit
                )
                if oco:
                    position['oco_order_id'] = str(oco.get('orderListId', ''))

    async def _execute_exit(self, ticker: str, quantity: float, price: float, reason: str) -> Optional[float]:
        """Execute exit (sell). Returns realized PnL or None on failure."""
        try:
            logger.info(f"Executing SELL: {quantity} {ticker} @ ${price:.4f} ({reason})")

            quantity = self.binance.round_quantity(ticker, quantity)
            if quantity <= 0:
                logger.warning(f"Exit quantity too small for {ticker}")
                return None

            order = self.binance.create_market_sell_order(ticker, quantity)

            if order:
                fills = order.get('fills', [])
                if fills:
                    total_qty = sum(float(f['qty']) for f in fills)
                    total_cost = sum(float(f['price']) * float(f['qty']) for f in fills)
                    executed_price = total_cost / total_qty if total_qty > 0 else price
                else:
                    executed_price = price

                executed_qty = float(order['executedQty'])

                # Calculate PnL
                entry_price = self.positions.get(ticker, {}).get('entry_price', price)
                sell_pnl = (executed_price - entry_price) * executed_qty

                logger.success(f"SELL executed: {executed_qty} {ticker} @ ${executed_price:.2f} | "
                             f"PnL: ${sell_pnl:.2f} | Reason: {reason}")

                # Log to database with PnL
                self.db.save_trade(
                    signal_id=0,
                    ticker=ticker,
                    action='SELL',
                    quantity=executed_qty,
                    price=executed_price,
                    total_value=executed_price * executed_qty,
                    status='executed',
                    pnl=sell_pnl
                )

                return sell_pnl

        except Exception as e:
            logger.error(f"Exit failed for {ticker}: {e}")

        return None

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

    bot = TradingBot()
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
