"use strict";

const COLORS = ["cyan", "red", "lime", "yellow", "purple", "orange", "pink", "white", "blue", "brown"];

const COLOR_HEX = {
  cyan: "#00e5ff",
  red: "#ff3b5c",
  lime: "#8eff5e",
  yellow: "#ffe94a",
  purple: "#b14dff",
  orange: "#ff9c3b",
  pink: "#ff7eb6",
  white: "#f6f7fa",
  blue: "#3b7dff",
  brown: "#a57149",
};

const PHASE_LABELS = {
  lobby: "Lobby",
  role_reveal: "Secret roles",
  play: "Free play",
  discussion: "Emergency discussion",
  voting: "Voting",
  game_over: "Game over",
};

const store = {
  playerId: "",
  name: "",
  color: "",
  lastPhase: "",
  cdEnd: 0,
  myVoteCast: false,
  ws: null,
};

const screen = document.getElementById("screen");
const phaseLabel = document.getElementById("phase-label");
const roundBadge = document.getElementById("announce-round");
const toasts = document.getElementById("toasts");

function lsGet(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value === null ? fallback : value;
  } catch {
    return fallback;
  }
}

function lsSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore storage failures
  }
}

function showToast(text, isError) {
  const toast = document.createElement("div");
  toast.className = "toast" + (isError ? " error" : "");
  toast.textContent = text;
  toasts.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("show"));
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 300);
  }, 4200);
}

function send(type, payload) {
  if (store.ws && store.ws.readyState === WebSocket.OPEN) {
    store.ws.send(JSON.stringify(Object.assign({ type }, payload || {})));
  }
}

function dot(color) {
  return `<span class="dot" style="background:${COLOR_HEX[color] || "#fff"}"></span>`;
}

function playerTiles(players) {
  return players
    .map(
      (p) =>
        `<div class="tile ${p.alive ? "" : "dead"} ${p.is_host ? "host" : ""}">
          ${dot(p.color)}<span class="name">${escapeHtml(p.name)}</span>
        </div>`
    )
    .join("");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => {
    const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return map[ch];
  });
}

function setScreen(html) {
  screen.innerHTML = html;
}

function setTopbar(snapshot) {
  phaseLabel.textContent = PHASE_LABELS[snapshot.phase] || snapshot.phase;
  if (snapshot.phase === "play" || snapshot.phase === "discussion" || snapshot.phase === "voting") {
    roundBadge.textContent = `Round ${snapshot.round} / ${snapshot.max_rounds}`;
    roundBadge.classList.remove("hidden");
  } else {
    roundBadge.classList.add("hidden");
  }
}

function aliveCount(snapshot) {
  return snapshot.players.filter((p) => p.alive).length;
}

function resetCountdown(snapshot, seconds) {
  store.cdEnd = Date.now() / 1000 + seconds;
}

function renderTimer() {
  const remain = Math.max(0, Math.ceil(store.cdEnd - Date.now() / 1000));
  const timer = document.getElementById("timer");
  const discBtn = document.getElementById("discuss-em-btn");
  if (timer) timer.textContent = remain;
  if (discBtn) discBtn.textContent = store.lastPhase === "voting" ? "Vote now" : `Discuss (${remain}s left)`;
  const skipVote = document.getElementById("skip-vote");
  if (skipVote) skipVote.textContent = `Skip vote (${remain}s)`;
}

function renderLobby(snap) {
  const you = snap.you;
  const cfg = snap.config;
  const host = you.is_host;
  const steppers = [
    ["max_players", "players", 4, 10],
    ["impostor_count", "impostors", 1, 3],
    ["discussion_seconds", "discuss (s)", 15, 180],
    ["voting_seconds", "vote (s)", 10, 120],
    ["kill_cooldown_seconds", "kill cd (s)", 5, 120],
    ["max_rounds", "rounds", 3, 10],
  ]
    .map(
      ([key, label, min, max]) =>
        `<div class="counter">
          <div class="num">${cfg[key]}</div>
          <div class="muted">${label}</div>
          ${host ? `<button class="ghost step-btn" data-key="${key}" data-delta="1" style="width:auto;padding:6px 10px;margin:4px 2px 0">+</button><button class="ghost step-btn" data-key="${key}" data-delta="-1" style="width:auto;padding:6px 10px;margin:4px 2px 0">-</button>` : ""}
        </div>`
    )
    .join("");
  setScreen(`
    <div class="card">
      <p class="eyebrow">Aboard the RV Paragon</p>
      <h2>Lobby</h2>
      <p class="muted">Waiting for players — need at least 4 to launch.</p>
      <div class="grid">${playerTiles(snap.players)}</div>
    </div>
    <div class="card">
      <h3>Setup</h3>
      <div class="counters">${steppers}</div>
      ${host ? '<button id="start-btn">Start the game</button>' : '<p class="statusline">The host will launch the game.</p>'}
    </div>`);
  document.querySelectorAll(".step-btn").forEach((btn) =>
    btn.addEventListener("click", () => {
      const key = btn.dataset.key;
      const delta = Number(btn.dataset.delta);
      send("config", { updates: { [key]: cfg[key] + delta } });
    })
  );
  const startBtn = document.getElementById("start-btn");
  if (startBtn) startBtn.addEventListener("click", () => send("start"));
}

function renderRoleReveal(snap) {
  const you = snap.you;
  const isImpostor = you.role === "impostor";
  setScreen(`
    <div class="card role-reveal ${isImpostor ? "role-impostor" : "role-crew"}">
      <p class="eyebrow">Your secret role</p>
      <div class="role-name">${isImpostor ? "IMPOSTOR" : "CREWMATE"}</div>
      <p class="muted">${isImpostor ? "No one can know. Blend in, kill silently." : "Trust no one. Finish your missions."}</p>
      <button id="ready-btn">I've seen my role</button>
    </div>`);
  document.getElementById("ready-btn").addEventListener("click", () => {
    send("ready");
    document.getElementById("ready-btn").disabled = true;
    document.getElementById("ready-btn").textContent = "Waiting for the crew…";
  });
}

function renderPlay(snap) {
  const you = snap.you;
  const players = snap.players;
  const alive = players.filter((p) => p.alive);
  const dead = players.filter((p) => !p.alive);
  let body = "";
  if (!you.alive) {
    body = `
      <div class="card ghost-screen">
        <h2 class="ghost-title">👻 You are a ghost</h2>
        <p class="muted">You can watch your friends squirm. No killing, no voting.</p>
        <div class="grid">${playerTiles(alive)}</div>
      </div>`;
  } else if (you.role === "impostor") {
    const targets = alive.filter((p) => p.player_id !== you.player_id);
    body = `
      <div class="card role-reveal role-impostor">
        <p class="eyebrow">You are the</p>
        <div class="role-name">IMPOSTOR</div>
        <p class="muted">Kill one crewmate without being caught, or save your skin in the meetings.</p>
      </div>
      <div class="card">
        <h3>Choose your target</h3>
        <select id="kill-target">
          ${targets.map((p) => `<option value="${p.player_id}">${escapeHtml(p.name)}</option>`).join("")}
        </select>
        <button id="kill-btn" class="impostor-btn danger" disabled>Kill (cooldown)</button>
        <p class="statusline">Cooldown: ${cooldownLabel(you)}</p>
      </div>
      <div class="card">
        <h3>Crew status</h3>
        <div class="grid">${playerTiles(alive)}</div>
      </div>`;
  } else {
    body = `
      <div class="card task-box">
        <p class="eyebrow">Your mission this round</p>
        <p class="task">${you.task ? escapeHtml(you.task) : "No mission this round."}</p>
        ${you.task && !you.task_done ? '<button id="task-btn">Mission done</button>' : '<p class="statusline">Mission complete ✅</p>'}
      </div>
      <div class="card">
        <h3>Emergency button</h3>
        <p class="muted">You have ${you.emergency_left} emergency meeting${you.emergency_left === 1 ? "" : "s"} left the whole game.</p>
        <button id="meeting-btn" class="ghost ${you.emergency_left ? "" : "hidden"}">Call an emergency meeting</button>
      </div>
      <div class="card">
        <h3>Crew status</h3>
        <div class="grid">${playerTiles(alive)}</div>
      </div>`;
  }
  if (dead.length) {
    body += `<div class="card"><p class="eyebrow">Lost</p><div class="grid">${playerTiles(dead)}</div></div>`;
  }
  setScreen(body);
  const killBtn = document.getElementById("kill-btn");
  if (killBtn) {
    if (you.kill_cd_until > 0) {
      killBtn.disabled = true;
      killBtn.textContent = `Kill ready in ${Math.ceil(you.kill_cd_until)}s`;
    } else {
      killBtn.disabled = false;
      killBtn.textContent = "Kill";
      killBtn.classList.remove("danger");
    }
    killBtn.addEventListener("click", () => {
      const target = document.getElementById("kill-target").value;
      send("kill", { target });
    });
  }
  const taskBtn = document.getElementById("task-btn");
  if (taskBtn) taskBtn.addEventListener("click", () => send("task_done"));
  const meetingBtn = document.getElementById("meeting-btn");
  if (meetingBtn) meetingBtn.addEventListener("click", () => send("call_meeting"));
}

function cooldownLabel(you) {
  const value = you.kill_cd_until !== undefined ? Math.ceil(you.kill_cd_until) : 0;
  return value > 0 ? `${value}s` : "ready";
}

function renderDiscussion(snap) {
  const alive = snap.players.filter((p) => p.alive);
  setScreen(`
    <div class="card meeting-banner">
      <p class="eyebrow">${escapeHtml(snap.meeting_heading)}</p>
      <h2>${escapeHtml(snap.meeting_sub)}</h2>
      <div id="timer" class="timer">${Math.ceil(store.cdEnd - Date.now() / 1000)}</div>
      <p class="muted">Accuse in person. Your phones will open for voting soon.</p>
    </div>
    <div class="card">
      <h3>Aboard (${alive.length} alive)</h3>
      <div class="grid">${playerTiles(alive)}</div>
    </div>`);
}

function renderVoting(snap) {
  const you = snap.you;
  const alive = snap.players.filter((p) => p.alive && p.player_id !== you.player_id);
  const voters = aliveCount(snap);
  setScreen(`
    <div class="card meeting-banner">
      <p class="eyebrow">The vote is open</p>
      <h2>Who goes out?</h2>
      <div id="timer" class="timer">${Math.ceil(store.cdEnd - Date.now() / 1000)}</div>
      <p class="statusline">${snap.voted_count} / ${voters} have voted</p>
    </div>
    <div class="card">
      ${snap.you.alive ? `
        <h3>Cast your vote</h3>
        <ul class="vote-list">
          ${!store.myVoteCast && alive.length ? alive.map((p) => `
            <li>${dot(p.color)}<span class="name">${escapeHtml(p.name)}</span>
              <button class="vote-btn" data-target="${p.player_id}">Vote</button></li>`).join("") : `<li class="muted">You've voted.</li>`}
        </ul>
        ${!store.myVoteCast ? '<button id="skip-vote" class="ghost">Skip vote</button>' : ""}
      ` : `<p class="muted">Ghosts cannot vote. Sit back and watch.</p>`}
    </div>`);
  document.querySelectorAll(".vote-btn").forEach((btn) =>
    btn.addEventListener("click", () => {
      store.myVoteCast = true;
      send("vote", { target: btn.dataset.target });
      renderVoting(snap);
    })
  );
  const skip = document.getElementById("skip-vote");
  if (skip)
    skip.addEventListener("click", () => {
      store.myVoteCast = true;
      send("vote", { target: "skip" });
      renderVoting(snap);
    });
}

function renderGhost(snap) {
  setScreen(`
    <div class="card ghost-screen">
      <h2>👻 You died</h2>
      <p class="muted">${snap.meeting_heading || "The ship moves on without you."} ${snap.meeting_sub || ""}</p>
      <div class="grid">${playerTiles(snap.players)}</div>
    </div>`);
}

function renderGameOver(snap) {
  const crewWin = snap.winner === "crew";
  const lines = snap.players
    .map(
      (p) =>
        `<div class="tile">
          ${dot(p.color)}<span class="name">${escapeHtml(p.name)}</span>
          <span class="role-tag ${p.role === "impostor" ? "role-impostor" : "role-crew"}">${p.role || "?"}</span>
        </div>`
    )
    .join("");
  setScreen(`
    <div class="card gameover">
      <p class="eyebrow">Final verdict</p>
      <div class="winner ${crewWin ? "win-crew" : "win-impostor"}">${crewWin ? "CREW WINS" : "IMPOSTOR WINS"}</div>
      <p class="muted">${escapeHtml(snap.win_reason)}</p>
    </div>
    <div class="card roles-lineup">
      <h3>The truth about everyone</h3>
      ${lines}
    </div>
    ${snap.you.is_host ? '<button id="again-btn">Play again</button>' : '<p class="statusline">Waiting for the host to restart…</p>'}
  `);
  const again = document.getElementById("again-btn");
  if (again) again.addEventListener("click", () => send("play_again"));
}

function renderLobbyJoining() {
  const remembered = lsGet("imp_name", "");
  const rememberedColor = lsGet("imp_color", "");
  setScreen(`
    <div class="card">
      <p class="eyebrow">Who is the Impostor?</p>
      <h2>Sign in to play</h2>
      <label for="name-input">Your name</label>
      <input id="name-input" maxlength="16" placeholder="Crewmate" value="${escapeHtml(remembered)}" />
      <label>Your color</label>
      <div class="swatches" id="swatches"></div>
      <button id="join-btn">Board the ship</button>
    </div>`);
  const swatches = document.getElementById("swatches");
  COLORS.forEach((color) => {
    const chip = document.createElement("div");
    chip.className = "swatch" + (color === rememberedColor ? " sel" : "");
    chip.style.background = COLOR_HEX[color];
    chip.dataset.color = color;
    chip.addEventListener("click", () => {
      store.color = color;
      swatches.querySelectorAll(".swatch").forEach((s) => s.classList.remove("sel"));
      chip.classList.add("sel");
    });
    swatches.appendChild(chip);
  });
  const joinBtn = document.getElementById("join-btn");
  joinBtn.addEventListener("click", () => {
    store.name = document.getElementById("name-input").value.trim() || "Crewmate";
    store.color = store.color || rememberedColor || COLORS[Math.floor(Math.random() * COLORS.length)];
    lsSet("imp_name", store.name);
    lsSet("imp_color", store.color);
    send("join", { name: store.name, color: store.color, player_id: store.playerId });
  });
}

function render(snapshot) {
  if (snapshot.phase !== store.lastPhase) {
    store.lastPhase = snapshot.phase;
    store.myVoteCast = false;
    if (snapshot.phase === "discussion") resetCountdown(snapshot, snapshot.config.discussion_seconds);
    if (snapshot.phase === "voting") resetCountdown(snapshot, snapshot.config.voting_seconds);
  }
  setTopbar(snapshot);
  if (!snapshot.you.in_game) {
    renderLobbyJoining();
    return;
  }
  switch (snapshot.phase) {
    case "lobby":
      renderLobby(snapshot);
      break;
    case "role_reveal":
      renderRoleReveal(snapshot);
      break;
    case "play":
      renderPlay(snapshot);
      break;
    case "discussion":
      renderDiscussion(snapshot);
      break;
    case "voting":
      renderVoting(snapshot);
      break;
    case "game_over":
      renderGameOver(snapshot);
      break;
    default:
      renderLobbyJoining();
  }
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  store.ws = new WebSocket(`${proto}://${location.host}/ws/game`);

  store.ws.onopen = () => {
    if (store.playerId) {
      send("join", {
        name: lsGet("imp_name", "Crewmate"),
        color: lsGet("imp_color", ""),
        player_id: store.playerId,
      });
    }
  };

  store.ws.onmessage = (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    if (message.type === "hello") {
      store.playerId = message.player_id;
      store.name = message.name;
      store.color = message.color;
      lsSet("imp_id", store.playerId);
    } else if (message.type === "state") {
      render(message.snapshot);
    } else if (message.type === "narration") {
      showToast(message.text);
    } else if (message.type === "error") {
      showToast(message.message, true);
    }
  };

  store.ws.onclose = () => {
    store.myVoteCast = false;
    setTimeout(connect, 1500);
  };
}

setInterval(renderTimer, 500);

const storedId = lsGet("imp_id", "");
if (storedId) {
  store.playerId = storedId;
} else {
  renderLobbyJoining();
}
connect();