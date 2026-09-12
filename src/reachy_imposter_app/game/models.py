"""Data model for the Imposter party game: roles, phases, players, config."""

import logging
from enum import Enum
from dataclasses import field, fields, replace, dataclass

from reachy_imposter_app.game.events import GameEvent


logger = logging.getLogger(__name__)


class Role(str, Enum):
    """Secret team a player belongs to. Never shared while the game hides it."""

    CREW = "crew"
    IMPOSTOR = "impostor"


class Phase(str, Enum):
    """Broad game phases every client renders against."""

    LOBBY = "lobby"
    ROLE_REVEAL = "role_reveal"
    PLAY = "play"
    DISCUSSION = "discussion"
    VOTING = "voting"
    GAME_OVER = "game_over"


MIN_PLAYERS = 4
MAX_PLAYERS = 10
MAX_IMPOSTORS = 3

PLAYER_COLORS: tuple[str, ...] = (
    "cyan",
    "red",
    "lime",
    "yellow",
    "purple",
    "orange",
    "pink",
    "white",
    "blue",
    "brown",
)

# (minimum, maximum) bounds per host-configurable field.
_CONFIG_RANGES: dict[str, tuple[int, int]] = {
    "max_players": (MIN_PLAYERS, MAX_PLAYERS),
    "impostor_count": (1, MAX_IMPOSTORS),
    "discussion_seconds": (15, 180),
    "voting_seconds": (10, 120),
    "kill_cooldown_seconds": (5, 120),
    "max_rounds": (3, 10),
}


@dataclass(frozen=True)
class GameConfig:
    """Host-controllable game parameters. Bounds live in ``_CONFIG_RANGES``."""

    max_players: int = 8
    impostor_count: int = 1
    discussion_seconds: float = 60.0
    voting_seconds: float = 30.0
    kill_cooldown_seconds: float = 30.0
    max_rounds: int = 6

    def with_updates(self, updates: dict[str, object]) -> "GameConfig":
        """Return a validated copy with ``updates`` applied; raise ValueError on bad values."""
        unknown = sorted(name for name in updates if name not in _CONFIG_FIELDS)
        if unknown:
            raise ValueError(f"Unknown config field(s): {', '.join(unknown)}")
        corrections: dict[str, int] = {}
        for name, raw_value in updates.items():
            low, high = _CONFIG_RANGES[name]
            if isinstance(raw_value, bool) or not isinstance(raw_value, int):
                raise ValueError(f"{name} must be an integer")
            candidate = raw_value
            if not low <= candidate <= high:
                raise ValueError(f"{name} must be between {low} and {high}")
            corrections[name] = candidate
        return replace(self, **corrections)


_CONFIG_FIELDS = frozenset(field_def.name for field_def in fields(GameConfig) if field_def.init)


@dataclass
class Player:
    """One participant's full server-side state."""

    player_id: str
    name: str
    color: str
    role: Role | None = None
    alive: bool = True
    online: bool = True
    is_host: bool = False
    ready: bool = False
    task_done: bool = False
    task: str | None = None
    emergency_used: bool = False
    vote: str | None = None
    kill_after_timestamp: float = 0.0
    seen_tasks: list[str] = field(default_factory=list)


def event(kind: str, **payload: object) -> GameEvent:
    """Build a typed game event with the common shape used across the engine."""
    return GameEvent(kind=kind, payload=payload)
