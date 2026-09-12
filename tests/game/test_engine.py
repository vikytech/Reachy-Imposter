"""Headless rules tests for the Imposter game engine."""

import random
import asyncio
from dataclasses import replace

import pytest

from reachy_imposter_app.game.engine import GameError, ImposterGame
from reachy_imposter_app.game.models import MAX_PLAYERS, MIN_PLAYERS, Role, Phase


def _make_game(**config_overrides) -> ImposterGame:
    game = ImposterGame(rng=random.Random(42))
    game.config = replace(game.config, **config_overrides)
    game.role_reveal_delay_s = 0.0
    return game


def _join(game: ImposterGame, count: int, prefix: str = "p") -> list[str]:
    ids = []
    for index in range(count):
        player_id = f"{prefix}{index}"
        game.join(player_id, prefix.capitalize() + str(index), "cyan")
        ids.append(player_id)
    return ids


async def _start(game: ImposterGame) -> None:
    game.start(game.host_player_id or "")
    for player_id in list(game.players):
        game.ready(player_id)
    await _wait_phase(game, Phase.PLAY)


async def _wait_until(predicate, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if predicate():
            return
        if loop.time() > deadline:
            raise AssertionError("Condition not met in time")
        await asyncio.sleep(0.01)


async def _wait_phase(game: ImposterGame, phase: Phase) -> None:
    await _wait_until(lambda: game.phase is phase)


async def _vote_for(game: ImposterGame, voters: list[str], target: str) -> None:
    for player_id in voters:
        if game.players[player_id].alive and game.players[player_id].vote is None:
            game.vote(player_id, target)
    await _wait_until(lambda: game.phase is not Phase.VOTING)


@pytest.mark.asyncio
async def test_host_is_first_joiner() -> None:
    """The first online player becomes the host."""
    game = _make_game()
    ids = _join(game, 3)
    assert game.host_player_id == ids[0]


@pytest.mark.asyncio
async def test_join_deduplicates_names() -> None:
    """A second player borrowing a name gets a numeric suffix."""
    game = _make_game()
    game.join("a", "Ava", "red")
    game.join("b", "Ava", "blue")
    assert [player.name for player in game.players.values()] == ["Ava", "Ava 2"]


@pytest.mark.asyncio
async def test_join_during_game_is_rejected() -> None:
    """Joining after the game left the lobby is refused."""
    game = _make_game()
    _join(game, MIN_PLAYERS)
    await _start(game)
    with pytest.raises(GameError):
        game.join("late", "Late", "red")


@pytest.mark.asyncio
async def test_start_requires_four_players() -> None:
    """The host cannot start with fewer than four players."""
    game = _make_game()
    _join(game, 3)
    with pytest.raises(GameError, match="Need at least"):
        game.start(game.host_player_id or "")


@pytest.mark.asyncio
async def test_start_requires_host() -> None:
    """Only the host may start the game."""
    game = _make_game()
    _join(game, 4)
    with pytest.raises(GameError, match="Only the host"):
        game.start(game.players["p1"].player_id)


@pytest.mark.asyncio
async def test_start_assigns_roles_and_moves_to_play() -> None:
    """Every player gets a role and one round opens."""
    game = _make_game()
    ids = _join(game, 5)
    events: list[str] = []
    game.set_emitter(lambda game_event: events.append(game_event.kind))
    await _start(game)
    assert game.phase is Phase.PLAY
    assert game.round_number == 1
    roles = {game.players[player_id].role for player_id in ids}
    assert roles == {Role.CREW, Role.IMPOSTOR}
    impostors = [player for player in game.players.values() if player.role is Role.IMPOSTOR]
    assert all(player.task is None for player in impostors)
    assert all(player.task is not None for player in game.players.values() if player.role is Role.CREW)
    assert "round_started" in events


@pytest.mark.asyncio
async def test_config_updates_are_host_only_and_range_checked() -> None:
    """Config edits are host-only and range-checked."""
    game = _make_game()
    _join(game, 4)
    with pytest.raises(GameError, match="Only the host"):
        game.update_config(game.players["p1"].player_id, {"max_players": 10})
    with pytest.raises(GameError, match="between"):
        game.update_config(game.host_player_id or "", {"max_players": 99})
    game.update_config(game.host_player_id or "", {"max_players": 6})
    assert game.config.max_players == 6
    assert game.config.max_players <= MAX_PLAYERS


@pytest.mark.asyncio
async def test_kill_requires_impostor_and_opens_meeting() -> None:
    """An impostor kill removes the target and raises a meeting."""
    game = _make_game(kill_cooldown_seconds=0.01)
    ids = _join(game, 4)
    await _start(game)
    target = next(player_id for player_id in ids if game.players[player_id].role is Role.CREW)
    killer = next(player_id for player_id in ids if game.players[player_id].role is Role.IMPOSTOR)
    game.players[killer].kill_after_timestamp = 0.0
    game.request_kill(killer, target)
    assert not game.players[target].alive
    assert game.phase is Phase.DISCUSSION
    assert game.meeting is not None and game.meeting.reason == "kill"


@pytest.mark.asyncio
async def test_kill_respects_cooldown() -> None:
    """A kill inside the cooldown window is refused."""
    game = _make_game(kill_cooldown_seconds=1.0)
    _join(game, 4)
    await _start(game)
    killer = next(player_id for player_id in game.players if game.players[player_id].role is Role.IMPOSTOR)
    victim = next(player_id for player_id in game.players if game.players[player_id].role is Role.CREW)
    with pytest.raises(GameError, match="cooldown"):
        game.request_kill(killer, victim)


@pytest.mark.asyncio
async def test_crewmate_cannot_kill() -> None:
    """Crewmates have no kill power."""
    game = _make_game()
    _join(game, 4)
    await _start(game)
    crew = next(player_id for player_id in game.players if game.players[player_id].role is Role.CREW)
    other = next(
        player_id for player_id in game.players if game.players[player_id].role is Role.CREW and player_id != crew
    )
    with pytest.raises(GameError, match="Only the impostor"):
        game.request_kill(crew, other)


@pytest.mark.asyncio
async def test_emergency_meeting_once_per_character() -> None:
    """One emergency meeting per crewmate per game."""
    game = _make_game(discussion_seconds=0.02, voting_seconds=0.02)
    ids = _join(game, 4)
    await _start(game)
    crew = next(player_id for player_id in ids if game.players[player_id].role is Role.CREW)
    game.call_meeting(crew)
    assert game.phase is Phase.DISCUSSION
    assert game.players[crew].emergency_used
    await _wait_phase(game, Phase.VOTING)
    for player_id in ids:
        if game.players[player_id].alive:
            game.vote(player_id, "skip")
    await _wait_phase(game, Phase.PLAY)
    with pytest.raises(GameError, match="No emergency"):
        game.call_meeting(crew)


@pytest.mark.asyncio
async def test_impostor_cannot_call_meeting() -> None:
    """Only crewmates can hit the emergency button."""
    game = _make_game()
    _join(game, 4)
    await _start(game)
    killer = next(player_id for player_id in game.players if game.players[player_id].role is Role.IMPOSTOR)
    with pytest.raises(GameError, match="Impostors cannot"):
        game.call_meeting(killer)


@pytest.mark.asyncio
async def test_crew_wins_when_impostor_ejected() -> None:
    """Ejecting the last impostor ends the game for the crew."""
    game = _make_game(discussion_seconds=0.02, voting_seconds=0.02)
    ids = _join(game, 5)
    await _start(game)
    killer = next(player_id for player_id in ids if game.players[player_id].role is Role.IMPOSTOR)
    game.players[killer].kill_after_timestamp = 0.0
    victim = next(player_id for player_id in ids if game.players[player_id].role is Role.CREW)
    game.request_kill(killer, victim)
    await _wait_phase(game, Phase.VOTING)
    crew_alive = [pid for pid in ids if game.players[pid].alive and pid != killer]
    await _vote_for(game, crew_alive, killer)
    assert game.phase is Phase.GAME_OVER
    assert game.winner_role is Role.CREW
    assert not game.players[killer].alive


@pytest.mark.asyncio
async def test_deadlock_overrides_ejection() -> None:
    """A split vote evicts nobody and the game rolls to a new round."""
    game = _make_game(discussion_seconds=0.02, voting_seconds=0.02)
    ids = _join(game, 4)
    await _start(game)
    killer = next(player_id for player_id in ids if game.players[player_id].role is Role.IMPOSTOR)
    game.players[killer].kill_after_timestamp = 0.0
    victim = next(player_id for player_id in ids if game.players[player_id].role is Role.CREW)
    game.request_kill(killer, victim)
    await _wait_phase(game, Phase.VOTING)
    bystanders = [player_id for player_id in ids if game.players[player_id].alive and player_id != killer]
    game.vote(killer, bystanders[0])
    game.vote(bystanders[0], killer)
    game.vote(bystanders[1], "skip")
    await _wait_until(lambda: game.round_number == 2)
    assert game.phase is Phase.PLAY
    assert game.meeting is None


@pytest.mark.asyncio
async def test_parity_wins_for_impostors() -> None:
    """Impostors win once they match or outnumber the crew."""
    game = _make_game(impostor_count=2, discussion_seconds=0.02, voting_seconds=0.02)
    ids = _join(game, 5)
    await _start(game)
    impostors = [pid for pid in ids if game.players[pid].role is Role.IMPOSTOR]
    assert len(impostors) == 2
    killer = impostors[0]
    game.players[killer].kill_after_timestamp = 0.0
    victim = next(pid for pid in ids if game.players[pid].role is Role.CREW)
    game.request_kill(killer, victim)
    await _wait_phase(game, Phase.VOTING)
    crew_target = next(pid for pid in ids if game.players[pid].role is Role.CREW and game.players[pid].alive)
    for player_id in ids:
        if game.players[player_id].alive:
            game.vote(player_id, crew_target)
    await _wait_phase(game, Phase.GAME_OVER)
    assert game.winner_role is Role.IMPOSTOR


@pytest.mark.asyncio
async def test_voting_rejects_duplicate_and_dead_targets() -> None:
    """Casting twice or naming a corpse is refused."""
    game = _make_game(discussion_seconds=0.02, voting_seconds=2.0)
    ids = _join(game, 4)
    await _start(game)
    killer = next(player_id for player_id in ids if game.players[player_id].role is Role.IMPOSTOR)
    game.players[killer].kill_after_timestamp = 0.0
    victim = next(player_id for player_id in ids if game.players[player_id].role is Role.CREW)
    game.request_kill(killer, victim)
    await _wait_phase(game, Phase.VOTING)
    crew_other = next(player_id for player_id in ids if player_id not in (killer, victim))
    crew_third = next(player_id for player_id in ids if player_id not in (killer, victim, crew_other))
    game.vote(killer, crew_other)
    with pytest.raises(GameError, match="already"):
        game.vote(killer, crew_other)
    with pytest.raises(GameError, match="Cannot vote for the dead"):
        game.vote(crew_third, victim)


@pytest.mark.asyncio
async def test_ghost_cannot_vote() -> None:
    """Dead players cannot cast a vote."""
    game = _make_game(discussion_seconds=0.02, voting_seconds=2.0)
    ids = _join(game, 4)
    await _start(game)
    killer = next(player_id for player_id in ids if game.players[player_id].role is Role.IMPOSTOR)
    game.players[killer].kill_after_timestamp = 0.0
    victim = next(player_id for player_id in ids if game.players[player_id].role is Role.CREW)
    game.request_kill(killer, victim)
    await _wait_phase(game, Phase.VOTING)
    with pytest.raises(GameError, match="Ghosts cannot vote"):
        game.vote(victim, killer)


@pytest.mark.asyncio
async def test_impostor_escapes_when_rounds_exhausted() -> None:
    """Losing the clock hands the win to the impostor."""
    game = _make_game(max_rounds=1, kill_cooldown_seconds=999.0)
    _join(game, 4)
    await _start(game)
    for player_id in list(game.players):
        if game.players[player_id].role is Role.CREW:
            game.complete_task(player_id)
    await _wait_phase(game, Phase.GAME_OVER)
    assert game.winner_role is Role.IMPOSTOR


@pytest.mark.asyncio
async def test_snapshot_exposes_player_ids() -> None:
    """Every player entry carries its id so kill and vote targets resolve."""
    game = _make_game()
    ids = _join(game, 4)
    snap = game.public_snapshot(ids[0])
    observed = [entry["player_id"] for entry in snap["players"]]
    assert sorted(observed) == sorted(ids)


@pytest.mark.asyncio
async def test_snapshot_hides_roles_until_game_over() -> None:
    """Other players' roles stay hidden until the reveal."""
    game = _make_game(max_rounds=1, kill_cooldown_seconds=999.0)
    ids = _join(game, 4)
    await _start(game)
    first = ids[0]
    snap = game.public_snapshot(first)
    assert snap["phase"] == "play"
    assert snap["players"][0]["alive"]
    for entry in snap["players"]:
        assert "role" not in entry
    assert "role" in snap["you"]
    for player_id in list(game.players):
        if game.players[player_id].role is Role.CREW:
            game.complete_task(player_id)
    await _wait_phase(game, Phase.GAME_OVER)
    ending = game.public_snapshot(first)
    assert ending["winner"] == "impostor"
    assert all("role" in entry for entry in ending["players"])
