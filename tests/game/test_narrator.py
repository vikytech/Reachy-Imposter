"""Regression tests for listener wiring between the game engine and its sinks."""

import random
from collections.abc import Callable, Coroutine

from reachy_imposter_app.game.engine import ImposterGame
from reachy_imposter_app.game.narrator import GameNarrator


def _make_narrator(game: ImposterGame, on_line: Callable[[str], None]) -> GameNarrator:
    async def say(_text: str) -> None:
        """Speech stub; narration lines are only logged, not voiced, in tests."""

    def schedule_say(_coroutine: Coroutine) -> None:
        """Drop scheduled speech in tests."""
        _coroutine.close()

    return GameNarrator(game, schedule_say, say, on_line=on_line)


def test_attach_keeps_existing_listeners() -> None:
    """GameServer-style listeners must survive narrator.attach() (regression)."""
    game = ImposterGame(rng=random.Random(0))
    received: list[str] = []
    game.add_listener(lambda event: received.append(event.kind))

    narrator = _make_narrator(game, on_line=lambda _text: None)
    narrator.attach()

    game.join("p0", "Alice", "cyan")

    assert "player_joined" in received
    assert "lobby_updated" in received


def test_narrator_line_and_state_listeners_both_fire() -> None:
    """The narrator announces events while other listeners keep receiving them."""
    game = ImposterGame(rng=random.Random(7))
    kinds: list[str] = []
    game.add_listener(lambda event: kinds.append(event.kind))
    lines: list[str] = []

    narrator = _make_narrator(game, on_line=lines.append)
    narrator.attach()

    game.join("p0", "Alice", "cyan")

    assert kinds == ["host_changed", "player_joined", "lobby_updated"]
    assert lines, "narrator must still produce lines after attach()"
