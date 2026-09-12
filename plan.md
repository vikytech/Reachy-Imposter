# Reachy Imposter — plan

Reachy Mini hosts a real-world "Who is the impostor?" party game (Among-Us
style) with friends in the same room. Players connect with their phones over
LAN; Reachy secretly assigns roles, runs rounds, announces events, and the
robot narrates with an LLM-driven, talking host personality.

## Confirmed decisions

| Question                | Answer                          |
|-------------------------|---------------------------------|
| Flavour                 | Python app + browser UI         |
| Game style              | Real-world party game           |
| Dead player view        | Yes — ghosts can watch the game |
| LLM narration           | Yes — talking, joking host      |

## Understanding

- Friends all in the same room; each opens a URL on their phone
  (`http://reachy-mini.local:8000`) and joins the game with a name.
- Robot secretly assigns roles: **Crew** vs **Impostor(s)**.
- During a round, players wander the room. The impostor picks a victim on
  their phone to "kill" them (with cooldown) — Reachy breaks the news.
- Crew can call an emergency meeting or find a body → Reachy hosts a meeting,
  everyone discusses, then votes simultaneously on phones.
- Reachy tallies votes, ejects a player, and keeps the game loop going until
  crew or impostor side wins.
- Killed/ejected players switch to a ghost screen and keep watching state.
- Reachy narrates the whole thing: role reveal, kills, meetings, suspense,
  jokes — via LLM + TTS, with offline scripted fallbacks.

## Technical approach

1. Scaffold with `reachy-mini-app-assistant` using the **conversation
   template** (LLM magic + speech already wired in), published at
   `Reachy-Imposter`.
2. Game architecture:
   - FastAPI daemon already listens on `:8000`; we mount our own
     routes/websockets for the game layer (`/api`, `/ws`) alongside the
     static `static/` UI served to phones.
   - A **game state machine** on the robot owns: lobby/join → role
     assignment → in-game rounds → meetings → voting → resolution → game over.
     Drives motion side-effects on every transition.
   - A **player session** per phone (name + color + role + alive/dead + vote)
     keeps state in the robot's memory — authoritative host, not on the phone.
   - **WebSocket** to each phone: private role reveal, personal mortal
     actions (kill, cut), game events, voting.
3. Motion/behaviors (all `goto_target()`, gestures ≥0.5s):
   - Happy/curious/defiant poses for role reveal, kills, ejections.
   - Suspicious side-to-side sway during meetings.
   - Relief pose at crew victory; taunting spin at impostor victory.
   - Head gaze / antenna lifts for pointing at speakers.
4. LLM host:
   - Conversation template's TTS + LLM pipeline, with a system prompt giving
     Reachy a host persona and a typed "game event" hook so it comments
     appropriately (kill, eject, tie, victory).
   - Deterministic scripted fallback lines if offline/LLM fails.
5. Testing (see `skills/testing-apps.md`): fake game script the robot runs
   solo with simulated players; validate state transitions headlessly before
   the real party.

## Confirmed game mechanics

- **Crew tasks**: yes — Reachy hands crew a silly physical task each round
  (10 jumping jacks, sing a tune, flip a coin till heads…).
- **Emergency meetings**: yes — each crew member gets 1 per game.
- **Counts**: configurable per game in the lobby (Reachy hosts and picks).
- **Network**: wireless/LAN — friends join at `reachy-mini.local:8000`.

## Next steps

Scaffold with `reachy-mini-app-assistant` (conversation template) once the
tool is available, then implement the game state machine + UI + motion +
LLM host, then test headlessly.

## Implementation design (agreed)

Everything lives inside the scaffolded `reachy_imposter_app`:

- `src/reachy_imposter_app/game/` — new package
  - `models.py` — `Role`, `Phase`, `GameConfig`, `Player`, `GameEvent`
  - `engine.py` — `ImposterGame`: authoritative asyncio state machine
    (lobby → role reveal → rounds → meetings/kill/vote → game over), emits
    typed events. Pure logic, no robot/web deps → headless-testable.
  - `tasks.py` — silly physical crew tasks pool
  - `scripts.py` — narration line generators (host banter)
  - `motion.py` — event → emotion/gaze `GotoQueueMove`/`EmotionQueueMove`
  - `narrator.py` — `GameNarrator`: subscribes to engine events → robot
    speech (`handler.say` via the stream event loop) + motion + on-screen
    narration for players (covers offline fallback)
  - `server.py` — `GameServer` (per-player websockets, per-player private
    state render, host detection/transfer) + `register_game_routes()`:
    `GET /game` UI + `WS /ws/game`
- `tools/game_status.py` — LLM tool so the talking host answers questions
  from real game state (never invented facts); added to the locked profile.
- `profiles/_reachy_imposter_app_locked_profile/profile.md` — rewritten
  persona: Reachy = dramatic gameshow host of the game.
- `static/game/` — mobile-first player UI: join → lobby (host config + QR +
  join URL) → secret role → task / kill pad → meeting discussion → voting →
  ghost spectator → game over. Vanilla JS + WebSocket, offline-capable
  (vendored QR lib, no CDN at runtime).
- `main.py` — builds engine+narrator+server, wires `schedule_say()` onto the
  stream loop, registers routes on the settings app (served at
  `http://reachy-mini.local:8000/game`).
- `tests/game/test_engine.py` — headless rule tests (joins, roles, kill
  rules + cooldown, meetings, voting/tie/ejection, win conditions, round cap,
  ghosts).

Gate before handoff: `ruff check . --fix && ruff format . && mypy
--pretty --show-error-codes && pytest tests/ -v`.