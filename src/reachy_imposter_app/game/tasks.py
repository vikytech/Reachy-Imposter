"""Silly physical crew tasks handed out to crewmates each round."""

from __future__ import annotations
import random


_CREW_TASKS: tuple[str, ...] = (
    "Do 10 jumping jacks without anyone catching you resting.",
    "Flip a coin until it lands heads, then loudly announce your victory.",
    "Hum a random song's chorus. Let the room guess the song.",
    "Whisper your most embarrassing fact to the person next to you.",
    "Stand up, spin three times, and sit back down like nothing happened.",
    "Tell the room one lie that is obviously a lie in a deadpan voice.",
    "Count backwards from 20 out loud at a dramatic pace.",
    "Do 5 push-ups (or the armchair version). Reachy is watching.",
    "Say 'sus' in your most serious voice at least 3 times.",
    "Stare at the wall for 10 full seconds without blinking, then blink slowly.",
    "Name 3 ice cream flavors that sound like they could be spaceship names.",
    "Make a victory pose and hold it for 5 seconds.",
    "Walk to the other side of the room and back with a completely straight face.",
    "Say the alphabet backwards as fast as you can.",
    "Invent a handshake with the nearest person.",
    "Mime opening the most dramatic door you can imagine.",
    "Whisper 'the vents are clean' to a random player and walk away.",
    "Do 10 squats while counting them in a different voice each time.",
    "Describe your favorite food using only grunts and gestures.",
    "Balance like a flamingo for 10 seconds without wobbling.",
    "Sing one line from a song you know by heart, then pretend it never happened.",
    "Throw three invisible grenades, each with a different sound effect.",
    "Whisper a recipe to the nearest player, step by step, without moving your lips.",
    "Do a dramatic slow-motion walk across the room.",
    "Speak only in rhyming couplets until the crew moves on.",
    "Name five planets in order, getting more dramatic with each one.",
    "Pretend you dropped something invisible, pick it up, and pocket it.",
    "Congratulate each player on a different made-up achievement.",
    "Count the ceiling lights out loud and report a suspiciously specific total.",
    "Give the nearest object a dramatic backstory in one sentence.",
    "Do your best robot impression for 10 seconds and end with a beep.",
    "Invent a secret code phrase and teach it to only one other player.",
)


def assign_task(rng: random.Random, seen_tasks: list[str], round_used: set[str]) -> str:
    """Pick a crew task not handed to this player recently or to anyone this round."""
    pool = [task for task in _CREW_TASKS if task not in seen_tasks and task not in round_used]
    if not pool:
        pool = [task for task in _CREW_TASKS if task not in round_used]
    if not pool:
        pool = list(_CREW_TASKS)
    chosen = rng.choice(pool)
    if len(seen_tasks) >= 6:
        del seen_tasks[0]
    seen_tasks.append(chosen)
    round_used.add(chosen)
    return chosen
