"""
Smoke tests for walk_forward_backtest_v5 utility functions.

Tests ONLY the pure-function utilities (simulate_pnl, calculate_metrics).
No model training is performed here.
"""
import numpy as np
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.walk_forward_backtest_v5 import simulate_pnl, calculate_metrics, normalise_ticker


# ---------------------------------------------------------------------------
# simulate_pnl
# ---------------------------------------------------------------------------

class TestSimulatePnl:
    def test_long_win(self):
        """LONG signal + truth=1 (TP hit) → positive return."""
        returns = simulate_pnl(np.array([1]), np.array([1]), tp_pct=0.05, sl_pct=0.03)
        assert returns[0] == pytest.approx(0.05)

    def test_long_loss(self):
        """LONG signal + truth=2 (SL hit) → negative return."""
        returns = simulate_pnl(np.array([2]), np.array([1]), tp_pct=0.05, sl_pct=0.03)
        assert returns[0] == pytest.approx(-0.03)

    def test_long_flat(self):
        """LONG signal + truth=0 (time expired) → zero return."""
        returns = simulate_pnl(np.array([0]), np.array([1]), tp_pct=0.05, sl_pct=0.03)
        assert returns[0] == pytest.approx(0.0)

    def test_short_win(self):
        """SHORT signal + truth=2 (SL hit in underlying = price dropped) → win."""
        returns = simulate_pnl(np.array([2]), np.array([2]), tp_pct=0.05, sl_pct=0.03)
        assert returns[0] == pytest.approx(0.05)

    def test_short_loss(self):
        """SHORT signal + truth=1 (TP hit in underlying = price rose) → loss."""
        returns = simulate_pnl(np.array([1]), np.array([2]), tp_pct=0.05, sl_pct=0.03)
        assert returns[0] == pytest.approx(-0.03)

    def test_short_flat(self):
        """SHORT signal + truth=0 (time expired) → zero return."""
        returns = simulate_pnl(np.array([0]), np.array([2]), tp_pct=0.05, sl_pct=0.03)
        assert returns[0] == pytest.approx(0.0)

    def test_hold_is_always_zero(self):
        """HOLD signal → 0 return regardless of truth."""
        y_pred = np.array([0, 0, 0])
        y_true = np.array([0, 1, 2])
        returns = simulate_pnl(y_true, y_pred, tp_pct=0.05, sl_pct=0.03)
        np.testing.assert_array_equal(returns, [0.0, 0.0, 0.0])

    def test_mixed_signals(self):
        """Mixed signals produce correct element-wise returns."""
        y_pred = np.array([1, 2, 0, 1, 2])
        y_true = np.array([1, 2, 1, 2, 1])
        # long+win, short+win, hold, long+loss, short+loss
        expected = np.array([0.05, 0.05, 0.0, -0.03, -0.03])
        returns = simulate_pnl(y_true, y_pred, tp_pct=0.05, sl_pct=0.03)
        np.testing.assert_allclose(returns, expected)

    def test_output_length_matches_input(self):
        """Return array has same length as inputs."""
        n = 50
        y_pred = np.random.choice([0, 1, 2], size=n)
        y_true = np.random.choice([0, 1, 2], size=n)
        returns = simulate_pnl(y_true, y_pred)
        assert len(returns) == n

    def test_custom_tp_sl(self):
        """Custom tp_pct and sl_pct are respected."""
        returns = simulate_pnl(np.array([1]), np.array([1]), tp_pct=0.10, sl_pct=0.05)
        assert returns[0] == pytest.approx(0.10)
        returns = simulate_pnl(np.array([2]), np.array([1]), tp_pct=0.10, sl_pct=0.05)
        assert returns[0] == pytest.approx(-0.05)


# ---------------------------------------------------------------------------
# calculate_metrics
# ---------------------------------------------------------------------------

class TestCalculateMetrics:
    def _base_inputs(self):
        """Simple deterministic set with known properties."""
        y_true = np.array([1, 2, 0, 1, 2, 1])
        y_pred = np.array([1, 2, 0, 0, 1, 1])
        # trade outcomes: long+win, short+win, hold, hold, short+loss, long+win
        returns = simulate_pnl(y_true, y_pred)
        return y_true, y_pred, returns

    def test_returns_dict_with_required_keys(self):
        y_true, y_pred, returns = self._base_inputs()
        metrics = calculate_metrics(y_true, y_pred, returns)
        required_keys = [
            "n_test_rows", "n_long_signals", "n_short_signals", "n_hold_signals",
            "long_win_rate", "short_win_rate", "overall_win_rate",
            "total_return_pct", "avg_return_per_trade",
            "sharpe", "max_drawdown_pct", "oos_accuracy",
        ]
        for key in required_keys:
            assert key in metrics, f"Missing key: {key}"

    def test_win_rates_in_valid_range(self):
        y_true, y_pred, returns = self._base_inputs()
        metrics = calculate_metrics(y_true, y_pred, returns)
        for key in ("long_win_rate", "short_win_rate", "overall_win_rate"):
            val = metrics[key]
            if not (isinstance(val, float) and np.isnan(val)):
                assert 0.0 <= val <= 1.0, f"{key}={val} out of [0,1]"

    def test_n_test_rows(self):
        y_true, y_pred, returns = self._base_inputs()
        metrics = calculate_metrics(y_true, y_pred, returns)
        assert metrics["n_test_rows"] == 6

    def test_signal_counts_sum_to_total(self):
        y_true, y_pred, returns = self._base_inputs()
        metrics = calculate_metrics(y_true, y_pred, returns)
        assert (
            metrics["n_long_signals"]
            + metrics["n_short_signals"]
            + metrics["n_hold_signals"]
        ) == metrics["n_test_rows"]

    def test_all_hold_returns_nan_win_rates(self):
        """If all predictions are HOLD, win rates should be NaN (no signals)."""
        y_true = np.array([1, 0, 2, 1, 0])
        y_pred = np.zeros(5, dtype=int)
        returns = simulate_pnl(y_true, y_pred)
        metrics = calculate_metrics(y_true, y_pred, returns)
        assert np.isnan(metrics["long_win_rate"])
        assert np.isnan(metrics["short_win_rate"])
        assert np.isnan(metrics["overall_win_rate"])

    def test_oos_accuracy_perfect(self):
        """When y_pred == y_true, accuracy = 1.0."""
        y = np.array([0, 1, 2, 0, 1, 2])
        returns = simulate_pnl(y, y)
        metrics = calculate_metrics(y, y, returns)
        assert metrics["oos_accuracy"] == pytest.approx(1.0)

    def test_total_return_is_sum_of_trade_returns(self):
        """total_return_pct = sum(returns) * 100."""
        y_true = np.array([1, 2, 1])
        y_pred = np.array([1, 2, 1])  # all wins
        returns = simulate_pnl(y_true, y_pred, tp_pct=0.05, sl_pct=0.03)
        metrics = calculate_metrics(y_true, y_pred, returns)
        expected_total = float(returns.sum()) * 100
        assert metrics["total_return_pct"] == pytest.approx(expected_total)

    def test_max_drawdown_is_non_positive(self):
        """Max drawdown is always <= 0."""
        y_true = np.array([1, 2, 0, 1, 2])
        y_pred = np.array([1, 2, 0, 1, 2])
        returns = simulate_pnl(y_true, y_pred)
        metrics = calculate_metrics(y_true, y_pred, returns)
        assert metrics["max_drawdown_pct"] <= 0.0

    def test_returns_computed_internally_if_not_passed(self):
        """calculate_metrics computes returns internally when not provided."""
        y_true = np.array([1, 1, 2])
        y_pred = np.array([1, 2, 2])
        metrics = calculate_metrics(y_true, y_pred)  # no returns arg
        assert "total_return_pct" in metrics


# ---------------------------------------------------------------------------
# normalise_ticker
# ---------------------------------------------------------------------------

class TestNormaliseTicker:
    def test_usdt_suffix_stripped(self):
        assert normalise_ticker("BTCUSDT") == "BTC-USD"

    def test_usd_suffix_stripped(self):
        assert normalise_ticker("ETHUSD") == "ETH-USD"

    def test_passthrough_dash_format(self):
        assert normalise_ticker("ADA-USD") == "ADA-USD"

    def test_lowercase_input(self):
        assert normalise_ticker("adausdt") == "ADA-USD"

    def test_sol(self):
        assert normalise_ticker("SOLUSDT") == "SOL-USD"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
