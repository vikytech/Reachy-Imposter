"""Authoritative Imposter party game state machine.

Pure logic with no robot or web dependencies, so the whole ruleset is
headless-testable. Mutations run on whatever asyncio loop drives the server;
timers (meetings, vote phase, round roll-over) are engine-owned tasks.
"""

import time
import random
import asyncio
import logging
from dataclasses import dataclass
from collections.abc import Callable

from src.reachy_imposter_app.game.tasks import assign_task
from src.reachy_imposter_app.game.events import GameEvent
from src.reachy_imposter_app.game.models import MIN_PLAYERS, Role, Phase, Player, GameConfig, event


logger = logging.getLogger(__name__)

# Delay between "everyone ready" and the first round starting.
ROLE_REVEAL_DELAY_S = 2.5
SKIP_VOTE = "skip"

Emitter = Callable[[GameEvent], None]


class GameError(Exception):
    """A rejected game action carrying a player-facing message."""

    def __init__(self, message: str) -> None:
        """Store the player-facing rejection message."""
        super().__init__(message)
        self.message = message


@dataclass
class Meeting:
    """Why a meeting was opened, for narration and the UI banner."""

    reason: str
    caller_id: str | None = None
    target_id: str | None = None

    def open_line(self, players: dict[str, Player]) -> tuple[str, str]:
        """Return a stable (heading, subheading) pair for the meeting screen."""
        if self.reason == "kill" and self.target_id:
            target_name = players[self.target_id].name
            return "Body Found!", f"{target_name} was found dead."
        if self.reason == "emergency" and self.caller_id:
            return "Emergency Meeting", f"Called by {players[self.caller_id].name}."
        return "Meeting", "Ship inspection complete."


class ImposterGame:
    """Single authoritative game; one instance per running app."""

    def __init__(self, rng: random.Random | None = None) -> None:
        """Spin up an empty lobby with a fresh, valid default configuration."""
        self.players: dict[str, Player] = {}
        self.config = GameConfig()
        self.phase = Phase.LOBBY
        self.round_number = 0
        self.meeting: Meeting | None = None
        self.votes: dict[str, str] = {}
        self.winner_role: Role | None = None
        self.win_reason: str = ""
        self.roles_revealed: bool = False
        self.host_player_id: str | None = None
        self.role_reveal_delay_s = ROLE_REVEAL_DELAY_S
        self._rng = rng or random.Random()
        self._listeners: list[Emitter] = []
        self._timer_task: asyncio.Task[None] | None = None
        self._now = time.monotonic

    # ── wiring ──────────────────────────────────────────────────────────────

    def set_emitter(self, emitter: Emitter | None) -> None:
        """Replace all event listeners with a single emitter (or none)."""
        self._listeners = [emitter] if emitter is not None else []

    def add_listener(self, listener: Emitter) -> None:
        """Append another event listener alongside any existing ones."""
        self._listeners.append(listener)

    def _emit(self, kind: str, **payload: object) -> None:
        game_event = event(kind, **payload)
        for listener in self._listeners:
            listener(game_event)

    def _cancel_timer(self) -> None:
        if self._timer_task is not None and not self._timer_task.done():
            self._timer_task.cancel()

    def _arm_timer(self, delay: float, action: str) -> None:
        self._cancel_timer()
        self._timer_task = asyncio.create_task(self._run_after(delay, action), name="game-phase-timer")

    async def _run_after(self, delay: float, action: str) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        try:
            getattr(self, action)()
        except Exception:
            logger.exception("Game phase action %r failed", action)

    # ── helpers ────────────────────────────────────────────────────────────

    def _player(self, player_id: str) -> Player:
        existing = self.players.get(player_id)
        if existing is None:
            raise GameError("Player no longer in the game")
        return existing

    def _require_phase(self, *phases: Phase, action: str) -> None:
        if self.phase not in phases:
            raise GameError(f"Cannot {action} right now")

    def _alive_crew(self) -> list[Player]:
        return [player for player in self.players.values() if player.alive and player.role is Role.CREW]

    def _alive_impostors(self) -> list[Player]:
        return [player for player in self.players.values() if player.alive and player.role is Role.IMPOSTOR]

    def _host(self) -> Player | None:
        if self.host_player_id is None:
            return None
        return self.players.get(self.host_player_id)

    def _available_name(self, requested: str) -> str:
        taken = {player.name for player in self.players.values()}
        if requested not in taken:
            return requested
        suffix = 2
        while f"{requested} {suffix}" in taken:
            suffix += 1
        return f"{requested} {suffix}"

    # ── lobby ──────────────────────────────────────────────────────────────

    def join(self, player_id: str, name: str, color: str) -> Player:
        """Add a player to the lobby or reattach a known connection."""
        existing = self.players.get(player_id)
        if existing is not None:
            existing.online = True
            return existing
        if self.phase is not Phase.LOBBY:
            raise GameError("Round in progress; wait for the next game to join.")
        if len(self.players) >= self.config.max_players:
            raise GameError("Host is full")
        player = Player(player_id=player_id, name=self._available_name(name), color=color)
        self.players[player_id] = player
        self._ensure_host()
        self._emit("player_joined", player_id=player_id, name=player.name, color=player.color, is_host=player.is_host)
        self._emit("lobby_updated")
        return player

    def _ensure_host(self) -> None:
        if self.host_player_id is not None and self.host_player_id in self.players:
            return
        online = [player for player in self.players.values() if player.online] or list(self.players.values())
        if not online:
            return
        host = online[0]
        for player in self.players.values():
            player.is_host = False
        host.is_host = True
        self.host_player_id = host.player_id
        self._emit("host_changed", host_id=self.host_player_id, host_name=host.name)

    def leave(self, player_id: str) -> None:
        """Mark a player offline (during a game) or drop them (in the lobby)."""
        player = self.players.get(player_id)
        if player is None:
            return
        if self.phase is Phase.LOBBY:
            del self.players[player_id]
            if self.host_player_id == player_id:
                self.host_player_id = None
            self._emit("player_left", player_id=player_id)
            self._emit("lobby_updated")
            self._ensure_host()
            return
        player.online = False
        self._emit("player_left", player_id=player_id)
        if self.host_player_id == player_id:
            self._ensure_host()

    def update_config(self, player_id: str, updates: dict[str, object]) -> GameConfig:
        """Host-only lobby config edit; validate ranges before applying."""
        host = self._host()
        if host is None or host.player_id != player_id:
            raise GameError("Only the host can change the setup")
        self._require_phase(Phase.LOBBY, action="change the setup")
        try:
            updated = self.config.with_updates(updates)
        except ValueError as exc:
            raise GameError(str(exc)) from exc
        self.config = updated
        self._emit("config_updated", max_players=self.config.max_players, impostor_count=self.config.impostor_count)
        return self.config

    # ── game start ─────────────────────────────────────────────────────────

    def start(self, player_id: str) -> None:
        """Assign secret roles and move the room into the role-reveal phase."""
        host = self._host()
        if host is None or host.player_id != player_id:
            raise GameError("Only the host can start the game")
        self._require_phase(Phase.LOBBY, action="start the game")
        if len(self.players) < MIN_PLAYERS:
            raise GameError(f"Need at least {MIN_PLAYERS} players")
        if self.config.impostor_count >= len(self.players):
            raise GameError("Fewer players than impostors")
        self.round_number = 0
        self.roles_revealed = False
        self.meeting = None
        self.votes.clear()
        order = list(self.players.values())
        self._rng.shuffle(order)
        for index, player in enumerate(order):
            player.role = Role.IMPOSTOR if index < self.config.impostor_count else Role.CREW
            player.alive = True
            player.ready = False
            player.task_done = False
            player.task = None
            player.emergency_used = False
            player.vote = None
        self.phase = Phase.ROLE_REVEAL
        self._emit(
            "game_started",
            min_players=MIN_PLAYERS,
            impostor_count=self.config.impostor_count,
            crew_count=len(self._alive_crew()),
        )
        self._emit("role_assigned")

    def ready(self, player_id: str) -> None:
        """Acknowledge one player's role; start the first round once all are ready."""
        self._require_phase(Phase.ROLE_REVEAL, action="ready up")
        player = self._player(player_id)
        if not player.ready:
            player.ready = True
            self._emit("ready", player_id=player_id, name=player.name)
            if all(existing.ready for existing in self.players.values()):
                self._emit("all_ready", impostor_count=len(self._alive_impostors()))
                self._arm_timer(self.role_reveal_delay_s, "_start_first_round")

    def _start_first_round(self) -> None:
        self._start_round()

    # ── rounds ─────────────────────────────────────────────────────────────

    def _start_round(self) -> None:
        impostors = self._alive_impostors()
        if impostors and len(impostors) >= len(self._alive_crew()):
            self._end_game(Role.IMPOSTOR, "the impostors reached parity with the crew")
            return
        if self.round_number >= self.config.max_rounds:
            self._end_game(Role.IMPOSTOR, "time ran out and the impostor escaped")
            return
        self.round_number += 1
        self.votes.clear()
        self.meeting = None
        now = self._now()
        round_tasks: set[str] = set()
        for player in self.players.values():
            if not player.alive:
                continue
            if player.role is Role.CREW:
                player.task = assign_task(self._rng, player.seen_tasks, round_tasks)
            player.task_done = False
            player.ready = False
            player.vote = None
            if player.role is Role.IMPOSTOR:
                player.kill_after_timestamp = now + self.config.kill_cooldown_seconds
        self.phase = Phase.PLAY
        self._emit(
            "round_started",
            round=self.round_number,
            max_rounds=self.config.max_rounds,
            alive_count=len([p for p in self.players.values() if p.alive]),
            impostor_count=len(self._alive_impostors()),
        )
        self._check_end_conditions()

    def complete_task(self, player_id: str) -> None:
        """Mark a crewmate's round task done; close the round when all tasks finish."""
        self._require_phase(Phase.PLAY, action="complete a task")
        player = self._player(player_id)
        if player.role is not Role.CREW:
            raise GameError("Only crewmates have tasks")
        if player.task_done:
            raise GameError("Task already done")
        player.task_done = True
        self._emit("task_done", player_id=player_id, name=player.name, remaining=self._undone_crew())
        if self._undone_crew() <= 0:
            self._emit("round_completed", round=self.round_number)
            self._arm_timer(self.role_reveal_delay_s, "_advance_round")

    def _undone_crew(self) -> int:
        return len(self._alive_crew()) - sum(1 for player in self._alive_crew() if player.task_done)

    def _advance_round(self) -> None:
        if self._undone_crew() <= 0:
            self._start_round()

    # ── violence and meetings ──────────────────────────────────────────────

    def request_kill(self, killer_id: str, target_id: str) -> None:
        """Impostor kill on a live crewmate; immediately opens a meeting."""
        self._require_phase(Phase.PLAY, action="kill")
        killer = self._player(killer_id)
        if killer.role is not Role.IMPOSTOR:
            raise GameError("Only the impostor can kill")
        if not killer.alive:
            raise GameError("The dead cannot kill")
        if self._now() < killer.kill_after_timestamp:
            raise GameError("Your kill is on cooldown")
        target = self._player(target_id)
        if target_id == killer_id:
            raise GameError("That would be absurd — even for you")
        if not target.alive:
            raise GameError("They're already gone")
        target.alive = False
        self.votes.clear()
        self.meeting = Meeting(reason="kill", target_id=target_id)
        self.phase = Phase.DISCUSSION
        self._emit("kill", killer_id=killer_id, target_id=target_id, target_name=target.name)
        self._emit("meeting_started", reason="kill", target_id=target_id)
        self._open_discussion()

    def call_meeting(self, player_id: str) -> None:
        """Use one player's single emergency-button meeting (can save a cornered impostor)."""
        self._require_phase(Phase.PLAY, action="call an emergency meeting")
        player = self._player(player_id)
        if not player.alive:
            raise GameError("Ghosts cannot call meetings")
        if player.role is not Role.CREW:
            raise GameError("Impostors cannot call meetings")
        if player.emergency_used:
            raise GameError("No emergency meetings left")
        player.emergency_used = True
        self.votes.clear()
        self.meeting = Meeting(reason="emergency", caller_id=player_id)
        self.phase = Phase.DISCUSSION
        self._emit("meeting_called", caller_id=player_id, caller_name=player.name)
        self._emit("meeting_started", reason="emergency", caller_id=player_id)
        self._open_discussion()

    def _open_discussion(self) -> None:
        self.phase = Phase.DISCUSSION
        self._emit("discussion_started", seconds=self.config.discussion_seconds)
        self._arm_timer(self.config.discussion_seconds, "_open_voting")

    def _open_voting(self) -> None:
        self.votes.clear()
        for player in self.players.values():
            player.vote = None
        self.phase = Phase.VOTING
        self._emit("vote_started", seconds=self.config.voting_seconds)
        self._arm_timer(self.config.voting_seconds, "_tally_if_pending")

    # ── voting ────────────────────────────────────────────────────────────

    def vote(self, player_id: str, target: str) -> None:
        """One anonymous vote (player id or ``skip``) from a living player."""
        self._require_phase(Phase.VOTING, action="vote")
        player = self._player(player_id)
        if not player.alive:
            raise GameError("Ghosts cannot vote")
        if player.vote is not None:
            raise GameError("Vote already cast")
        if target != SKIP_VOTE:
            voted = self.players.get(target)
            if voted is None:
                raise GameError("Unknown voting target")
            if not voted.alive:
                raise GameError("Cannot vote for the dead")
        player.vote = target
        self._emit("vote_casted", player_id=player_id)
        if all(existing.vote is not None for existing in self.players.values() if existing.alive):
            self._tally_votes()

    def _tally_if_pending(self) -> None:
        if self.phase is Phase.VOTING and any(player.vote is None for player in self.players.values() if player.alive):
            self._tally_votes()

    def _tally_votes(self) -> None:
        if self.phase is not Phase.VOTING:
            return
        counts: dict[str, int] = {}
        for player in self.players.values():
            choice = player.vote
            if choice is None or choice == SKIP_VOTE or player.vote is None:
                continue
            counts[choice] = counts.get(choice, 0) + 1
        skipped = sum(1 for player in self.players.values() if player.vote == SKIP_VOTE)
        self._cancel_timer()
        ejected_id: str | None = None
        if counts:
            top = max(counts.values())
            leaders = [player_id for player_id, count in counts.items() if count == top]
            if len(leaders) == 1:
                ejected_id = leaders[0]
        if not ejected_id:
            self._emit("meeting_result", target_id=None, skipped=skipped, votes=counts)
            self._after_tally(None, skipped)
            return
        ejected = self.players[ejected_id]
        ejected.alive = False
        self._emit("meeting_result", target_id=ejected_id, target_name=ejected.name, skipped=skipped, votes=counts)
        self._after_tally(ejected_id, skipped)

    def _after_tally(self, ejected_id: str | None, skipped: int) -> None:
        impostors = self._alive_impostors()
        if not impostors:
            self._end_game(Role.CREW, "all impostors were ejected")
            return
        if len(impostors) >= len(self._alive_crew()):
            self._end_game(Role.IMPOSTOR, "the impostors were left in charge")
            return
        if self.round_number >= self.config.max_rounds:
            self._end_game(Role.IMPOSTOR, "time ran out and the impostor escaped")
            return
        self.phase = Phase.PLAY
        self.meeting = None
        self._arm_timer(0.1, "_start_round_after_meeting")

    def _start_round_after_meeting(self) -> None:
        self._start_round()

    def _check_end_conditions(self) -> None:
        impostors = self._alive_impostors()
        if not impostors:
            self._end_game(Role.CREW, "all impostors were ejected")
        elif len(impostors) >= len(self._alive_crew()):
            self._end_game(Role.IMPOSTOR, "the impostors reached parity with the crew")

    # ── end of game ───────────────────────────────────────────────────────

    def _end_game(self, winner: Role, reason: str) -> None:
        self._cancel_timer()
        self.winner_role = winner
        self.win_reason = reason
        self.phase = Phase.GAME_OVER
        self._emit(
            "game_over",
            winner=winner.value,
            reason=reason,
            roles={
                player_id: player.role.value if player.role else winner.value
                for player_id, player in self.players.items()
            },
        )

    def play_again(self, player_id: str) -> None:
        """Host resets the room to a new lobby for the next game."""
        host = self._host()
        if host is None or host.player_id != player_id:
            raise GameError("Only the host can restart")
        self._require_phase(Phase.GAME_OVER, action="play again")
        for player in list(self.players.values()):
            player.role = None
            player.alive = True
            player.ready = False
            player.task = None
            player.task_done = False
            player.emergency_used = False
            player.vote = None
            player.kill_after_timestamp = 0.0
        self.round_number = 0
        self.meeting = None
        self.winner_role = None
        self.win_reason = ""
        self.roles_revealed = False
        self.phase = Phase.LOBBY
        self._emit("game_reset")

    # ── snapshot (server-rendered per player) ──────────────────────────────

    def public_snapshot(self, observer_id: str) -> dict[str, object]:
        """Serializable view of the whole room for one observer (roles kept private)."""
        players: list[dict[str, object]] = []
        for player in self.players.values():
            entry: dict[str, object] = {
                "player_id": player.player_id,
                "name": player.name,
                "color": player.color,
                "alive": player.alive,
                "online": player.online,
                "is_host": player.is_host,
            }
            if self.phase is Phase.GAME_OVER and self.winner_role is not None:
                entry["role"] = player.role.value if player.role else None
            players.append(entry)

        observer = self.players.get(observer_id)
        you: dict[str, object] = {"player_id": observer_id, "in_game": observer is not None, "is_host": False}
        if observer is not None:
            you["is_host"] = observer.is_host
            you["alive"] = observer.alive
            you["name"] = observer.name
            you["color"] = observer.color
            if self.phase not in (Phase.LOBBY, Phase.GAME_OVER) and observer.role is not None:
                you["role"] = observer.role.value
            you["emergency_left"] = int(observer.emergency_used is False)
            if self.phase is Phase.PLAY:
                you["task"] = observer.task if observer.task_done is False else None
                you["task_done"] = observer.task_done
                you["can_kill"] = observer.role is Role.IMPOSTOR and observer.alive
                if observer.role is Role.IMPOSTOR:
                    you["kill_cd_until"] = max(0.0, observer.kill_after_timestamp - self._now())

        meeting_heading = ""
        meeting_sub = ""
        if self.meeting is not None:
            heading, sub = self.meeting.open_line(self.players)
            meeting_heading = heading
            meeting_sub = sub

        return {
            "phase": self.phase.value,
            "round": self.round_number,
            "max_rounds": self.config.max_rounds,
            "config": {
                "max_players": self.config.max_players,
                "impostor_count": self.config.impostor_count,
                "discussion_seconds": int(self.config.discussion_seconds),
                "voting_seconds": int(self.config.voting_seconds),
                "kill_cooldown_seconds": int(self.config.kill_cooldown_seconds),
                "max_rounds": self.config.max_rounds,
            },
            "host_id": self.host_player_id,
            "roles_seen_count": sum(1 for player in self.players.values() if player.ready),
            "players": players,
            "you": you,
            "voted_count": sum(1 for player in self.players.values() if player.alive and player.vote is not None),
            "winner": self.winner_role.value if self.winner_role is not None else None,
            "win_reason": self.win_reason,
            "meeting_heading": meeting_heading,
            "meeting_sub": meeting_sub,
        }
