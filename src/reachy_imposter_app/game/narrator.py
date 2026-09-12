"""Turn engine events into the host's spoken narration, moves and UI lines."""

import random
import asyncio
import logging
from typing import Any
from collections.abc import Callable, Awaitable, Coroutine

from reachy_imposter_app.game import scripts
from reachy_imposter_app.game.engine import ImposterGame
from reachy_imposter_app.game.events import GameEvent
from reachy_imposter_app.game.motion import GameMotion


logger = logging.getLogger(__name__)


class GameNarrator:
    """Subscribes to engine events and drives speech, motion and on-screen lines."""

    def __init__(
        self,
        game: ImposterGame,
        schedule_say: Callable[[Coroutine[Any, Any, None]], None],
        say: Callable[[str], Awaitable[None]],
        motion: GameMotion | None = None,
        on_line: Callable[[str], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """Store dependencies; call :meth:`attach` to start listening to the engine."""
        self.game = game
        self.motion = motion
        self.on_line = on_line
        self._schedule_say = schedule_say
        self._say = say
        self._rng = rng or random.Random()

    def attach(self) -> None:
        """Subscribe to every engine event the game produces."""
        self.game.set_emitter(self._handle)

    def _announce(self, texts: str | list[str], pause_s: float = 1.4) -> None:
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            return
        for text in texts:
            logger.info("Game narration: %s", text)
            if self.on_line is not None:
                self.on_line(text)
        self._schedule_say(self._speak_each(texts, pause_s))

    async def _speak_each(self, texts: list[str], pause_s: float) -> None:
        for index, text in enumerate(texts):
            await self._say(text)
            if index < len(texts) - 1:
                await asyncio.sleep(pause_s)

    def _name_tallies(self, payload: dict[str, object]) -> dict[str, int]:
        raw_votes = payload.get("votes")
        if not isinstance(raw_votes, dict):
            return {}
        return {
            self.game.players[player_id].name: count
            for player_id, count in raw_votes.items()
            if isinstance(count, int) and player_id in self.game.players
        }

    @staticmethod
    def _as_int(value: object, default: int) -> int:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return default

    def _line_for(self, game_event: GameEvent) -> list[str]:
        kind = game_event.kind
        payload = game_event.payload
        rng = self._rng
        if kind == "player_joined":
            name = str(payload.get("name") or "somebody")
            if payload.get("is_host"):
                return [scripts.welcome(rng, name)]
            return [scripts.join(rng, name)]
        if kind == "game_started":
            return [scripts.game_start(rng)]
        if kind == "all_ready":
            return [scripts.all_ready(rng, self._as_int(payload.get("impostor_count", 0), 0))]
        if kind == "round_started":
            round_number = self._as_int(payload.get("round", 1), 1)
            alive_count = self._as_int(payload.get("alive_count", 0), 0)
            impostor_count = self._as_int(payload.get("impostor_count", 0), 0)
            return [scripts.round_start(rng, round_number, alive_count, impostor_count), scripts.crew_task_prompt(rng)]
        if kind == "task_done":
            return [scripts.task_done(rng, str(payload.get("name") or "somebody"))]
        if kind == "round_completed":
            return [scripts.round_complete(rng)]
        if kind == "kill":
            return [scripts.kill(rng, str(payload.get("target_name") or "someone"))]
        if kind == "meeting_called":
            return [scripts.emergency_call(rng, str(payload.get("caller_name") or "someone"))]
        if kind == "discussion_started":
            return [scripts.discussion_open(rng)]
        if kind == "vote_started":
            return [scripts.vote_open(rng)]
        if kind == "meeting_result":
            ejected_name = payload.get("target_name")
            tallies = self._name_tallies(payload)
            skipped = self._as_int(payload.get("skipped", 0), 0)
            counted = scripts.vote_monologue(rng, tallies, skipped, str(ejected_name) if ejected_name else None)
            verdict = scripts.ejection(rng, str(ejected_name)) if ejected_name else scripts.no_ejection(rng)
            return [counted, verdict]
        if kind == "game_over":
            winner = payload.get("winner")
            win_line = scripts.impostor_win(rng) if winner == "impostor" else scripts.crew_win(rng)
            return [scripts.game_over_roll(rng), win_line]
        return []

    def _handle(self, game_event: GameEvent) -> None:
        texts = self._line_for(game_event)
        if texts:
            self._announce(texts)
        if self.motion is not None:
            self.motion.handle(game_event)
