"""
WebSocket Routes for Real-time Updates
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Any
import asyncio
import json
from loguru import logger
from datetime import datetime
import pandas as pd

from config import settings
from src.data.storage.db_manager import DatabaseManager


def serialize_for_json(obj: Any) -> Any:
    """
    Convert non-JSON-serializable objects to JSON-serializable format

    Handles:
    - pandas Timestamp -> ISO string
    - datetime -> ISO string
    - numpy types -> Python types
    - pandas Series/DataFrame -> dict/list
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
    """Manage WebSocket connections"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and store new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"🔌 WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        self.active_connections.remove(websocket)
        logger.info(f"🔌 WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"❌ Failed to send to client: {e}")
                disconnected.append(connection)

        # Remove disconnected clients
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates

    Sends periodic updates with:
    - Bot status
    - Dashboard stats
    - Recent signals
    - Recent trades
    """
    await manager.connect(websocket)

    try:
        while True:
            try:
                # Fetch current data
                stats = db.get_dashboard_stats()
                bot_status = db.get_bot_status()
                recent_signals = db.get_recent_signals(limit=10)
                recent_trades = db.get_recent_trades(limit=10)

                # Prepare update message with serialization
                update = {
                    "type": "dashboard_update",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": {
                        "stats": serialize_for_json(stats),
                        "bot_status": serialize_for_json(bot_status),
                        "recent_signals_count": len(recent_signals),
                        "recent_trades_count": len(recent_trades)
                    }
                }

                # Send to this client
                await websocket.send_json(update)

                # Wait before next update (every 5 seconds)
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"❌ Error in WebSocket loop: {e}")
                await asyncio.sleep(5)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")


@router.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """
    WebSocket endpoint for real-time signal updates

    Sends new signals as they are generated
    """
    await manager.connect(websocket)

    last_signal_id = 0

    try:
        while True:
            try:
                # Get recent signals
                signals_df = db.get_recent_signals(limit=1)

                if len(signals_df) > 0:
                    latest_signal = signals_df.iloc[0]
                    signal_id = int(latest_signal['id'])

                    # Check if this is a new signal
                    if signal_id > last_signal_id:
                        # New signal detected - serialize timestamp properly
                        signal_timestamp = latest_signal['timestamp']
                        if isinstance(signal_timestamp, (pd.Timestamp, datetime)):
                            signal_timestamp = signal_timestamp.isoformat()

                        update = {
                            "type": "new_signal",
                            "timestamp": datetime.utcnow().isoformat(),
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

                # Wait before checking again (every 2 seconds)
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"❌ Error in signals WebSocket: {e}")
                await asyncio.sleep(2)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Signals WebSocket client disconnected")


async def broadcast_bot_status_update(status: str, message: str = ""):
    """
    Broadcast bot status update to all connected clients

    Args:
        status: New bot status
        message: Optional message
    """
    update = {
        "type": "bot_status_update",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "status": status,
            "message": message
        }
    }
    await manager.broadcast(update)


async def broadcast_new_trade(trade_data: dict):
    """
    Broadcast new trade execution to all connected clients

    Args:
        trade_data: Trade information dict
    """
    update = {
        "type": "new_trade",
        "timestamp": datetime.utcnow().isoformat(),
        "data": trade_data
    }
    await manager.broadcast(update)
