"""
TRADING PREDICTOR
=================
Sistema completo de predicción que integra:
- Feature engineering
- Model loading
- Prediction logic
- Trading signals
"""

import numpy as np
import pandas as pd
import xgboost as xgb
from typing import Dict, Optional, Tuple
from loguru import logger

from config import settings
from src.data.features import FeatureEngineer
from src.data.macro_data import MacroDataFetcher
from src.models.model_loader import ModelLoader


class TradingPredictor:
    """
    Complete trading prediction system for Model V3
    """

    def __init__(self):
        """Initialize predictor with model and feature engineer"""

        # Load model
        self.model_loader = ModelLoader(settings.MODEL_FILE)
        self.model = self.model_loader.load_model()

        # Initialize feature engineer
        self.feature_engineer = FeatureEngineer()

        # Initialize macro data fetcher
        self.macro_fetcher = MacroDataFetcher()

        # Trading parameters from config
        self.threshold = settings.PREDICTION_THRESHOLD

        logger.info(f"✅ Trading Predictor initialized - Threshold: {self.threshold}")

    def predict_single(
        self,
        ticker: str,
        ohlcv_data: pd.DataFrame,
        btc_data: Optional[pd.DataFrame] = None,
        macro_data: Optional[Dict] = None
    ) -> Tuple[int, float, Dict]:
        """
        Make prediction for a single ticker

        Args:
            ticker: Crypto ticker (e.g., 'BTCUSDT')
            ohlcv_data: OHLCV DataFrame with columns [timestamp, open, high, low, close, volume]
            btc_data: Optional BTC OHLCV data for correlation features
            macro_data: Optional macro indicators dict

        Returns:
            Tuple of (prediction, probability, features_dict)
            - prediction: 0 (HOLD) or 1 (BUY)
            - probability: Model confidence (0-1)
            - features_dict: Dictionary of calculated features
        """
        try:
            # Calculate features
            feature_vector = self.feature_engineer.calculate_single_prediction_features(
                ticker_data=ohlcv_data,
                btc_data=btc_data,
                macro_data=macro_data
            )

            if feature_vector is None:
                logger.warning(f"⚠️ Could not calculate features for {ticker}")
                return 0, 0.0, {}

            # Convert to DMatrix for XGBoost
            dmatrix = xgb.DMatrix(
                feature_vector.reshape(1, -1),
                feature_names=self.feature_engineer.required_features
            )

            # Get prediction probability
            probability = self.model_loader.predict(dmatrix)

            # Make decision based on threshold
            prediction = 1 if probability >= self.threshold else 0

            # Create features dict for logging
            features_dict = {
                name: float(value)
                for name, value in zip(self.feature_engineer.required_features, feature_vector)
            }

            signal_type = "BUY" if prediction == 1 else "HOLD"
            logger.info(f"📊 {ticker}: {signal_type} (p={probability:.4f})")

            return prediction, probability, features_dict

        except Exception as e:
            logger.error(f"❌ Prediction failed for {ticker}: {e}")
            return 0, 0.0, {}

    def predict_multiple(
        self,
        tickers_data: Dict[str, pd.DataFrame],
        btc_data: Optional[pd.DataFrame] = None,
        macro_data: Optional[Dict] = None
    ) -> pd.DataFrame:
        """
        Make predictions for multiple tickers

        Args:
            tickers_data: Dict mapping ticker -> OHLCV DataFrame
            btc_data: Optional BTC data
            macro_data: Optional macro data

        Returns:
            DataFrame with columns [ticker, prediction, probability, signal_type]
        """
        results = []

        logger.info(f"🔮 Making predictions for {len(tickers_data)} tickers...")

        for ticker, ohlcv_data in tickers_data.items():
            prediction, probability, features = self.predict_single(
                ticker=ticker,
                ohlcv_data=ohlcv_data,
                btc_data=btc_data,
                macro_data=macro_data
            )

            results.append({
                'ticker': ticker,
                'prediction': prediction,
                'probability': probability,
                'signal_type': 'BUY' if prediction == 1 else 'HOLD',
                'features': features
            })

        df = pd.DataFrame(results)

        # Count buy signals
        buy_signals = (df['prediction'] == 1).sum()
        logger.success(f"✅ Predictions complete: {buy_signals} BUY signals from {len(tickers_data)} tickers")

        return df

    def get_top_signals(
        self,
        predictions_df: pd.DataFrame,
        top_n: int = 10,
        min_probability: Optional[float] = None
    ) -> pd.DataFrame:
        """
        Get top N signals by probability

        Args:
            predictions_df: DataFrame from predict_multiple
            top_n: Number of top signals to return
            min_probability: Minimum probability threshold (overrides default)

        Returns:
            DataFrame with top signals sorted by probability
        """
        threshold = min_probability if min_probability is not None else self.threshold

        # Filter by threshold
        signals = predictions_df[predictions_df['probability'] >= threshold].copy()

        # Sort by probability descending
        signals = signals.sort_values('probability', ascending=False)

        # Get top N
        top_signals = signals.head(top_n)

        logger.info(f"📈 Top {len(top_signals)} signals (threshold={threshold:.2f})")

        return top_signals

    async def get_macro_data_async(self) -> Dict:
        """
        Fetch macro data asynchronously

        Returns:
            Dict with macro indicators
        """
        try:
            macro_data = await self.macro_fetcher.get_all_macro_data()
            return macro_data
        except Exception as e:
            logger.error(f"❌ Failed to fetch macro data: {e}")
            # Return defaults
            return {
                'fear_greed': 50.0,
                'funding_rate': 0.0,
                'spx': 4500.0,
                'spx_change_7d': 0.0,
                'vix': 20.0
            }

    def get_macro_data_sync(self) -> Dict:
        """
        Fetch macro data synchronously

        Returns:
            Dict with macro indicators
        """
        try:
            macro_data = self.macro_fetcher.get_all_macro_data_sync()
            return macro_data
        except Exception as e:
            logger.error(f"❌ Failed to fetch macro data: {e}")
            # Return defaults
            return {
                'fear_greed': 50.0,
                'funding_rate': 0.0,
                'spx': 4500.0,
                'spx_change_7d': 0.0,
                'vix': 20.0
            }

    def should_trade(
        self,
        ticker: str,
        probability: float,
        current_positions: int,
        daily_loss: float
    ) -> Tuple[bool, str]:
        """
        Determine if we should execute a trade based on risk management rules

        Args:
            ticker: Ticker symbol
            probability: Model probability
            current_positions: Number of current open positions
            daily_loss: Current daily loss in USD

        Returns:
            Tuple of (should_trade: bool, reason: str)
        """
        # Check probability threshold
        if probability < self.threshold:
            return False, f"Probability {probability:.4f} below threshold {self.threshold}"

        # Check max positions
        if current_positions >= settings.MAX_POSITIONS:
            return False, f"Max positions reached ({settings.MAX_POSITIONS})"

        # Check daily loss limit
        if daily_loss >= settings.MAX_DAILY_LOSS_USD:
            return False, f"Daily loss limit reached (${daily_loss:.2f})"

        # Check manual approval requirement
        if settings.REQUIRE_MANUAL_APPROVAL:
            return False, "Manual approval required"

        return True, "All checks passed"

    def calculate_position_size(
        self,
        current_price: float,
        portfolio_value: float,
        probability: float
    ) -> Dict[str, float]:
        """
        Calculate position size based on risk management

        Args:
            current_price: Current price of the asset
            portfolio_value: Total portfolio value
            probability: Model probability

        Returns:
            Dict with {quantity, usd_value, position_pct}
        """
        # Base position size (% of portfolio)
        base_pct = settings.POSITION_SIZE_PCT

        # Scale by probability (optional - more aggressive for higher confidence)
        # scaled_pct = base_pct * (probability / self.threshold)
        # For now, use fixed percentage
        scaled_pct = base_pct

        # Calculate USD value
        usd_value = portfolio_value * scaled_pct

        # Cap at max position size
        if usd_value > settings.MAX_POSITION_SIZE_USD:
            usd_value = settings.MAX_POSITION_SIZE_USD

        # Cap at max position percentage
        max_usd_by_pct = portfolio_value * settings.MAX_POSITION_SIZE_PCT
        if usd_value > max_usd_by_pct:
            usd_value = max_usd_by_pct

        # Calculate quantity
        quantity = usd_value / current_price

        return {
            'quantity': quantity,
            'usd_value': usd_value,
            'position_pct': (usd_value / portfolio_value) * 100
        }

    def calculate_stop_loss_take_profit(
        self,
        entry_price: float
    ) -> Dict[str, float]:
        """
        Calculate stop loss and take profit levels

        Args:
            entry_price: Entry price

        Returns:
            Dict with {stop_loss, take_profit}
        """
        stop_loss = entry_price * (1 - settings.STOP_LOSS_PCT)
        take_profit = entry_price * (1 + settings.TAKE_PROFIT_PCT)

        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'stop_loss_pct': settings.STOP_LOSS_PCT * 100,
            'take_profit_pct': settings.TAKE_PROFIT_PCT * 100
        }
