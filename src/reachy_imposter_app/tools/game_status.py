"""LLM tool exposing the live Imposter game snapshot for the host persona."""

from typing import Any, Dict

from src.reachy_imposter_app.tools.core_tools import Tool, ToolDependencies


class GameStatus(Tool):
    """Peek at the Imposter party game without spoiling secret roles."""

    name = "game_status"
    description = (
        "Read the current Imposter party game state: phase, round, players, "
        "meeting status, winners. Secret roles stay hidden."
    )
    needs_response = False
    parameters_schema: Dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        """Return the public game snapshot, or an error when no game is running."""
        if deps.game is None:
            return {"error": "No game is currently running"}
        return deps.game.public_snapshot("robot")
