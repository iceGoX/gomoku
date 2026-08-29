const BOARD_SIZE = 15;
const EMPTY = 0;
const BLACK = 1;
const WHITE = 2;
const DIRECTIONS = [[1, 0], [0, 1], [1, 1], [1, -1]];
const MAX_FORBIDDEN_DEPTH = 2;
const COLUMNS = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M", "N", "O", "P"];
const SESSION_KEY = "gomoku-room-session";
const APP_BASE = new URL("./", window.location.href);

const elements = {
  lobbyScreen: document.querySelector("#lobbyScreen"),
  waitingScreen: document.querySelector("#waitingScreen"),
  gameScreen: document.querySelector("#gameScreen"),
  homeButton: document.querySelector("#homeButton"),
  rulesButton: document.querySelector("#rulesButton"),
  rulesDialog: document.querySelector("#rulesDialog"),
  resultDialog: document.querySelector("#resultDialog"),
  confirmDialog: document.querySelector("#confirmDialog"),
  confirmResignButton: document.querySelector("#confirmResignButton"),
  modeBadge: document.querySelector("#modeBadge"),
  createForm: document.querySelector("#createForm"),
  joinForm: document.querySelector("#joinForm"),
  createName: document.querySelector("#createName"),
  joinName: document.querySelector("#joinName"),
  joinCode: document.querySelector("#joinCode"),
  lobbyMessage: document.querySelector("#lobbyMessage"),
  offlineButton: document.querySelector("#offlineButton"),
  roomChip: document.querySelector("#roomChip"),
  connectionDot: document.querySelector("#connectionDot"),
  headerRoomCode: document.querySelector("#headerRoomCode"),
  waitingRoomCode: document.querySelector("#waitingRoomCode"),
  copyRoomCodeButton: document.querySelector("#copyRoomCodeButton"),
  seatList: document.querySelector("#seatList"),
  startButton: document.querySelector("#startButton"),
  leaveWaitingButton: document.querySelector("#leaveWaitingButton"),
  waitingMessage: document.querySelector("#waitingMessage"),
  board: document.querySelector("#board"),
  turnStone: document.querySelector("#turnStone"),
  turnEyebrow: document.querySelector("#turnEyebrow"),
  turnTitle: document.querySelector("#turnTitle"),
  turnNumber: document.querySelector("#turnNumber"),
  playerStrip: document.querySelector("#playerStrip"),
  statusLine: document.querySelector("#statusLine"),
  statusText: document.querySelector("#statusText"),
  panelModeTitle: document.querySelector("#panelModeTitle"),
  onlineState: document.querySelector("#onlineState"),
  ruleSummary: document.querySelector("#ruleSummary"),
  previewCard: document.querySelector("#previewCard"),
  previewStone: document.querySelector("#previewStone"),
  previewCoordinate: document.querySelector("#previewCoordinate"),
  previewHint: document.querySelector("#previewHint"),
  confirmButton: document.querySelector("#confirmButton"),
  clearPreviewButton: document.querySelector("#clearPreviewButton"),
  resignButton: document.querySelector("#resignButton"),
  moveCount: document.querySelector("#moveCount"),
  moveList: document.querySelector("#moveList"),
  resultSymbol: document.querySelector("#resultSymbol"),
  resultTitle: document.querySelector("#resultTitle"),
  resultMessage: document.querySelector("#resultMessage"),
  rematchButton: document.querySelector("#rematchButton"),
  resultLobbyButton: document.querySelector("#resultLobbyButton"),
};

const state = {
  transport: "idle",
  localGame: null,
  room: null,
  session: loadSession(),
  preview: null,
  previewAnalysis: null,
  eventAbort: null,
  eventLoopId: 0,
  resultKey: null,
  statusOverride: null,
};

function loadSession() {
  try {
    const value = JSON.parse(sessionStorage.getItem(SESSION_KEY));
    return value?.code && value?.playerId && value?.playerToken ? value : null;
  } catch {
    return null;
  }
}

function saveSession(session) {
  state.session = session;
  if (session) sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  else sessionStorage.removeItem(SESSION_KEY);
}

function selectedMode() {
  return document.querySelector('input[name="gameMode"]:checked')?.value || "normal";
}

function modeLabel(mode) {
  return mode === "professional" ? "专业模式" : "普通模式";
}

function colorLabel(color) {
  return color === BLACK ? "黑方" : "白方";
}

function colorClass(color) {
  return color === BLACK ? "black" : "white";
}

function coordinateLabel(row, col) {
  return `${COLUMNS[col]}${BOARD_SIZE - row}`;
}

function indexOf(row, col) {
  return row * BOARD_SIZE + col;
}

function inBounds(row, col) {
  return row >= 0 && row < BOARD_SIZE && col >= 0 && col < BOARD_SIZE;
}

function valueAt(board, row, col) {
  return inBounds(row, col) ? board[indexOf(row, col)] : -1;
}

function pointKey([row, col]) {
  return `${row},${col}`;
}

function setKey(points) {
  return [...points].map(pointKey).sort().join(";");
}

function lineCoordinates(row, col, dr, dc) {
  let startRow = row;
  let startCol = col;
  while (inBounds(startRow - dr, startCol - dc)) {
    startRow -= dr;
    startCol -= dc;
  }
  const points = [];
  while (inBounds(startRow, startCol)) {
    points.push([startRow, startCol]);
    startRow += dr;
    startCol += dc;
  }
  return points;
}

function contiguousLength(board, row, col, color, dr, dc) {
  let total = 1;
  for (const sign of [-1, 1]) {
    let step = 1;
    while (valueAt(board, row + sign * dr * step, col + sign * dc * step) === color) {
      total += 1;
      step += 1;
    }
  }
  return total;
}

function lineLengths(board, row, col, color) {
  return DIRECTIONS.map(([dr, dc]) => contiguousLength(board, row, col, color, dr, dc));
}

function collectFours(board, row, col) {
  const fours = new Map();
  for (const [dr, dc] of DIRECTIONS) {
    const line = lineCoordinates(row, col, dr, dc);
    const anchor = line.findIndex(([itemRow, itemCol]) => itemRow === row && itemCol === col);
    const first = Math.max(0, anchor - 4);
    const last = Math.min(anchor, line.length - 5);
    for (let start = first; start <= last; start += 1) {
      const window = line.slice(start, start + 5);
      const values = window.map(([itemRow, itemCol]) => valueAt(board, itemRow, itemCol));
      if (values.filter((value) => value === BLACK).length !== 4 || values.filter((value) => value === EMPTY).length !== 1) continue;
      const stones = window.filter((_, index) => values[index] === BLACK);
      if (!stones.some(([itemRow, itemCol]) => itemRow === row && itemCol === col)) continue;
      const emptyIndex = values.indexOf(EMPTY);
      const [winRow, winCol] = window[emptyIndex];
      const trial = [...board];
      trial[indexOf(winRow, winCol)] = BLACK;
      if (contiguousLength(trial, winRow, winCol, BLACK, dr, dc) === 5) fours.set(setKey(stones), stones);
    }
  }
  return fours;
}

function straightFoursContaining(board, anchor, added, dr, dc) {
  const line = lineCoordinates(anchor[0], anchor[1], dr, dc);
  const result = new Map();
  for (let start = 0; start <= line.length - 4; start += 1) {
    const stones = line.slice(start, start + 4);
    const containsAnchor = stones.some(([row, col]) => row === anchor[0] && col === anchor[1]);
    const containsAdded = stones.some(([row, col]) => row === added[0] && col === added[1]);
    if (!containsAnchor || !containsAdded || stones.some(([row, col]) => valueAt(board, row, col) !== BLACK)) continue;
    const before = [stones[0][0] - dr, stones[0][1] - dc];
    const after = [stones[3][0] + dr, stones[3][1] + dc];
    if (valueAt(board, before[0], before[1]) !== EMPTY || valueAt(board, after[0], after[1]) !== EMPTY) continue;
    const beforeTrial = [...board];
    beforeTrial[indexOf(before[0], before[1])] = BLACK;
    const afterTrial = [...board];
    afterTrial[indexOf(after[0], after[1])] = BLACK;
    if (
      contiguousLength(beforeTrial, before[0], before[1], BLACK, dr, dc) === 5
      && contiguousLength(afterTrial, after[0], after[1], BLACK, dr, dc) === 5
    ) result.set(setKey(stones), stones);
  }
  return result;
}

function collectOpenThrees(board, row, col, depth, memo) {
  const threes = new Map();
  const anchor = [row, col];
  for (const [dr, dc] of DIRECTIONS) {
    const line = lineCoordinates(row, col, dr, dc);
    const anchorIndex = line.findIndex(([itemRow, itemCol]) => itemRow === row && itemCol === col);
    const first = Math.max(0, anchorIndex - 4);
    const last = Math.min(line.length, anchorIndex + 5);
    for (let index = first; index < last; index += 1) {
      const candidate = line[index];
      if (valueAt(board, candidate[0], candidate[1]) !== EMPTY) continue;
      const trial = [...board];
      trial[indexOf(candidate[0], candidate[1])] = BLACK;
      if (forbiddenReason(trial, candidate[0], candidate[1], depth + 1, memo)) continue;
      for (const stones of straightFoursContaining(trial, anchor, candidate, dr, dc).values()) {
        const triple = stones.filter(([itemRow, itemCol]) => itemRow !== candidate[0] || itemCol !== candidate[1]);
        if (triple.length === 3 && triple.some(([itemRow, itemCol]) => itemRow === row && itemCol === col)) threes.set(setKey(triple), triple);
      }
    }
  }
  return threes;
}

function forbiddenReason(board, row, col, depth = 0, memo = new Map()) {
  const cacheKey = `${board.join("")}|${row}|${col}|${depth}`;
  if (memo.has(cacheKey)) return memo.get(cacheKey);
  const lengths = lineLengths(board, row, col, BLACK);
  if (lengths.includes(5)) {
    memo.set(cacheKey, null);
    return null;
  }
  if (lengths.some((length) => length >= 6)) {
    memo.set(cacheKey, "OVERLINE");
    return "OVERLINE";
  }
  if (collectFours(board, row, col).size >= 2) {
    memo.set(cacheKey, "DOUBLE_FOUR");
    return "DOUBLE_FOUR";
  }
  if (depth < MAX_FORBIDDEN_DEPTH && collectOpenThrees(board, row, col, depth, memo).size >= 2) {
    memo.set(cacheKey, "DOUBLE_THREE");
    return "DOUBLE_THREE";
  }
  memo.set(cacheKey, null);
  return null;
}

function analyzeMove(board, row, col, color, mode) {
  if (!inBounds(row, col)) return { legal: false, code: "OUT_OF_BOUNDS", message: "落点超出棋盘。" };
  if (valueAt(board, row, col) !== EMPTY) return { legal: false, code: "OCCUPIED", message: "这里已经有棋子。" };
  if (mode === "professional" && color === BLACK && board.every((value) => value === EMPTY) && (row !== 7 || col !== 7)) {
    return { legal: false, code: "CENTER_REQUIRED", message: "专业模式黑方首手必须落在天元。" };
  }
  const trial = [...board];
  trial[indexOf(row, col)] = color;
  const lengths = lineLengths(trial, row, col, color);
  if (mode === "professional" && color === BLACK) {
    const forbidden = forbiddenReason(trial, row, col);
    const messages = {
      OVERLINE: "这是长连禁手，黑方不能落在这里。",
      DOUBLE_FOUR: "这是四四禁手，黑方不能落在这里。",
      DOUBLE_THREE: "这是三三禁手，黑方不能落在这里。",
    };
    if (forbidden) return { legal: false, code: forbidden, message: messages[forbidden] };
    return { legal: true, code: "LEGAL", message: "再次点击确认落子。", wins: lengths.includes(5) };
  }
  return { legal: true, code: "LEGAL", message: "再次点击确认落子。", wins: lengths.some((length) => length >= 5) };
}

function createLocalGame(mode) {
  return {
    mode,
    boardSize: BOARD_SIZE,
    board: Array(BOARD_SIZE * BOARD_SIZE).fill(EMPTY),
    currentColor: BLACK,
    turn: 1,
    status: "playing",
    winnerColor: null,
    resultReason: null,
    lastMove: null,
    moveHistory: [],
  };
}

function placeLocal(row, col) {
  const game = state.localGame;
  const analysis = analyzeMove(game.board, row, col, game.currentColor, game.mode);
  if (!analysis.legal) return { ok: false, message: analysis.message };
  const color = game.currentColor;
  game.board[indexOf(row, col)] = color;
  game.lastMove = [row, col];
  game.moveHistory.push({ turn: game.turn, color, row, col });
  if (analysis.wins) {
    game.status = "finished";
    game.winnerColor = color;
    game.resultReason = "FIVE_IN_A_ROW";
    return { ok: true, message: `${colorLabel(color)}连成五子，获得胜利。` };
  }
  if (game.board.every((value) => value !== EMPTY)) {
    game.status = "finished";
    game.resultReason = "BOARD_FULL";
    return { ok: true, message: "棋盘已满，本局和棋。" };
  }
  game.currentColor = color === BLACK ? WHITE : BLACK;
  game.turn += 1;
  return { ok: true, message: "落子成功" };
}

function currentGame() {
  return state.transport === "offline" ? state.localGame : state.room?.game;
}

function currentPlayer() {
  return state.room?.players?.find((player) => player.id === state.session?.playerId) || null;
}

function canAct() {
  const game = currentGame();
  if (!game || game.status !== "playing") return false;
  if (state.transport === "offline") return true;
  const player = currentPlayer();
  return Boolean(player && player.color === game.currentColor);
}

function apiUrl(path) {
  return new URL(`api/${path.replace(/^\//, "")}`, APP_BASE).toString();
}

async function apiRequest(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.session) {
    headers["X-Player-Id"] = state.session.playerId;
    headers["X-Player-Token"] = state.session.playerToken;
  }
  const response = await fetch(apiUrl(path), { method: "POST", ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.message || "请求失败，请稍后再试。");
    error.data = data;
    throw error;
  }
  return data;
}

function setStatus(message, error = false) {
  state.statusOverride = { message, error };
  elements.statusText.textContent = message;
  elements.statusLine.classList.toggle("error", error);
}

function clearStatusOverride() {
  state.statusOverride = null;
}

function showScreen(name) {
  document.body.dataset.screen = name;
  elements.lobbyScreen.classList.toggle("hidden", name !== "lobby");
  elements.waitingScreen.classList.toggle("hidden", name !== "waiting");
  elements.gameScreen.classList.toggle("hidden", name !== "game");
}

function createBoard() {
  const stars = new Set(["3,3", "3,11", "7,7", "11,3", "11,11"]);
  const fragment = document.createDocumentFragment();
  for (let row = 0; row < BOARD_SIZE; row += 1) {
    for (let col = 0; col < BOARD_SIZE; col += 1) {
      const button = document.createElement("button");
      button.className = "intersection";
      button.type = "button";
      button.dataset.row = String(row);
      button.dataset.col = String(col);
      button.setAttribute("role", "gridcell");
      button.setAttribute("aria-label", coordinateLabel(row, col));
      if (stars.has(`${row},${col}`)) {
        button.classList.add("star");
        const dot = document.createElement("span");
        dot.className = "star-dot";
        button.append(dot);
      }
      button.addEventListener("click", () => handleIntersection(row, col));
      fragment.append(button);
    }
  }
  elements.board.append(fragment);
}

function renderBoard() {
  const game = currentGame();
  if (!game) return;
  for (const button of elements.board.children) {
    const row = Number(button.dataset.row);
    const col = Number(button.dataset.col);
    button.querySelectorAll(".stone").forEach((stone) => stone.remove());
    const value = game.board[indexOf(row, col)];
    const isPreview = state.preview?.row === row && state.preview?.col === col;
    if (value !== EMPTY) {
      const stone = document.createElement("span");
      stone.className = `stone ${colorClass(value)}`;
      if (game.lastMove?.[0] === row && game.lastMove?.[1] === col) stone.classList.add("last");
      button.append(stone);
      button.setAttribute("aria-label", `${coordinateLabel(row, col)}，${colorLabel(value)}棋子`);
    } else if (isPreview) {
      const stone = document.createElement("span");
      stone.className = `stone ${colorClass(game.currentColor)} ghost`;
      if (!state.previewAnalysis?.legal) stone.classList.add("illegal");
      button.append(stone);
      button.setAttribute("aria-label", `${coordinateLabel(row, col)}，待确认${colorLabel(game.currentColor)}棋子`);
    } else {
      button.setAttribute("aria-label", `${coordinateLabel(row, col)}，空位`);
    }
    button.disabled = value !== EMPTY || game.status !== "playing";
  }
}

function renderPlayers() {
  const game = currentGame();
  if (!game) return;
  let players;
  if (state.transport === "offline") {
    players = [
      { color: BLACK, name: "本机 · 黑方", connected: true },
      { color: WHITE, name: "本机 · 白方", connected: true },
    ];
  } else {
    players = state.room.players;
  }
  elements.playerStrip.innerHTML = players.map((player) => {
    const active = game.currentColor === player.color && game.status === "playing";
    const status = state.transport === "offline" ? (active ? "当前回合" : "等待回合") : `${player.connected ? "在线" : "离线"}${active ? " · 当前回合" : ""}`;
    return `<div class="player-card${active ? " active" : ""}"><span class="seat-stone ${colorClass(player.color)}"></span><span><strong>${escapeHtml(player.name)}</strong><small>${status}</small></span></div>`;
  }).join("");
}

function renderTurn() {
  const game = currentGame();
  if (!game) return;
  const color = game.currentColor;
  elements.turnStone.className = `turn-stone ${colorClass(color)}`;
  elements.turnNumber.textContent = String(game.turn).padStart(2, "0");
  if (game.status === "finished") {
    elements.turnEyebrow.textContent = "MATCH FINISHED";
    elements.turnTitle.textContent = game.winnerColor ? `${colorLabel(game.winnerColor)}获胜` : "本局和棋";
  } else if (canAct()) {
    elements.turnEyebrow.textContent = state.transport === "offline" ? "LOCAL TURN" : "YOUR TURN";
    elements.turnTitle.textContent = `${colorLabel(color)}，请选择落点`;
  } else {
    elements.turnEyebrow.textContent = "OPPONENT TURN";
    const player = state.room?.players?.find((item) => item.color === color);
    elements.turnTitle.textContent = `等待 ${player?.name || colorLabel(color)} 落子`;
  }
}

function renderRules() {
  const game = currentGame();
  if (!game) return;
  const professional = game.mode === "professional";
  elements.panelModeTitle.textContent = modeLabel(game.mode);
  elements.onlineState.textContent = state.transport === "offline" ? "离线本地" : "在线房间";
  elements.ruleSummary.innerHTML = professional
    ? "<p><b>1</b><span>黑方首手必须落在正中央天元。</span></p><p><b>2</b><span>黑方三三、四四、六子及以上长连为禁手。</span></p><p><b>3</b><span>黑方恰好五连获胜；白方五连或长连获胜。</span></p>"
    : "<p><b>1</b><span>黑白双方交替在任意空交叉点落子。</span></p><p><b>2</b><span>横、竖或斜线连成五子及以上即胜。</span></p><p><b>3</b><span>双方都没有三三、四四或长连限制。</span></p>";
}

function renderPreview() {
  const game = currentGame();
  if (!game) return;
  elements.previewStone.className = `preview-stone ${colorClass(game.currentColor)}`;
  if (!state.preview) {
    elements.previewCoordinate.textContent = "尚未选择";
    elements.previewHint.textContent = canAct() ? "点击棋盘上的空交叉点" : "等待对方完成落子";
    elements.previewCard.classList.remove("illegal");
    elements.confirmButton.disabled = true;
    elements.clearPreviewButton.disabled = true;
    return;
  }
  elements.previewCoordinate.textContent = coordinateLabel(state.preview.row, state.preview.col);
  elements.previewHint.textContent = state.previewAnalysis?.message || "再次点击确认落子。";
  elements.previewCard.classList.toggle("illegal", !state.previewAnalysis?.legal);
  elements.confirmButton.disabled = !state.previewAnalysis?.legal;
  elements.clearPreviewButton.disabled = false;
}

function renderMoveLog() {
  const game = currentGame();
  if (!game) return;
  const moves = game.moveHistory || [];
  elements.moveCount.textContent = `${moves.length} 手`;
  if (!moves.length) {
    elements.moveList.innerHTML = '<li class="empty-log">棋局开始后会记录坐标</li>';
    return;
  }
  elements.moveList.innerHTML = [...moves].reverse().slice(0, 16).map((move) => `<li><i class="${colorClass(move.color)}"></i><span>${colorLabel(move.color)} · ${coordinateLabel(move.row, move.col)}</span><time>#${String(move.turn).padStart(2, "0")}</time></li>`).join("");
}

function renderStatus() {
  if (state.statusOverride) {
    setStatus(state.statusOverride.message, state.statusOverride.error);
    return;
  }
  const game = currentGame();
  if (!game) return;
  if (game.status === "finished") setStatus("本局已经结束，可选择再来一局或返回大厅。", false);
  else if (!canAct()) setStatus("当前是对方回合，棋盘将在对方落子后自动同步。", false);
  else if (state.preview) setStatus(state.previewAnalysis?.message || "再次点击同一位置确认落子。", !state.previewAnalysis?.legal);
  else setStatus("第一次点击预览虚子，第二次点击同一位置确认落子。", false);
}

function renderGame() {
  const game = currentGame();
  if (!game) return;
  if (elements.resultDialog.open && game.status === "playing") elements.resultDialog.close();
  renderTurn();
  renderPlayers();
  renderRules();
  renderBoard();
  renderPreview();
  renderMoveLog();
  renderStatus();
  maybeShowResult();
}

function renderWaiting() {
  if (!state.room) return;
  elements.waitingRoomCode.textContent = state.room.code;
  elements.headerRoomCode.textContent = state.room.code;
  elements.roomChip.classList.remove("hidden");
  const colors = [BLACK, WHITE];
  elements.seatList.innerHTML = colors.map((color) => {
    const player = state.room.players.find((item) => item.color === color);
    if (!player) return `<div class="seat empty"><span class="seat-stone ${colorClass(color)}"></span><span><strong>等待${colorLabel(color)}加入</strong><small>空位</small></span></div>`;
    return `<div class="seat"><span class="seat-stone ${colorClass(color)}"></span><span><strong>${escapeHtml(player.name)}</strong><small>${player.isHost ? "房主" : "已入席"}${player.connected ? " · 在线" : ""}</small></span></div>`;
  }).join("");
  const me = currentPlayer();
  const ready = state.room.players.length === 2;
  elements.startButton.disabled = !me?.isHost || !ready;
  elements.startButton.textContent = !me?.isHost ? "等待房主开始" : ready ? "开始对局" : "等待玩家加入";
  elements.waitingMessage.textContent = state.room.lastEvent?.message || "";
}

function renderRoom() {
  if (!state.room) return;
  elements.headerRoomCode.textContent = state.room.code;
  elements.roomChip.classList.remove("hidden");
  if (state.room.status === "waiting") {
    state.preview = null;
    showScreen("waiting");
    renderWaiting();
  } else if (state.room.game) {
    showScreen("game");
    renderGame();
  }
}

function handleIntersection(row, col) {
  const game = currentGame();
  if (!game || !canAct()) {
    setStatus("当前不能落子，请等待自己的回合。", true);
    return;
  }
  if (valueAt(game.board, row, col) !== EMPTY) return;
  if (state.preview?.row === row && state.preview?.col === col) {
    if (state.previewAnalysis?.legal) confirmMove();
    else setStatus(state.previewAnalysis?.message || "这个落点不合法。", true);
    return;
  }
  state.preview = { row, col };
  state.previewAnalysis = analyzeMove(game.board, row, col, game.currentColor, game.mode);
  clearStatusOverride();
  renderGame();
}

async function confirmMove() {
  if (!state.preview || !state.previewAnalysis?.legal) return;
  const { row, col } = state.preview;
  elements.confirmButton.disabled = true;
  if (state.transport === "offline") {
    const result = placeLocal(row, col);
    state.preview = null;
    state.previewAnalysis = null;
    clearStatusOverride();
    if (!result.ok) setStatus(result.message, true);
    renderGame();
    return;
  }
  try {
    const result = await apiRequest(`rooms/${state.room.code}/place`, {
      body: JSON.stringify({ row, col, expectedVersion: state.room.version }),
    });
    state.room = result.room;
    state.preview = null;
    state.previewAnalysis = null;
    clearStatusOverride();
    renderRoom();
  } catch (error) {
    if (error.data?.room) state.room = error.data.room;
    setStatus(error.message, true);
    renderRoom();
  }
}

function clearPreview() {
  state.preview = null;
  state.previewAnalysis = null;
  clearStatusOverride();
  renderGame();
}

function maybeShowResult() {
  const game = currentGame();
  if (!game || game.status !== "finished") return;
  const key = `${state.transport}:${state.room?.version || game.moveHistory.length}:${game.resultReason}:${game.winnerColor}`;
  if (state.resultKey === key) return;
  state.resultKey = key;
  if (game.winnerColor) {
    elements.resultSymbol.textContent = game.winnerColor === BLACK ? "●" : "○";
    elements.resultTitle.textContent = `${colorLabel(game.winnerColor)}获胜`;
    elements.resultMessage.textContent = game.resultReason === "RESIGN" ? "对方认输，本局立即结束。" : "连成五子，本局结束。";
  } else {
    elements.resultSymbol.textContent = "和";
    elements.resultTitle.textContent = "本局和棋";
    elements.resultMessage.textContent = "棋盘已满，双方均未形成有效胜局。";
  }
  if (state.transport === "online") {
    const voted = state.room.rematchVotes?.includes(state.session.playerId);
    elements.rematchButton.textContent = voted ? "已邀请，等待对方" : "邀请再来一局";
    elements.rematchButton.disabled = voted;
  } else {
    elements.rematchButton.textContent = "再来一局";
    elements.rematchButton.disabled = false;
  }
  if (!elements.resultDialog.open) elements.resultDialog.showModal();
}

function startOffline(mode = selectedMode()) {
  stopEventLoop();
  saveSession(null);
  state.transport = "offline";
  state.room = null;
  state.localGame = createLocalGame(mode);
  state.preview = null;
  state.previewAnalysis = null;
  state.resultKey = null;
  clearStatusOverride();
  elements.roomChip.classList.add("hidden");
  showScreen("game");
  renderGame();
}

async function createRoom(event) {
  event.preventDefault();
  elements.lobbyMessage.textContent = "";
  try {
    const result = await apiRequest("rooms", {
      body: JSON.stringify({ name: elements.createName.value.trim(), mode: selectedMode() }),
    });
    saveSession({ code: result.room.code, playerId: result.playerId, playerToken: result.playerToken });
    state.transport = "online";
    state.room = result.room;
    startEventLoop();
    renderRoom();
  } catch (error) {
    elements.lobbyMessage.textContent = error.message;
  }
}

async function joinRoom(event) {
  event.preventDefault();
  elements.lobbyMessage.textContent = "";
  const code = elements.joinCode.value.trim().toUpperCase();
  try {
    const result = await apiRequest(`rooms/${code}/join`, {
      body: JSON.stringify({ name: elements.joinName.value.trim() }),
    });
    saveSession({ code: result.room.code, playerId: result.playerId, playerToken: result.playerToken });
    state.transport = "online";
    state.room = result.room;
    startEventLoop();
    renderRoom();
  } catch (error) {
    elements.lobbyMessage.textContent = error.message;
  }
}

async function startRoom() {
  elements.startButton.disabled = true;
  elements.waitingMessage.textContent = "正在开始对局…";
  try {
    const result = await apiRequest(`rooms/${state.room.code}/start`, { body: "{}" });
    state.room = result.room;
    renderRoom();
  } catch (error) {
    elements.waitingMessage.textContent = error.message;
    renderWaiting();
  }
}

function setConnection(online) {
  elements.connectionDot.classList.toggle("online", online);
}

function stopEventLoop() {
  state.eventLoopId += 1;
  state.eventAbort?.abort();
  state.eventAbort = null;
  setConnection(false);
}

async function startEventLoop() {
  stopEventLoop();
  if (!state.session) return;
  const loopId = state.eventLoopId;
  const controller = new AbortController();
  state.eventAbort = controller;
  while (state.session && loopId === state.eventLoopId && !controller.signal.aborted) {
    try {
      const response = await fetch(apiUrl(`rooms/${state.session.code}/events`), {
        headers: {
          "X-Player-Id": state.session.playerId,
          "X-Player-Token": state.session.playerToken,
        },
        signal: controller.signal,
      });
      if (!response.ok || !response.body) throw new Error(response.status === 401 ? "玩家身份已失效。" : "实时连接失败。" );
      setConnection(true);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (!controller.signal.aborted) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const event of events) {
          const dataLine = event.split("\n").find((line) => line.startsWith("data: "));
          if (!dataLine) continue;
          const room = JSON.parse(dataLine.slice(6));
          const previousTurn = state.room?.game?.turn;
          state.room = room;
          if (previousTurn !== room.game?.turn) {
            state.preview = null;
            state.previewAnalysis = null;
            clearStatusOverride();
          }
          renderRoom();
        }
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      setConnection(false);
      if (error.message.includes("身份")) {
        saveSession(null);
        state.room = null;
        state.transport = "idle";
        elements.roomChip.classList.add("hidden");
        elements.lobbyMessage.textContent = "房间身份已失效，请重新创建或加入。";
        showScreen("lobby");
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1800));
    }
  }
}

async function leaveRoom() {
  const session = state.session;
  const room = state.room;
  if (session && room) {
    try {
      await apiRequest(`rooms/${room.code}/leave`, { body: "{}" });
    } catch {
      // The local identity is still cleared even if the room is already gone.
    }
  }
  stopEventLoop();
  saveSession(null);
  state.room = null;
  state.localGame = null;
  state.transport = "idle";
  state.preview = null;
  state.previewAnalysis = null;
  state.resultKey = null;
  elements.roomChip.classList.add("hidden");
  if (elements.resultDialog.open) elements.resultDialog.close();
  showScreen("lobby");
}

async function resignGame() {
  if (state.transport === "offline") {
    const game = state.localGame;
    game.status = "finished";
    game.winnerColor = game.currentColor === BLACK ? WHITE : BLACK;
    game.resultReason = "RESIGN";
    state.preview = null;
    state.previewAnalysis = null;
    renderGame();
    return;
  }
  try {
    const result = await apiRequest(`rooms/${state.room.code}/resign`, { body: "{}" });
    state.room = result.room;
    state.preview = null;
    state.previewAnalysis = null;
    renderRoom();
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function rematch() {
  const game = currentGame();
  if (!game) return;
  if (state.transport === "offline") {
    state.localGame = createLocalGame(game.mode);
    state.preview = null;
    state.previewAnalysis = null;
    state.resultKey = null;
    elements.resultDialog.close();
    clearStatusOverride();
    renderGame();
    return;
  }
  elements.rematchButton.disabled = true;
  try {
    const result = await apiRequest(`rooms/${state.room.code}/rematch`, { body: "{}" });
    state.room = result.room;
    state.resultKey = null;
    if (result.room.status === "playing") elements.resultDialog.close();
    renderRoom();
  } catch (error) {
    elements.resultMessage.textContent = error.message;
    elements.rematchButton.disabled = false;
  }
}

async function copyRoomCode() {
  const code = state.room?.code;
  if (!code) return;
  try {
    await navigator.clipboard.writeText(code);
    if (state.room.status === "waiting") elements.waitingMessage.textContent = `房间号 ${code} 已复制。`;
    else setStatus(`房间号 ${code} 已复制。`, false);
  } catch {
    if (state.room.status === "waiting") elements.waitingMessage.textContent = `房间号：${code}`;
    else setStatus(`房间号：${code}`, false);
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function bindEvents() {
  document.querySelectorAll('input[name="gameMode"]').forEach((input) => input.addEventListener("change", () => {
    elements.modeBadge.textContent = selectedMode() === "professional" ? "专业" : "普通";
  }));
  document.querySelectorAll(".online-tab").forEach((button) => button.addEventListener("click", () => {
    document.querySelectorAll(".online-tab").forEach((item) => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-selected", String(active));
    });
    elements.createForm.classList.toggle("hidden", button.dataset.tab !== "create");
    elements.joinForm.classList.toggle("hidden", button.dataset.tab !== "join");
    elements.lobbyMessage.textContent = "";
  }));
  elements.createForm.addEventListener("submit", createRoom);
  elements.joinForm.addEventListener("submit", joinRoom);
  elements.joinCode.addEventListener("input", () => { elements.joinCode.value = elements.joinCode.value.toUpperCase().replace(/[^A-Z2-9]/g, ""); });
  elements.offlineButton.addEventListener("click", () => startOffline());
  elements.startButton.addEventListener("click", startRoom);
  elements.leaveWaitingButton.addEventListener("click", leaveRoom);
  elements.homeButton.addEventListener("click", leaveRoom);
  elements.roomChip.addEventListener("click", copyRoomCode);
  elements.copyRoomCodeButton.addEventListener("click", copyRoomCode);
  elements.rulesButton.addEventListener("click", () => elements.rulesDialog.showModal());
  elements.confirmButton.addEventListener("click", confirmMove);
  elements.clearPreviewButton.addEventListener("click", clearPreview);
  elements.resignButton.addEventListener("click", () => elements.confirmDialog.showModal());
  elements.confirmResignButton.addEventListener("click", resignGame);
  elements.rematchButton.addEventListener("click", rematch);
  elements.resultLobbyButton.addEventListener("click", leaveRoom);
  window.addEventListener("keydown", (event) => {
    if (event.key === "?" && !elements.rulesDialog.open) elements.rulesDialog.showModal();
    if (event.key === "Escape" && state.preview && !elements.rulesDialog.open && !elements.confirmDialog.open) clearPreview();
    if (event.key === "Enter" && state.previewAnalysis?.legal && !elements.resultDialog.open) confirmMove();
  });
}

async function restoreSession() {
  if (!state.session) return;
  state.transport = "online";
  elements.roomChip.classList.remove("hidden");
  elements.headerRoomCode.textContent = state.session.code;
  showScreen("waiting");
  elements.waitingRoomCode.textContent = state.session.code;
  elements.waitingMessage.textContent = "正在恢复房间状态…";
  startEventLoop();
}

createBoard();
bindEvents();
restoreSession();
