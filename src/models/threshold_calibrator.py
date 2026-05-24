"""
THRESHOLD CALIBRATOR
=====================
Automatically calibrates per-ticker floor and ceiling thresholds based on
actual signal/trade history.

- floor (threshold_medium): minimum probability to enter a trade.
  Calibrated to the probability value that maximises win_rate × profit_factor
  using historical trade outcomes.
- ceiling (threshold): reject-overfit upper bound.
  Calibrated to percentile_85 of the ticker's probability distribution,
  ensuring the model never silently discards all signals.

If a ticker has no closed trade history (e.g. ONDO when the ceiling was too
low), a distribution-based fallback is used: floor = P30, ceiling = P85 of
all generated probabilities.  This guarantees a usable band for every coin.

Results are persisted to the `coin_thresholds` table and read by
TradingPredictorV4 at startup so no code changes are needed after
each retraining.
"""

from __future__ import annotations

import numpy as np
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from loguru import logger


# ──────────────────────────────────────────────────────────────────────────────
#  DB helpers (raw psycopg2 / sqlalchemy — whatever the project uses)
# ──────────────────────────────────────────────────────────────────────────────

def _get_engine():
    from src.data.storage.db_manager import DatabaseManager
    from config import settings
    return DatabaseManager(settings.get_database_url()).engine


# ──────────────────────────────────────────────────────────────────────────────
#  ThresholdCalibrator
# ──────────────────────────────────────────────────────────────────────────────

class ThresholdCalibrator:
    """
    Per-ticker threshold calibration engine.

    Usage (called by AutoTrainer after a successful model promotion):
        calibrator = ThresholdCalibrator()
        calibrator.calibrate_all(model_version=version)

    Manual bootstrap (run once after deploy):
        calibrator.calibrate_all(model_version=0)

    After calibration, call:
        thresholds = calibrator.load_all_thresholds()
    which returns {ticker: {"floor": float, "ceiling": float}}.
    """

    # Minimum number of signals/trades required to use the trade-based method.
    MIN_SIGNALS_FOR_TRADE_METHOD = 20
    MIN_TRADES_FOR_TRADE_METHOD = 10

    # Grid of candidate floor values to evaluate.
    FLOOR_CANDIDATES = np.arange(0.10, 0.75, 0.05).tolist()

    def __init__(self):
        self.engine = _get_engine()
        self._ensure_table()

    # ──────────────────────────────────────────────────────────────────────────
    #  Table setup
    # ──────────────────────────────────────────────────────────────────────────

    def _ensure_table(self):
        """Create coin_thresholds table if it doesn't exist."""
        ddl = """
        CREATE TABLE IF NOT EXISTS coin_thresholds (
            ticker            VARCHAR(20) PRIMARY KEY,
            floor             NUMERIC     NOT NULL,
            ceiling           NUMERIC     NOT NULL,
            win_rate          NUMERIC,
            profit_factor     NUMERIC,
            n_signals         INTEGER     DEFAULT 0,
            n_trades          INTEGER     DEFAULT 0,
            calibration_method VARCHAR(20) DEFAULT 'distribution',
            calibrated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            model_version     INTEGER
        );
        """
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                conn.execute(text(ddl))
                conn.commit()
        except Exception as exc:
            logger.error(f"ThresholdCalibrator: failed to ensure table: {exc}")

    # ──────────────────────────────────────────────────────────────────────────
    #  Data fetchers
    # ──────────────────────────────────────────────────────────────────────────

    def _fetch_signal_probs(self, ticker: str) -> np.ndarray:
        """Return array of all generated probabilities for a ticker."""
        sql = """
            SELECT probability
            FROM signals
            WHERE ticker = :ticker
              AND probability IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 500
        """
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                rows = conn.execute(text(sql), {"ticker": ticker}).fetchall()
            return np.array([float(r[0]) for r in rows])
        except Exception as exc:
            logger.warning(f"[Calibrator] fetch_signal_probs({ticker}) failed: {exc}")
            return np.array([])

    def _fetch_trade_outcomes(self, ticker: str) -> list[dict]:
        """
        Return list of {probability, pnl, won} for closed BUY trades.
        Joins signals → trades via ticker + time window.
        """
        sql = """
            SELECT
                s.probability,
                t.pnl,
                (t.pnl > 0)::int AS won
            FROM trades t
            JOIN signals s
              ON s.ticker = t.ticker
             AND s.signal_type = 'BUY'
             AND s.timestamp BETWEEN t.timestamp - INTERVAL '1 hour'
                                 AND t.timestamp + INTERVAL '1 hour'
            WHERE t.ticker   = :ticker
              AND t.action   = 'BUY'
              AND t.status   = 'executed'
              AND t.pnl      IS NOT NULL
              AND s.probability IS NOT NULL
            ORDER BY t.timestamp DESC
            LIMIT 200
        """
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                rows = conn.execute(text(sql), {"ticker": ticker}).fetchall()
            return [{"probability": float(r[0]), "pnl": float(r[1]), "won": int(r[2])} for r in rows]
        except Exception as exc:
            logger.warning(f"[Calibrator] fetch_trade_outcomes({ticker}) failed: {exc}")
            return []

    # ──────────────────────────────────────────────────────────────────────────
    #  Core calibration logic
    # ──────────────────────────────────────────────────────────────────────────

    def _calibrate_from_trades(self, trades: list[dict]) -> Tuple[float, float, Dict]:
        """
        Find the floor threshold that maximises win_rate × profit_factor.
        Returns (floor, ceiling, stats).
        """
        best_floor = 0.25
        best_score = -1.0
        best_stats: Dict = {}

        for candidate in self.FLOOR_CANDIDATES:
            filtered = [t for t in trades if t["probability"] >= candidate]
            if len(filtered) < 5:
                continue

            wins = [t for t in filtered if t["won"] == 1]
            losses = [t for t in filtered if t["won"] == 0]

            win_rate = len(wins) / len(filtered)
            gross_profit = sum(t["pnl"] for t in wins) if wins else 0.0
            gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 1e-9
            profit_factor = gross_profit / max(gross_loss, 1e-9)

            score = win_rate * profit_factor

            if score > best_score:
                best_score = score
                best_floor = candidate
                best_stats = {
                    "win_rate": win_rate,
                    "profit_factor": profit_factor,
                    "n_trades": len(filtered),
                    "score": score,
                }

        # Ceiling = floor + 0.40, capped at 0.97
        best_ceiling = min(best_floor + 0.40, 0.97)

        return float(best_floor), float(best_ceiling), best_stats

    def _calibrate_from_distribution(
        self,
        probs: np.ndarray,
        tier_floor: float = 0.25,
        tier_ceiling: float = 0.42,
    ) -> Tuple[float, float, Dict]:
        """
        Distribution-based fallback when trade history is insufficient.
        floor  = max(tier_floor,  P30 of probabilities)
        ceiling = min(0.95, max(tier_ceiling, P85 of probabilities))
        This ensures the band covers the model's actual output range.
        """
        if len(probs) < 10:
            # No data at all — return tier defaults unchanged
            return tier_floor, tier_ceiling, {"method": "no_data"}

        p30 = float(np.percentile(probs, 30))
        p85 = float(np.percentile(probs, 85))

        floor = max(tier_floor, p30)
        ceiling = min(0.97, max(tier_ceiling, p85))

        # Sanity: ceiling must be > floor by at least 0.10
        if ceiling <= floor + 0.10:
            ceiling = min(0.97, floor + 0.20)

        return floor, ceiling, {
            "method": "distribution",
            "p30": p30,
            "p85": p85,
            "n_signals": len(probs),
        }

    # ──────────────────────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────────────────────

    def calibrate_ticker(
        self,
        ticker: str,
        tier_floor: float = 0.25,
        tier_ceiling: float = 0.42,
        model_version: int = 0,
    ) -> Optional[Dict]:
        """
        Calibrate thresholds for a single ticker.
        Returns the calibration result dict or None on failure.
        """
        try:
            trades = self._fetch_trade_outcomes(ticker)
            probs = self._fetch_signal_probs(ticker)

            if len(trades) >= self.MIN_TRADES_FOR_TRADE_METHOD:
                floor, ceiling, stats = self._calibrate_from_trades(trades)
                method = "trades"
            else:
                floor, ceiling, stats = self._calibrate_from_distribution(
                    probs, tier_floor, tier_ceiling
                )
                method = stats.get("method", "distribution")

            result = {
                "ticker": ticker,
                "floor": floor,
                "ceiling": ceiling,
                "win_rate": stats.get("win_rate"),
                "profit_factor": stats.get("profit_factor"),
                "n_signals": int(len(probs)),
                "n_trades": int(len(trades)),
                "calibration_method": method,
                "model_version": model_version,
            }

            self._save_ticker(result)
            logger.info(
                f"[Calibrator] {ticker}: floor={floor:.2f} ceiling={ceiling:.2f} "
                f"method={method} trades={len(trades)} signals={len(probs)}"
            )
            return result

        except Exception as exc:
            logger.error(f"[Calibrator] calibrate_ticker({ticker}) failed: {exc}")
            return None

    def calibrate_all(
        self,
        tickers: Optional[list] = None,
        model_version: int = 0,
    ) -> Dict[str, Dict]:
        """
        Calibrate all tickers. If tickers is None, uses settings.TICKERS.
        Returns {ticker: calibration_result}.
        """
        if tickers is None:
            from config import settings
            tickers = settings.TICKERS
            coin_profiles = settings.COIN_RISK_PROFILES
            default_profile = settings.DEFAULT_RISK_PROFILE
        else:
            from config import settings
            coin_profiles = settings.COIN_RISK_PROFILES
            default_profile = settings.DEFAULT_RISK_PROFILE

        logger.info(f"[Calibrator] Starting calibration for {len(tickers)} tickers...")
        results = {}

        for ticker in tickers:
            profile = coin_profiles.get(ticker, default_profile)
            tier_floor = profile.get("threshold_medium", 0.25)
            tier_ceiling = profile.get("threshold", 0.42)

            result = self.calibrate_ticker(
                ticker=ticker,
                tier_floor=tier_floor,
                tier_ceiling=tier_ceiling,
                model_version=model_version,
            )
            if result:
                results[ticker] = result

        logger.success(
            f"[Calibrator] Done. Calibrated {len(results)}/{len(tickers)} tickers."
        )
        return results

    def load_all_thresholds(self) -> Dict[str, Dict]:
        """
        Load calibrated thresholds from DB.
        Returns {ticker: {"floor": float, "ceiling": float}}.
        """
        sql = "SELECT ticker, floor, ceiling FROM coin_thresholds"
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                rows = conn.execute(text(sql)).fetchall()
            result = {
                str(r[0]): {"floor": float(r[1]), "ceiling": float(r[2])}
                for r in rows
            }
            logger.info(f"[Calibrator] Loaded {len(result)} calibrated thresholds from DB")
            return result
        except Exception as exc:
            logger.error(f"[Calibrator] load_all_thresholds failed: {exc}")
            return {}

    # ──────────────────────────────────────────────────────────────────────────
    #  Internal persistence
    # ──────────────────────────────────────────────────────────────────────────

    def _save_ticker(self, data: Dict):
        """Upsert calibration result for a ticker."""
        sql = """
            INSERT INTO coin_thresholds
                (ticker, floor, ceiling, win_rate, profit_factor, n_signals,
                 n_trades, calibration_method, calibrated_at, model_version)
            VALUES
                (:ticker, :floor, :ceiling, :win_rate, :profit_factor,
                 :n_signals, :n_trades, :calibration_method, NOW(), :model_version)
            ON CONFLICT (ticker) DO UPDATE SET
                floor              = EXCLUDED.floor,
                ceiling            = EXCLUDED.ceiling,
                win_rate           = EXCLUDED.win_rate,
                profit_factor      = EXCLUDED.profit_factor,
                n_signals          = EXCLUDED.n_signals,
                n_trades           = EXCLUDED.n_trades,
                calibration_method = EXCLUDED.calibration_method,
                calibrated_at      = NOW(),
                model_version      = EXCLUDED.model_version
        """
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                conn.execute(text(sql), data)
                conn.commit()
        except Exception as exc:
            logger.error(f"[Calibrator] _save_ticker({data.get('ticker')}) failed: {exc}")
