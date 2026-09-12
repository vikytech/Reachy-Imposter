"""Typed event shape emitted by the game engine to servers, narrators, and tests."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameEvent:
    """One semantic fact that happened in the game; consumers subscribe by kind."""

    kind: str
    payload: dict[str, object]
