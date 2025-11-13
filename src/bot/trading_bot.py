"""
CRYPTONITA TRADING BOT V3
==========================
Main trading bot implementation with:
- Market scanning every 12 hours
- Position monitoring every 5 minutes
- Automatic trade execution
- Risk management
- Database logging
"""

import json
import asyncio
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from loguru import logger
import pandas as pd

from config import settings
from src.services.binance_service import BinanceService
from src.services.binance_data_service import BinanceDataService
from src.models.predictor import TradingPredictor
from src.data.storage.db_manager import DatabaseManager
from src.data.macro_data import MacroDataFetcher
from src.trading.dynamic_risk_manager import DynamicRiskManager


class TradingBot:
    """
    Main trading bot for automated cryptocurrency trading
    """

    def __init__(self, config_path: str = "bot_config.json"):
        """
        Initialize trading bot

        Args:
            config_path: Path to bot configuration file
        """
        logger.info("=" * 60)
        logger.info("🤖 INITIALIZING CRYPTONITA TRADING BOT V3")
        logger.info("=" * 60)

        # Load configuration
        self.config = self._load_config(config_path)
        self.production_config = self._load_production_config()

        # Initialize services
        self.binance = BinanceService()  # For trading (testnet)
        self.binance_data = BinanceDataService()  # For historical data (production, read-only)
        self.predictor = TradingPredictor()
        self.db = DatabaseManager(settings.get_database_url())
        self.macro_fetcher = MacroDataFetcher()
        self.risk_manager = DynamicRiskManager()  # Dynamic TP/SL management

        logger.info("💡 Using Binance PRODUCTION for data, TESTNET for trading")

        # Bot state
        self.is_running = False
        self.cycle_number = 0
        self.daily_loss = 0.0
        self.last_scan_time = None
        self.positions: Dict[str, Dict] = {}

        # Trading parameters from config
        self.scan_interval_hours = self.config['trading']['scan_interval_hours']
        self.position_monitoring_minutes = self.config['trading']['position_monitoring_minutes']
        self.auto_trading = self.config['trading']['auto_trading_enabled']

        logger.success("✅ Trading Bot initialized successfully")
        self._log_configuration()

    def _load_config(self, config_path: str) -> dict:
        """Load bot configuration"""
        try:
            # Try relative path first
            config_file = Path(config_path)

            # If not found, try from project root
            if not config_file.exists():
                project_root = Path(__file__).parent.parent.parent
                config_file = project_root / config_path

            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                logger.info(f"📄 Bot config loaded from {config_file}")
                return config
            else:
                logger.warning(f"⚠️ Config file not found: {config_path}, using defaults")
                return self._default_config()
        except Exception as e:
            logger.warning(f"⚠️ Failed to load config: {e}, using defaults")
            return self._default_config()

    def _load_production_config(self) -> dict:
        """Load production system configuration"""
        try:
            config_path = Path(settings.MASTER_CONFIG_FILE)
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info("📄 Production config loaded")
            return config
        except Exception as e:
            logger.error(f"❌ Failed to load production config: {e}")
            return {}

    def _default_config(self) -> dict:
        """Return default configuration"""
        return {
            "trading": {
                "scan_interval_hours": 12,
                "position_monitoring_minutes": 5,
                "auto_trading_enabled": True,
                "require_manual_approval": False
            },
            "risk_management": {
                "max_positions": 10,
                "max_daily_loss_usd": 200
            }
        }

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

    # ============================================
    # MAIN BOT LOOP
    # ============================================

    async def start(self):
        """Start the trading bot"""
        logger.info("🚀 Starting trading bot...")

        # Test Binance connection
        if not self.binance.test_connectivity():
            logger.error("❌ Failed to connect to Binance. Aborting.")
            return

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
            asyncio.create_task(self._binance_sync_loop())
        ]

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

                # Wait for next scan interval
                wait_seconds = self.scan_interval_hours * 3600
                logger.info(f"⏰ Next scan in {self.scan_interval_hours} hours...")

                # Sleep in small chunks to allow for shutdown
                for _ in range(int(wait_seconds / 60)):
                    if not self.is_running:
                        break
                    await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"❌ Error in market scan loop: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error

    async def _scan_market(self):
        """Scan market for new trading opportunities"""
        self.cycle_number += 1
        logger.info("=" * 60)
        logger.info(f"🔍 MARKET SCAN - CYCLE #{self.cycle_number}")
        logger.info("=" * 60)

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

            for ticker in settings.TICKERS:
                try:
                    df = self.binance_data.get_historical_klines(ticker, '1d', 250)
                    if len(df) >= 200:
                        tickers_data[ticker] = df
                    else:
                        logger.warning(f"⚠️ Insufficient data for {ticker}: {len(df)} rows")
                except Exception as e:
                    logger.error(f"❌ Failed to fetch {ticker}: {e}")

            logger.info(f"✅ Fetched data for {len(tickers_data)} tickers")

            # 4. Make predictions
            logger.info("🔮 Making predictions...")
            predictions_df = self.predictor.predict_multiple(
                tickers_data=tickers_data,
                btc_data=btc_data,
                macro_data=macro_data
            )

            # 5. Save all signals to database
            total_signals = len(predictions_df)
            buy_signals = (predictions_df['prediction'] == 1).sum()

            for _, row in predictions_df.iterrows():
                self.db.save_signal(
                    ticker=row['ticker'],
                    signal_type=row['signal_type'],
                    probability=row['probability'],
                    features=row['features']
                )

            logger.info(f"📊 Signals: {buy_signals} BUY / {total_signals} total")

            # 6. Update bot status (convert numpy types to Python types)
            self.db.update_bot_status(
                status='running',
                total_signals=int(total_signals),  # Convert from numpy.int64 to int
                buy_signals=int(buy_signals),      # Convert from numpy.int64 to int
                cycle_number=self.cycle_number,
                last_error=None
            )

            # 7. Get top buy signals
            top_signals = self.predictor.get_top_signals(predictions_df, top_n=10)

            # 8. Execute trades if auto-trading enabled
            if self.auto_trading and len(top_signals) > 0:
                await self._execute_signals(top_signals)
            else:
                logger.info("ℹ️ Auto-trading disabled. Signals logged only.")

            self.last_scan_time = datetime.utcnow()
            logger.success(f"✅ Market scan complete - Cycle #{self.cycle_number}")

        except Exception as e:
            logger.error(f"❌ Market scan failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Update bot status with error
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
        logger.info(f"💰 Executing trades for {len(signals_df)} signals...")

        for _, signal in signals_df.iterrows():
            try:
                await self._execute_trade(signal)
                await asyncio.sleep(2)  # Small delay between trades
            except Exception as e:
                logger.error(f"❌ Failed to execute trade for {signal['ticker']}: {e}")

    async def _execute_trade(self, signal: pd.Series):
        """Execute a single trade"""
        ticker = signal['ticker']
        probability = signal['probability']

        logger.info(f"💵 Evaluating trade: {ticker} (p={probability:.4f})")

        # 1. Get current price
        current_price = self.binance.get_current_price(ticker)
        if current_price is None:
            logger.error(f"❌ Could not get price for {ticker}")
            return

        # 2. Get portfolio value
        usdt_balance = self.binance.get_usdt_balance()
        portfolio_value = usdt_balance  # Simplified for now

        # 3. Check if we should trade
        current_positions = len(self.positions)
        should_trade, reason = self.predictor.should_trade(
            ticker=ticker,
            probability=probability,
            current_positions=current_positions,
            daily_loss=self.daily_loss
        )

        if not should_trade:
            logger.warning(f"⚠️ Trade blocked: {reason}")
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

        logger.info(f"💰 Position: {quantity} {ticker} = ${usd_value:.2f}")

        # 5. Execute buy order on Binance
        logger.info(f"🛒 Executing BUY order: {ticker}")
        order = self.binance.create_market_buy_order(ticker, quantity)

        if order is None:
            logger.error(f"❌ Buy order failed for {ticker}")
            return

        # 6. Get actual executed price
        executed_price = float(order.get('fills', [{}])[0].get('price', current_price))
        executed_qty = float(order['executedQty'])
        executed_value = executed_price * executed_qty

        logger.success(f"✅ BUY executed: {executed_qty} {ticker} @ ${executed_price:.2f}")

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
            market_conditions=macro_data_dict
        )

        # 8. Place OCO order for TP1 (first take profit level)
        # We'll manage TP2, TP3 and trailing stop dynamically in monitoring
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

        # 9. Log trade to database
        # Get signal_id from the most recent signal for this ticker
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

        # Update positions table in database
        self.db.upsert_position(
            ticker=ticker,
            quantity=executed_qty,
            avg_buy_price=executed_price,
            current_price=executed_price
        )

        # 10. Update position tracking with dynamic TP/SL data
        self.positions[ticker] = {
            'quantity': executed_qty,
            'remaining_quantity': executed_qty,  # Track remaining after partial exits
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
            'entry_features': signal.get('features', {}),  # Save entry features for comparison
            'trade_id': trade_id,
            'entry_time': datetime.utcnow()
        }

        logger.success(f"✅ Trade complete: {ticker} position opened with dynamic TP/SL")

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

        for ticker, position in list(self.positions.items()):
            try:
                # 1. Get current price
                current_price = self.binance.get_current_price(ticker)
                if current_price is None:
                    continue

                # Update position
                position['current_price'] = current_price

                # 2. Calculate P&L
                pnl = (current_price - position['entry_price']) * position['remaining_quantity']
                pnl_pct = ((current_price - position['entry_price']) / position['entry_price']) * 100

                logger.debug(f"  {ticker}: ${current_price:.2f} | P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")

                # 3. Get current market features for intelligent exit
                try:
                    df = self.binance_data.get_historical_klines(ticker, '1d', 250)
                    btc_data = self.binance_data.get_historical_klines('BTCUSDT', '1d', 250)

                    # Get macro data (await since we're in async function)
                    macro_data = await self.macro_fetcher.get_all_macro_data()

                    # Calculate current features
                    from src.data.features import FeatureEngineer
                    feature_engineer = FeatureEngineer()
                    df_with_features = feature_engineer.calculate_features(df, btc_data, macro_data)
                    feature_vector = feature_engineer.get_feature_vector(df_with_features)

                    if len(feature_vector) > 0:
                        current_features = feature_vector.iloc[-1].to_dict()
                    else:
                        current_features = {}

                except Exception as e:
                    logger.warning(f"⚠️ Could not get current features for {ticker}: {e}")
                    current_features = {}

                # 4. Apply Trailing Stop Loss
                if position['trailing_stop_enabled']:
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
                        logger.info(f"🔼 {ticker} Trailing SL: ${old_sl:.4f} → ${new_stop_loss:.4f}")

                        # Update OCO order with new stop loss
                        # Note: Binance requires canceling old OCO and creating new one
                        # For simplicity, we'll just track it here

                # 5. Check intelligent exit conditions
                tp_levels = {
                    'tp1': position['tp1'],
                    'tp1_hit': position['tp1_hit'],
                    'tp1_size': position['tp1_size'],
                    'tp2': position['tp2'],
                    'tp2_hit': position['tp2_hit'],
                    'tp2_size': position['tp2_size'],
                    'tp3': position['tp3'],
                    'tp3_hit': position['tp3_hit'],
                    'tp3_size': position['tp3_size']
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
                    logger.warning(f"🚪 {ticker} FULL EXIT: {exit_decision['reason']}")
                    await self._execute_exit(ticker, position['remaining_quantity'], current_price, exit_decision['reason'])
                    del self.positions[ticker]
                    continue

                elif exit_decision['action'] == 'exit_partial':
                    exit_qty = position['remaining_quantity'] * exit_decision['quantity']
                    logger.info(f"📤 {ticker} PARTIAL EXIT: {exit_decision['reason']} ({exit_decision['quantity']*100:.0f}%)")
                    await self._execute_exit(ticker, exit_qty, current_price, exit_decision['reason'])

                    position['remaining_quantity'] -= exit_qty

                    # Mark TP level as hit if applicable
                    if 'level' in exit_decision:
                        level_key = f"{exit_decision['level'].lower()}_hit"
                        position[level_key] = True

                # 7. Check basic TP/SL (in case OCO failed)
                if current_price <= position['stop_loss']:
                    logger.warning(f"🛑 {ticker} STOP LOSS hit: ${current_price:.2f} <= ${position['stop_loss']:.2f}")
                    await self._execute_exit(ticker, position['remaining_quantity'], current_price, 'stop_loss')
                    del self.positions[ticker]
                    continue

                # 8. Update position in database
                self.db.execute_command(
                    """
                    UPDATE positions
                    SET current_price = :current_price,
                        total_value = :total_value,
                        pnl = :pnl,
                        pnl_percentage = :pnl_pct,
                        last_update = :last_update
                    WHERE ticker = :ticker
                    """,
                    {
                        'ticker': ticker,
                        'current_price': current_price,
                        'total_value': current_price * position['remaining_quantity'],
                        'pnl': pnl,
                        'pnl_pct': pnl_pct / 100,
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
            logger.info(f"💰 Executing SELL: {quantity} {ticker} @ ${price:.4f}")

            # Round quantity
            quantity = self.binance.round_quantity(ticker, quantity)

            # Execute market sell
            order = self.binance.create_market_sell_order(ticker, quantity)

            if order:
                executed_price = float(order.get('fills', [{}])[0].get('price', price))
                executed_qty = float(order['executedQty'])
                logger.success(f"✅ SELL executed: {executed_qty} {ticker} @ ${executed_price:.2f} | Reason: {reason}")

                # Log to database
                self.db.save_trade(
                    signal_id=0,
                    ticker=ticker,
                    action='SELL',
                    quantity=executed_qty,
                    price=executed_price,
                    total_value=executed_price * executed_qty,
                    status='executed'
                )

        except Exception as e:
            logger.error(f"❌ Exit failed for {ticker}: {e}")

    # ============================================
    # BINANCE SYNC (every 30 minutes)
    # ============================================

    async def _binance_sync_loop(self):
        """Sync positions with Binance every 30 minutes"""
        logger.info("🔄 Binance sync started (interval: 30min)")

        while self.is_running:
            try:
                await self._sync_positions_with_binance()

                # Wait for next sync interval (30 minutes)
                await asyncio.sleep(30 * 60)

            except Exception as e:
                logger.error(f"❌ Error in Binance sync: {e}")
                await asyncio.sleep(60)

    async def _sync_positions_with_binance(self):
        """Fetch real positions from Binance and update database"""
        try:
            logger.info("🔄 Syncing positions with Binance...")

            # Get positions that the bot has opened (from DB)
            db_positions = self.db.get_positions()

            if len(db_positions) == 0:
                logger.info("📊 No bot positions to sync")
                return

            # Get all balances from Binance ONCE (not inside loop!)
            logger.debug("📊 Fetching account balances from Binance...")
            balances = self.binance.get_account_balance()

            # Update each position with current price from Binance
            synced_count = 0
            for _, db_pos in db_positions.iterrows():
                ticker = db_pos['ticker']

                try:
                    # Get current price from Binance
                    current_price = self.binance.get_current_price(ticker)
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

                    # Get actual quantity from Binance
                    actual_quantity = balances[asset]['total']

                    # Update position with current data
                    self.db.upsert_position(
                        ticker=ticker,
                        quantity=actual_quantity,
                        avg_buy_price=float(db_pos['avg_buy_price']),
                        current_price=current_price
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
