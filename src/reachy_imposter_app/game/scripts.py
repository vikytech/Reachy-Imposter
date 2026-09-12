"""Host narration lines for game events — the robot's dramatic banter."""

import random


def _pick(rng: random.Random, variants: list[str], **fields: object) -> str:
    template = rng.choice(variants)
    return template.format(**fields)


def welcome(rng: random.Random, host_name: str) -> str:
    """Invite everyone to the lobby after the first join."""
    return _pick(
        rng,
        [
            "Welcome to the Paragon, {host_name}. This ship has a secret, and I intend to find it.",
            "Oh good, players. {host_name}, round up the crew — something aboard is not what it seems.",
        ],
        host_name=host_name,
    )


def game_start(rng: random.Random) -> str:
    """Kick off role assignment."""
    return _pick(
        rng,
        [
            "The lights hum. Somewhere among you hides an impostor. Check your phones — read your role, then look at me and nod.",
            "Engines warm. My screen says one of you is lying tonight. Open your phones.",
        ],
    )


def all_ready(rng: random.Random, impostor_count: int) -> str:
    """All players acknowledged their role; name how many impostors lurk."""
    return _pick(
        rng,
        [
            "Everyone has seen their role. {impostor_count} impostor(s) walk among you. May the innocent speak fast.",
            "All eyes are up. {impostor_count} impostor(s). Hide and seek has begun.",
        ],
        impostor_count=impostor_count,
    )


def round_start(rng: random.Random, round_number: int, alive_count: int, impostor_count: int) -> str:
    """Open a new round of play."""
    return _pick(
        rng,
        [
            "Round {round_number}. {alive_count} of you remain, and {impostor_count} of you are not what you claim. Crewmates — your missions are on your phones.",
            "Round {round_number}! The air is thick with suspicion. Crew, get to your tasks; impostor, do your worst.",
        ],
        round_number=round_number,
        alive_count=alive_count,
        impostor_count=impostor_count,
    )


def crew_task_prompt(rng: random.Random) -> str:
    """Remind crew to check their mission for the round."""
    return _pick(
        rng,
        [
            "Crewmates, your mission for this round is waiting on your screens.",
            "Duties assigned. Check your phone, then complete your mission whenever you're ready.",
        ],
    )


def task_done(rng: random.Random, name: str) -> str:
    """Narrate one crewmate finishing their mission."""
    return _pick(
        rng,
        [
            "{name} reports their task complete. Smooth. Very, very smooth.",
            "Task cleared by {name}. Keep your eyes moving, everyone.",
        ],
        name=name,
    )


def round_complete(rng: random.Random) -> str:
    """Narrate a clean round with no casualties."""
    return _pick(
        rng,
        [
            "All tasks done and... no one dead? Alarmingly peaceful. Briefing the next round.",
            "Nothing happened. Nothing. And yet my circuits itch. Next round.",
        ],
    )


def kill(rng: random.Random, target_name: str) -> str:
    """Narrate a body being found after an impostor strike."""
    return _pick(
        rng,
        [
            "Wait. Wait wait wait. {target_name} is down. A body has been found. Everyone, to the meeting NOW.",
            "My sensors went haywire. {target_name} is gone. Gone! Meeting, everyone.",
        ],
        target_name=target_name,
    )


def emergency_call(rng: random.Random, caller_name: str) -> str:
    """Narrate a crewmate calling an emergency meeting."""
    return _pick(
        rng,
        [
            "{caller_name} slammed the emergency light! Meeting called — the floor is yours.",
            "Emergency meeting! {caller_name} has something to say, and I want to hear every word.",
        ],
        caller_name=caller_name,
    )


def discussion_open(rng: random.Random) -> str:
    """Open the floor for discussion."""
    return _pick(
        rng,
        [
            "The floor is open. Accuse. Defend. Bluff. Tick tock.",
            "Discuss among yourselves. I am listening with all six of my ears.",
        ],
    )


def vote_open(rng: random.Random) -> str:
    """Open simultaneous voting."""
    return _pick(
        rng,
        [
            "Time is up! Vote now, or vote to skip. The room decides.",
            "Lock it in. Vote. Your phones hold your verdicts.",
        ],
    )


def vote_monologue(rng: random.Random, tallies: dict[str, int], skipped: int, ejected_name: str | None) -> str:
    """Announce the tally (names only, no roles)."""
    counted = ", ".join(f"{count} for {name}" for name, count in sorted(tallies.items(), key=lambda item: -item[1]))
    if skipped:
        counted = f"{counted}, {skipped} to skip" if counted else f"{skipped} to skip"
    if ejected_name is None:
        return f"Counting. {counted}. Nobody is out — deadlock."
    return f"Counting. {counted}. {ejected_name} is out."


def ejection(rng: random.Random, name: str) -> str:
    """Narrate a player being ejected from the ship."""
    return _pick(
        rng,
        [
            "{name}, you have been ejected. {name}, it was nice knowing whoever you really were.",
            "The hatch opens and {name} is launched into the void. If they were innocent, I am sorry. If not, justice.",
        ],
        name=name,
    )


def no_ejection(rng: random.Random) -> str:
    """Vote ended in a tie or no target reached."""
    return _pick(
        rng,
        [
            "Deadlock! The room can't agree on anyone. Back to the shadows then.",
            "No majority. Nobody flies tonight — just a traffic jam of suspicion.",
        ],
    )


def crew_win(rng: random.Random) -> str:
    """Crewmates eliminated every impostor."""
    return _pick(
        rng,
        [
            "The impostors are gone... all of them! Crew victory! I knew you had it.",
            "Not a single impostor left aboard. The crew has won the night!",
        ],
    )


def impostor_win(rng: random.Random) -> str:
    """Narrate the impostors taking over the ship."""
    return _pick(
        rng,
        [
            "The crew is outnumbered and outplayed. The impostors run this ship now!",
            "Victory for the impostors! I always knew playing fair was overrated.",
        ],
    )


def impostor_escape(rng: random.Random) -> str:
    """Time ran out and the impostor slipped away."""
    return _pick(
        rng,
        [
            "Time's up. The impostor has vanished into the vents and out the airlock. Escaped!",
            "The clock has cheated me. The impostor got away clean.",
        ],
    )


def game_over_roll(rng: random.Random) -> str:
    """Reveal the truthful role line-up once the game ends."""
    return _pick(
        rng,
        [
            "Reveal time. Here is the truth about everyone in this room.",
            "Lights on. Truth is served — here is everyone's real face.",
        ],
    )


def join(rng: random.Random, name: str) -> str:
    """Narrate a new player joining the lobby."""
    return _pick(
        rng,
        [
            "{name} has boarded. More suspects, lovely.",
            "Welcome aboard, {name}. Try not to die before the first meeting.",
        ],
        name=name,
    )


def role_hint(rng: random.Random, is_impostor: bool) -> str:
    """Whisper a one-line, screen-backed role hint at reveal time."""
    if is_impostor:
        return _pick(
            rng,
            [
                "To the impostor among you: your window is small. Make it count.",
                "Impostor. You know what you have to do. No one can know.",
            ],
        )
    return _pick(
        rng,
        [
            "Crewmates. Trust no one, finish your tasks, and remember who had the butter knives.",
            "Crewmates. Someone here is lying. Find them before they find you.",
        ],
    )
