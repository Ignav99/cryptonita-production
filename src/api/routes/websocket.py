"""
WebSocket Routes for Real-time Updates
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import List, Any, Optional
import asyncio
import json
from loguru import logger
from datetime import datetime, timezone
import pandas as pd

from config import settings
from src.data.storage.db_manager import DatabaseManager
from src.api.auth import decode_token


def serialize_for_json(obj: Any) -> Any:
    """
    Convert non-JSON-serializable objects to JSON-serializable format
    """
    if pd.isna(obj):
        return None
    elif isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    elif hasattr(obj, 'item'):  # numpy types
        return obj.item()
    else:
        return obj

router = APIRouter(tags=["WebSocket"])

# Database instance
db = DatabaseManager(settings.get_database_url())


class ConnectionManager:
    """Manage WebSocket connections for a specific channel"""

    def __init__(self, name: str = "default"):
        self.name = name
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[{self.name}] WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"[{self.name}] WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


# Separate managers per channel
dashboard_manager = ConnectionManager("dashboard")
signals_manager = ConnectionManager("signals")


async def _validate_ws_token(websocket: WebSocket, token: Optional[str]) -> bool:
    """Validate JWT token for WebSocket connections"""
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return False
    try:
        payload = decode_token(token)
        username = payload.get("sub")
        if not username:
            await websocket.close(code=4001, reason="Invalid token")
            return False
        return True
    except Exception:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return False


@router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket, token: Optional[str] = Query(default=None)):
    """
    WebSocket endpoint for real-time dashboard updates.
    Requires ?token=<jwt> query parameter.
    """
    if not await _validate_ws_token(websocket, token):
        return

    await dashboard_manager.connect(websocket)

    try:
        while True:
            try:
                stats = db.get_dashboard_stats()
                bot_status = db.get_bot_status()
                recent_signals = db.get_recent_signals(limit=10)
                recent_trades = db.get_recent_trades(limit=10)

                update = {
                    "type": "dashboard_update",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": {
                        "stats": serialize_for_json(stats),
                        "bot_status": serialize_for_json(bot_status),
                        "recent_signals_count": len(recent_signals),
                        "recent_trades_count": len(recent_trades)
                    }
                }

                await websocket.send_json(update)
                await asyncio.sleep(5)

            except WebSocketDisconnect:
                break
            except Exception as e:
                error_msg = str(e)
                if "1001" in error_msg or "going away" in error_msg or "close frame" in error_msg:
                    break
                else:
                    logger.error(f"Error in dashboard WebSocket: {e}")
                await asyncio.sleep(5)

    except WebSocketDisconnect:
        pass
    finally:
        dashboard_manager.disconnect(websocket)


@router.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket, token: Optional[str] = Query(default=None)):
    """
    WebSocket endpoint for real-time signal updates.
    Requires ?token=<jwt> query parameter.
    """
    if not await _validate_ws_token(websocket, token):
        return

    await signals_manager.connect(websocket)

    last_signal_id = 0

    try:
        while True:
            try:
                signals_df = db.get_recent_signals(limit=1)

                if len(signals_df) > 0:
                    latest_signal = signals_df.iloc[0]
                    signal_id = int(latest_signal['id'])

                    if signal_id > last_signal_id:
                        signal_timestamp = latest_signal['timestamp']
                        if isinstance(signal_timestamp, (pd.Timestamp, datetime)):
                            signal_timestamp = signal_timestamp.isoformat()

                        update = {
                            "type": "new_signal",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "data": {
                                "id": signal_id,
                                "ticker": latest_signal['ticker'],
                                "signal_type": latest_signal['signal_type'],
                                "probability": float(latest_signal['probability']),
                                "timestamp": signal_timestamp
                            }
                        }

                        await websocket.send_json(update)
                        last_signal_id = signal_id

                await asyncio.sleep(2)

            except WebSocketDisconnect:
                break
            except Exception as e:
                error_msg = str(e)
                if "1001" in error_msg or "going away" in error_msg or "close frame" in error_msg:
                    break
                else:
                    logger.error(f"Error in signals WebSocket: {e}")
                await asyncio.sleep(2)

    except WebSocketDisconnect:
        pass
    finally:
        signals_manager.disconnect(websocket)


async def broadcast_bot_status_update(status: str, message: str = ""):
    """Broadcast bot status update to all dashboard clients"""
    update = {
        "type": "bot_status_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "status": status,
            "message": message
        }
    }
    await dashboard_manager.broadcast(update)


async def broadcast_new_trade(trade_data: dict):
    """Broadcast new trade execution to all dashboard clients"""
    update = {
        "type": "new_trade",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": trade_data
    }
    await dashboard_manager.broadcast(update)
