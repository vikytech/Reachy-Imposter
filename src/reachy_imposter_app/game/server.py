"""WebSocket game server: per-player sessions, state rendering, broadcast."""

import json
import uuid
import asyncio
import logging
from pathlib import Path
from collections.abc import Callable, Awaitable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from reachy_imposter_app.game.engine import GameError, ImposterGame
from reachy_imposter_app.game.events import GameEvent
from reachy_imposter_app.game.narrator import GameNarrator


logger = logging.getLogger(__name__)

_GAME_STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "game"


class GameServer:
    """Owns the websocket connections and drives the shared engine."""

    def __init__(self, game: ImposterGame, narrator: GameNarrator) -> None:
        """Bind the engine and narrator and register the engine event hook."""
        self.game = game
        self.narrator = narrator
        self._sockets: dict[str, WebSocket] = {}
        game.add_listener(self._on_event)

    def _on_event(self, game_event: GameEvent) -> None:
        asyncio.create_task(self._broadcast_states(), name="game-broadcast")

    async def _broadcast_states(self) -> None:
        for player_id, websocket in list(self._sockets.items()):
            try:
                await self._push_state(websocket, player_id)
            except Exception:
                logger.warning("State push to %s failed", player_id)

    def broadcast_narration(self, text: str) -> None:
        """Queue a narration line for every connected player."""
        asyncio.create_task(
            self._send_all(json.dumps({"type": "narration", "text": text})),
            name="game-narration",
        )

    async def _send_all(self, message: str) -> None:
        for websocket in list(self._sockets.values()):
            try:
                await websocket.send_text(message)
            except Exception:
                logger.warning("Narration broadcast failed for one player")

    async def _push_state(self, websocket: WebSocket, player_id: str) -> None:
        await websocket.send_text(json.dumps({"type": "state", "snapshot": self.game.public_snapshot(player_id)}))

    @staticmethod
    def _read_join(data: dict[str, object]) -> tuple[str, str, str]:
        stored_id = data.get("player_id")
        player_id = str(stored_id).strip() if isinstance(stored_id, str) and stored_id.strip() else ""
        name = str(data.get("name") or "Crewmate").strip() or "Crewmate"
        color = str(data.get("color") or "cyan").strip() or "cyan"
        return player_id, name, color

    async def _handle_join(self, websocket: WebSocket) -> str:
        first = json.loads(await websocket.receive_text())
        player_id, name, color = self._read_join(first)
        is_rejoin = player_id in self.game.players
        if not player_id:
            player_id = uuid.uuid4().hex[:8]
        player = self.game.join(player_id, name, color)
        self._sockets[player_id] = websocket
        await websocket.send_text(
            json.dumps(
                {
                    "type": "hello",
                    "player_id": player.player_id,
                    "name": player.name,
                    "color": player.color,
                    "rejoin": is_rejoin,
                }
            )
        )
        await self._push_state(websocket, player.player_id)
        return player.player_id

    async def _route_message(self, player_id: str, data: dict[str, object]) -> None:
        kind = data.get("type")
        if not isinstance(kind, str):
            return
        handler = _HANDLERS.get(kind)
        if handler is None:
            return
        try:
            await handler(self, player_id, data)
        except GameError as exc:
            await self._send_error(player_id, exc.message)
        except Exception:
            logger.exception("Game action %r failed", kind)
            await self._send_error(player_id, "Something went wrong. Try again")

    async def _send_error(self, player_id: str, message: str) -> None:
        logger.warning("Game error for %s: %s", player_id, message)
        websocket = self._sockets.get(player_id)
        if websocket is not None:
            await websocket.send_text(json.dumps({"type": "error", "message": message}))

    async def serve(self, websocket: WebSocket) -> None:
        """Accept one websocket, negotiate identity, then serve messages."""
        await websocket.accept()
        player_id = ""
        try:
            try:
                player_id = await self._handle_join(websocket)
            except GameError as exc:
                await websocket.send_text(json.dumps({"type": "error", "message": exc.message}))
                return
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                if isinstance(data, dict):
                    await self._route_message(player_id, data)
        except WebSocketDisconnect:
            pass
        finally:
            if player_id in self._sockets:
                del self._sockets[player_id]
            if player_id:
                self.game.leave(player_id)


async def _action_config(server: GameServer, player_id: str, data: dict[str, object]) -> None:
    updates = data.get("updates")
    server.game.update_config(player_id, updates if isinstance(updates, dict) else {})


async def _action_start(server: GameServer, player_id: str, data: dict[str, object]) -> None:
    server.game.start(player_id)


async def _action_ready(server: GameServer, player_id: str, data: dict[str, object]) -> None:
    server.game.ready(player_id)


async def _action_task(server: GameServer, player_id: str, data: dict[str, object]) -> None:
    server.game.complete_task(player_id)


async def _action_kill(server: GameServer, player_id: str, data: dict[str, object]) -> None:
    server.game.request_kill(player_id, str(data.get("target")))


async def _action_meeting(server: GameServer, player_id: str, data: dict[str, object]) -> None:
    server.game.call_meeting(player_id)


async def _action_vote(server: GameServer, player_id: str, data: dict[str, object]) -> None:
    target = data.get("target", "skip")
    server.game.vote(player_id, str(target) if target is not None else "skip")


async def _action_play_again(server: GameServer, player_id: str, data: dict[str, object]) -> None:
    server.game.play_again(player_id)


_HANDLERS: dict[str, Callable[[GameServer, str, dict[str, object]], Awaitable[None]]] = {
    "config": _action_config,
    "start": _action_start,
    "ready": _action_ready,
    "task_done": _action_task,
    "kill": _action_kill,
    "call_meeting": _action_meeting,
    "vote": _action_vote,
    "play_again": _action_play_again,
}


def register_game_routes(app: FastAPI, server: GameServer) -> None:
    """Mount the game page and websocket onto a FastAPI app."""
    index = (_GAME_STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/game")
    async def game_page() -> HTMLResponse:
        """Serve the mobile player web UI."""
        return HTMLResponse(index)

    @app.websocket("/ws/game")
    async def game_socket(websocket: WebSocket) -> None:
        """Serve one player's game websocket."""
        await server.serve(websocket)
