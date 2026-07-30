from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, player_id: str, websocket: WebSocket):
        await websocket.accept()
        if player_id not in self.active_connections:
            self.active_connections[player_id] = []
        self.active_connections[player_id].append(websocket)
        logger.info(f"WebSocket connected for player: {player_id}")

    def disconnect(self, player_id: str, websocket: WebSocket):
        if player_id in self.active_connections:
            if websocket in self.active_connections[player_id]:
                self.active_connections[player_id].remove(websocket)
            if not self.active_connections[player_id]:
                del self.active_connections[player_id]
        logger.info(f"WebSocket disconnected for player: {player_id}")

    async def broadcast_to_player(self, player_id: str, message: dict):
        if player_id in self.active_connections:
            for connection in self.active_connections[player_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending WebSocket message to {player_id}: {e}")

    async def broadcast_all(self, message: dict):
        for player_id, connections in self.active_connections.items():
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

ws_manager = ConnectionManager()

@router.websocket("/ws/queue/{player_id}")
async def queue_websocket(websocket: WebSocket, player_id: str):
    await ws_manager.connect(player_id, websocket)
    try:
        while True:
            # Keep connection open and listen for heartbeat / ping
            data = await websocket.receive_text()
            # Optional ping response
            await websocket.send_json({"type": "PONG", "message": "heartbeat ok"})
    except WebSocketDisconnect:
        ws_manager.disconnect(player_id, websocket)
