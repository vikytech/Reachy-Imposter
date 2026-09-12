# Installing & Running Reachy Imposter (first-time guide)

Reachy Imposter turns your Reachy Mini into a social-deduction party game (like
Among Us, with a real robot): players join a lobby from their phones, vote each
other out, and the robot narrates, moves, and chats over voice.

Two ways to run it:

- **Part 1 — on your computer with the simulator** (no robot needed): quickest
  way to see it work and to develop.
- **Part 2 — standalone on the real Reachy Mini** (no laptop needed at runtime):
  the robot runs everything; players just open a URL from their phones.

---

## Prerequisites

- Python 3.10+ and [uv](https://docs.astral.sh/uv/) on your computer (for dev /
  building the package).
- A Reachy Mini (wireless) robot with its daemon running (Part 2 only).
- A Hugging Face token for the realtime voice backend. Put it in `.env` as
  `HF_TOKEN` (or `huggingface-cli login` on the robot). The game itself works
  without it; speaking/listening does not.

---

## Part 1 — Quick start on your computer (simulator)

```bash
# 1. Clone and install the app
git clone <your-repo-url> Reachy-Imposter
cd Reachy-Imposter
uv sync

# 2. Configure the Hugging Face backend token
cp .env.example .env        # then set HF_TOKEN=<your token> inside .env

# 3. Start a simulated robot daemon (no hardware, no audio)
.env_local/bin/reachy-mini-daemon --mockup-sim --headless --no-media --log-level INFO

# 4. In a second terminal, start the app
.env_local/bin/reachy-imposter-app --ui
```

Wait ~15 s for the log line `Web UI available at http://localhost:7860`, then
open http://localhost:7860/ — it redirects straight to the **game lobby**.
Open the same URL in a few extra browser windows (incognito counts as separate
players), and play.

> `--ui` launches the web game at port 7860. Without it the app runs headless
> (no web page) — you don't want that here.

---

## Part 2 — Standalone on the real robot

### 2.1 Build the package

```bash
uv build
# produces dist/reachy_imposter_app-1.0.1-py3-none-any.whl
```

### 2.2 Copy it to the robot

Find your robot's IP (router page, `ping reachy-mini.local`, or Reachy Mini
Desktop). Then:

```bash
scp dist/*.whl root@<robot-ip>:/tmp/
```

### 2.3 Install it into the daemon's `apps_venv` (this is what makes it visible)

The daemon only lists apps registered as `reachy_mini_apps` **Python entry
points inside the shared `apps_venv`** — not the daemon's own venv, not global
pip. Installing into the wrong place is the #1 cause of "installed but not in
the app list".

```bash
ssh root@<robot-ip>

# Find the daemon's venv, then the sibling apps_venv the daemon scans
which reachy-mini-daemon
# e.g. /opt/reachy/.venv/bin/reachy-mini-daemon  ->  apps_venv is /opt/reachy/apps_venv

APPS=/venvs/apps_venv

# Install the wheel into apps_venv
$APPS/bin/pip install /tmp/reachy_imposter_app-*.whl
# or:  uv pip install --python $APPS/bin/python /tmp/reachy_imposter_app-*.whl

# Verify the entry point is registered (must print ['reachy_imposter_app'])
$APPS/bin/python -c "from importlib.metadata import entry_points; print([ep.name for ep in entry_points(group='reachy_mini_apps')])"
```

Restart the daemon (or reopen Reachy Mini Desktop). The app now appears under
**Installed** apps in the desktop app.

### 2.4 Launch it

Either:

- In **Reachy Mini Desktop**: pick `reachy_imposter_app` from the installed app
  list and Start. Or
- Over SSH: `reachy-imposter-app --ui`

### 2.5 Play from phones — no laptop needed

The app serves on `0.0.0.0:7860`. Every player on the same WiFi opens:

```
http://<robot-ip>:7860/
```

(It redirects to the `/game` lobby automatically.) The first phone to join is
the **host** and sets the game up from the lobby; ready up, and the robot
starts narrating and playing along.

### 2.6 (Optional) Auto-start at boot

Configure the daemon to install + launch the app whenever it starts:

```bash
# ~/.config/reachy_mini/daemon_config.json on the robot
{
  "startup_app": "reachy_imposter_app"
}
```

Then the app comes up by itself after the robot boots — nobody ever presses
anything.

---

## Playing the game

1. Each player opens `http://<robot-ip>:7860/` on their phone (one tab per
   person; a phone and a tab are separate "players").
2. The **first joiner is the host**: adjust the setup (player count, impostor
   probability, meeting/vote timings) from the lobby — host-only.
3. Everyone taps **Ready**; the game starts a hidden-roles round. The robot
   narrates each event out loud.
4. During meetings, players vote to eject the impostor. Mis-votes cost the
   crew; the impostor escapes if the crew runs out of rounds.
5. The conversation backend lets you also just *talk* to the robot (its
   personality lives in `profiles/_reachy_imposter_app_locked_profile/profile.md`).

---

## Configuration reference

| Variable | Purpose | Default |
|---|---|---|
| `HF_TOKEN` | Token for the deployed realtime voice backend | required for voice |
| `HF_REALTIME_CONNECTION_MODE` | `deployed` (HF cloud) or `local` (LAN backend) | `deployed` |
| `HF_REALTIME_WS_URL` | Direct realtime URL, only for `local` mode | — |
| `REALTIME_TRANSCRIPTION_LANGUAGE` | STT language code | `en` |
| `REACHY_MINI_APP_TIMEOUT_MINUTES` | Idle minutes before robot sleeps; `0` disables | `1440` |

CLI flags (`reachy-imposter-app --help`):

| Flag | What it does |
|---|---|
| `--ui` | Serve the web UI at `:7860` (always use this) |
| `--no-camera` | Skip the camera |
| `--debug` | Verbose logging |
| `--robot-name <name>` | Match a daemon's `--robot-name` when connecting over the network (only needed for laptop→robot with several robots; irrelevant when the app runs on the robot itself) |

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| App installed but **not in the app list** | Installed into the wrong Python env. Must be `apps_venv` with the `reachy_mini_apps` entry point registered (see 2.3, verify with the one-liner). |
| Legacy **"Failed to validate/save key"** page | Old onboarding UI was replaced: `/` now redirects to `/game`. Nothing to enter — just open the base URL. |
| `zeroconf - ... No route to host` in daemon logs | Non-fatal mDNS advertisement warning on your network. Ignore it for on-robot use; it only affects discovery from a laptop. |
| `Audio system is not initialized` warnings | Expected under `--no-media` (simulator). On the real robot audio is present. The warning loop itself was fixed. |
| App can't connect to the daemon | App on the robot = automatic (localhost). From a laptop, make `reachy-mini.local` resolve (add `http://<robot-ip> reachy-mini.local` to `/etc/hosts`) or use `--robot-name` matching the daemon. |
| Voice doesn't work, game still does | `HF_TOKEN` missing/unset on the robot. The lobby is independent of the voice backend. |

---

## Development checks

Run the full gate before handing work back:

```bash
ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v
```