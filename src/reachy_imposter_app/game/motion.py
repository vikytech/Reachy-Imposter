"""Map game events to robot reactions (recorded emotions + head gaze)."""

import logging
from typing import TYPE_CHECKING

from reachy_imposter_app.game.events import GameEvent
from reachy_imposter_app.tools.play_emotion import resolve_emotion_name
from reachy_imposter_app.dance_emotion_moves import GotoQueueMove, EmotionQueueMove


if TYPE_CHECKING:
    from reachy_mini.motion.recorded_move import RecordedMoves
    from reachy_imposter_app.moves import MovementManager


logger = logging.getLogger(__name__)

# Recorded emotion intents, by event kind. Skipped kinds stay silent.
_EVENT_INTENTS: dict[str, str] = {
    "game_started": "excited",
    "all_ready": "attentive",
    "round_started": "attentive",
    "task_done": "happy",
    "round_completed": "happy",
    "kill": "scared",
    "meeting_called": "surprised",
    "discussion_started": "attentive",
    "vote_started": "thinking",
    "game_reset": "greeting",
    "player_joined": "greeting",
}

_GAZE_EVENTS: frozenset[str] = frozenset({"game_started", "kill"})


class GameMotion:
    """Reacts to engine events by queueing expressive robot moves."""

    def __init__(self, movement_manager: "MovementManager", library: "RecordedMoves | None" = None) -> None:
        """Store the movement manager and optionally preload the emotion library."""
        self.movement_manager = movement_manager
        self._library = library
        self._emotion_names: list[str] = []

    def _loaded_library(self) -> "RecordedMoves | None":
        if self._library is None:
            try:
                from reachy_mini.motion.recorded_move import RecordedMoves

                self._library = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")
            except Exception as exc:
                logger.warning("Emotion library unavailable: %s", exc)
                return None
        return self._library

    def _queue_emotion(self, intent: str) -> None:
        library = self._loaded_library()
        if library is None:
            return
        if not self._emotion_names:
            self._emotion_names = library.list_moves()
        emotion_name = resolve_emotion_name(intent, self._emotion_names)
        if emotion_name is None:
            return
        self.movement_manager.queue_move(EmotionQueueMove(emotion_name, library))

    def _queue_gaze(self) -> None:
        try:
            from reachy_mini.utils import create_head_pose

            left = create_head_pose(0, 0, 0, 0, 0, 20, degrees=True)
            right = create_head_pose(0, 0, 0, 0, 0, -20, degrees=True)
            neutral = create_head_pose(0, 0, 0, 0, 0, 0, degrees=True)
        except Exception as exc:  # pragma: no cover - reachy_mini not installed
            logger.warning("Head pose helpers unavailable: %s", exc)
            return
        self.movement_manager.queue_move(GotoQueueMove(left, duration=0.4))
        self.movement_manager.queue_move(GotoQueueMove(right, duration=0.4))
        self.movement_manager.queue_move(GotoQueueMove(neutral, duration=0.4))

    def _react_to_result(self, payload: dict[str, object]) -> None:
        if payload.get("target_id") is None:
            self._queue_emotion("confused")
        else:
            self._queue_emotion("surprised")

    def handle(self, game_event: GameEvent) -> None:
        """Queue the reaction for one engine event, ignoring unhandled kinds."""
        kind = game_event.kind
        if kind in _GAZE_EVENTS:
            self._queue_gaze()
        if kind == "meeting_result":
            self._react_to_result(game_event.payload)
            return
        if kind == "game_over":
            self._queue_emotion("excited" if game_event.payload.get("winner") == "impostor" else "grateful")
            return
        intent = _EVENT_INTENTS.get(kind)
        if intent is not None:
            self._queue_emotion(intent)
