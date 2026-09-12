---
title: Reachy Imposter App
emoji: 🤖
colorFrom: purple
colorTo: gray
sdk: static
pinned: false
tags:
  - reachy_mini
  - reachy_mini_python_app
---

# Reachy Imposter App

Forked from the Reachy Mini conversation app.

> **New here?** Read [`INSTALL.md`](INSTALL.md): it walks through running the
> app on the simulator, installing it standalone on the robot (with the exact
> `apps_venv` + entry-point steps), playing, and troubleshooting.

Customize `profiles/_reachy_imposter_app_locked_profile/profile.md` to change the assistant instructions and enabled tools.
Add custom tools under `src/reachy_imposter_app/tools/` by subclassing `Tool`.

Do not forget to customize:
- this `README.md` file
- the `index.html` file (Hugging Face Spaces landing page)
- the `src/reachy_imposter_app/static/game/index.html` (the game lobby page)

The original README from the conversation app is available in `README_OLD.md`.