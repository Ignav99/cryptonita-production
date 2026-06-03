"""Unit tests for BinanceFuturesService using mocks."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def make_service():
    """Create service with mocked settings and client."""
    with patch("src.services.binance_futures_service.settings") as mock_settings:
        mock_settings.get_binance_credentials.return_value = ("key", "secret")
        mock_settings.is_testnet.return_value = True

        from src.services.binance_futures_service import BinanceFuturesService

        svc = BinanceFuturesService(lazy_init=True)

        # Inject mock client directly, bypassing _ensure_client
        mock_client = MagicMock()
        svc._client = mock_client
        svc._initialized = True

        return svc, mock_client


def test_open_long_calls_futures_create_order():
    svc, mock_client = make_service()
    mock_client.futures_change_leverage.return_value = {"leverage": 1}
    mock_client.futures_create_order.return_value = {"orderId": "123", "status": "FILLED"}

    result = svc.open_long("BTCUSDT", 0.001)

    assert result is not None
    mock_client.futures_create_order.assert_called_once()
    call_kwargs = mock_client.futures_create_order.call_args[1]
    assert call_kwargs["side"] == "BUY"
    assert call_kwargs["type"] == "MARKET"


def test_open_short_calls_sell():
    svc, mock_client = make_service()
    mock_client.futures_change_leverage.return_value = {"leverage": 1}
    mock_client.futures_create_order.return_value = {"orderId": "456"}

    result = svc.open_short("ETHUSDT", 0.01)

    assert result is not None
    call_kwargs = mock_client.futures_create_order.call_args[1]
    assert call_kwargs["side"] == "SELL"


def test_close_long_uses_reduce_only():
    svc, mock_client = make_service()
    mock_client.futures_create_order.return_value = {"orderId": "789"}

    svc.close_long("BTCUSDT", 0.001)

    call_kwargs = mock_client.futures_create_order.call_args[1]
    assert call_kwargs.get("reduceOnly") is True
    assert call_kwargs["side"] == "SELL"


def test_close_short_uses_buy_reduce_only():
    svc, mock_client = make_service()
    mock_client.futures_create_order.return_value = {"orderId": "101"}

    svc.close_short("BTCUSDT", -0.001)  # Negative qty (positionAmt)

    call_kwargs = mock_client.futures_create_order.call_args[1]
    assert call_kwargs.get("reduceOnly") is True
    assert call_kwargs["side"] == "BUY"
    assert call_kwargs["quantity"] > 0  # Must be positive


def test_get_position_returns_dict():
    svc, mock_client = make_service()
    mock_client.futures_position_information.return_value = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "0.001",
            "entryPrice": "30000",
            "unRealizedProfit": "10.5",
            "leverage": "1",
            "liquidationPrice": "0",
            "marginType": "cross",
        }
    ]

    pos = svc.get_position("BTCUSDT")

    assert pos is not None
    assert pos["symbol"] == "BTCUSDT"
    assert pos["positionAmt"] == 0.001


def test_set_leverage_cached():
    svc, mock_client = make_service()
    mock_client.futures_change_leverage.return_value = {"leverage": 2}

    svc.set_leverage("BTCUSDT", 2)
    svc.set_leverage("BTCUSDT", 2)  # Second call should NOT hit API

    assert mock_client.futures_change_leverage.call_count == 1


def test_get_futures_balance_returns_usdt():
    svc, mock_client = make_service()
    mock_client.futures_account.return_value = {
        "assets": [
            {"asset": "BNB", "availableBalance": "5.0"},
            {"asset": "USDT", "availableBalance": "1234.56"},
        ]
    }

    balance = svc.get_futures_balance()

    assert balance == 1234.56


def test_get_futures_balance_returns_zero_on_missing_usdt():
    svc, mock_client = make_service()
    mock_client.futures_account.return_value = {"assets": []}

    balance = svc.get_futures_balance()

    assert balance == 0.0


def test_get_all_positions_filters_zero_amt():
    svc, mock_client = make_service()
    mock_client.futures_position_information.return_value = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "0.001",
            "entryPrice": "30000",
            "unRealizedProfit": "5.0",
            "leverage": "1",
        },
        {
            "symbol": "ETHUSDT",
            "positionAmt": "0",
            "entryPrice": "0",
            "unRealizedProfit": "0",
            "leverage": "1",
        },
    ]

    positions = svc.get_all_positions()

    assert len(positions) == 1
    assert positions[0]["symbol"] == "BTCUSDT"
    assert positions[0]["side"] == "LONG"


def test_cancel_all_orders_returns_true():
    svc, mock_client = make_service()
    mock_client.futures_cancel_all_open_orders.return_value = {}

    result = svc.cancel_all_orders("BTCUSDT")

    assert result is True
    mock_client.futures_cancel_all_open_orders.assert_called_once_with(symbol="BTCUSDT")


def test_open_long_returns_none_on_api_error():
    from binance.exceptions import BinanceAPIException

    svc, mock_client = make_service()
    mock_client.futures_change_leverage.return_value = {"leverage": 1}
    mock_client.futures_create_order.side_effect = BinanceAPIException(
        MagicMock(status_code=400), 400, '{"code": -2010, "msg": "Insufficient margin"}'
    )

    result = svc.open_long("BTCUSDT", 999999.0)

    assert result is None


def test_is_connected_after_manual_init():
    svc, mock_client = make_service()
    assert svc.is_connected() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
