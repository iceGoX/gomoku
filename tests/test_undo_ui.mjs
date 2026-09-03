import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createContext, runInContext } from "node:vm";

const source = readFileSync(new URL("../game.js", import.meta.url), "utf8");
const label = (remaining) => `请求悔棋（剩余 ${remaining} 次）`;

function element(fragment = false) {
  const classes = new Set();
  const attributes = new Map();
  return {
    fragment, dataset: {}, children: [], className: "", textContent: "", innerHTML: "",
    disabled: false, open: false,
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      toggle(name, force = !classes.has(name)) {
        if (force) classes.add(name);
        else classes.delete(name);
        return force;
      },
    },
    append(child) {
      if (child.fragment) child.children.forEach((item) => this.append(item));
      else {
        this.children.push(child);
        child.parent = this;
      }
    },
    remove() { this.parent.children = this.parent.children.filter((child) => child !== this); },
    querySelectorAll(selector) {
      return this.children.filter((child) => child.className.split(" ").includes(selector.slice(1)));
    },
    setAttribute(name, value) { attributes.set(name, value); },
    getAttribute(name) { return attributes.get(name); },
    addEventListener() {},
    showModal() { this.open = true; },
    close() { this.open = false; },
  };
}

function loadGame({ playerId = "black", moves = [[7, 7]], local = false } = {}) {
  const nodes = new Map();
  const context = createContext({
    URL,
    window: { location: { href: "http://gomoku.test/" }, addEventListener() {} },
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    document: {
      body: element(),
      querySelector(selector) {
        if (!nodes.has(selector)) nodes.set(selector, element());
        return nodes.get(selector);
      },
      querySelectorAll: () => [],
      createElement: () => element(),
      createDocumentFragment: () => element(true),
    },
    fetch: async () => { throw new Error("Unexpected network request"); },
  });
  runInContext(`${source}\nglobalThis.app = {
    state, elements, createLocalGame, placeLocal, startOffline, canAct, undoActionState,
    renderUndoAction, renderGame, renderStatus, requestUndo, respondToUndo, applyRoomUpdate, setStatus,
  };`, context);
  const app = context.app;
  const game = app.createLocalGame("normal");
  app.state.transport = "offline";
  app.state.localGame = game;
  for (const [row, col] of moves) assert.equal(app.placeLocal(row, col).ok, true);
  if (!local) {
    app.state.transport = "online";
    app.state.session = { playerId, playerToken: "test-token", code: "ABC234" };
    app.state.room = {
      code: "ABC234", mode: "normal", status: "playing", version: moves.length + 3,
      players: [
        { id: "black", color: 1, name: "黑方", isHost: true, connected: true },
        { id: "white", color: 2, name: "白方", isHost: false, connected: true },
      ],
      undo: { requestPlayerId: null, uses: { black: 0, white: 0 } },
      rematchVotes: [], seatSwapRequestPlayerId: null, game,
    };
  }
  app.setFetch = (fetch) => { context.fetch = fetch; };
  return app;
}

function expectButton(app, remaining, disabled) {
  app.renderUndoAction();
  assert.equal(app.elements.undoButton.textContent, label(remaining));
  assert.equal(app.elements.undoButton.disabled, disabled);
}

function snapshot(app, requesterId) {
  const room = structuredClone(app.state.room);
  room.version += 1;
  room.undo.requestPlayerId = requesterId;
  return room;
}

function response(room) {
  return { ok: true, json: async () => ({ room }) };
}

test("empty board keeps the same label and disables undo for either player", () => {
  for (const playerId of ["black", "white"]) {
    expectButton(loadGame({ playerId, moves: [] }), 2, true);
  }
});

test("turns change availability, never the undo action label", () => {
  const app = loadGame();
  expectButton(app, 2, false);
  app.state.session.playerId = "white";
  expectButton(app, 2, true);
  assert.equal(app.placeLocal(7, 8).ok, true);
  expectButton(app, 2, false);
  app.state.session.playerId = "black";
  expectButton(app, 2, true);
});

test("own turn cannot issue undo even through the click handler", async () => {
  const app = loadGame({ playerId: "white" });
  let calls = 0;
  app.setFetch(async () => { calls += 1; });
  await app.requestUndo();
  assert.equal(calls, 0);
  expectButton(app, 2, true);
});

test("only the requester gets a cancel button, and only the opponent gets the dialog", () => {
  const app = loadGame();
  app.applyRoomUpdate(snapshot(app, "black"));
  app.renderGame();
  assert.equal(app.elements.undoButton.textContent, "取消悔棋请求");
  assert.equal(app.elements.undoButton.disabled, false);
  assert.equal(app.elements.undoRequestDialog.open, false);
  assert.match(app.elements.statusText.textContent, /等待对方确认/);
  app.state.session.playerId = "white";
  app.renderGame();
  expectButton(app, 2, true);
  assert.equal(app.elements.undoRequestDialog.open, true);
  assert.equal(app.elements.approveUndoButton.disabled, false);
  assert.equal(app.elements.rejectUndoButton.disabled, false);
  assert.match(app.elements.statusText.textContent, /请在弹窗中处理/);
  assert.equal(app.elements.turnTitle.textContent, "悔棋确认中");
  assert.equal(app.elements.previewHint.textContent, "请先处理悔棋请求");
  assert.equal(app.canAct(), false);
  assert.equal(app.elements.board.children.every((button) => button.disabled), true);
});

test("normal status is not cached and request changes replace stale hints without a new turn", () => {
  const app = loadGame({ playerId: "white" });
  app.renderStatus();
  assert.equal(app.state.statusOverride, null);
  app.state.preview = { row: 7, col: 8 };
  app.state.previewAnalysis = { legal: true };
  app.setStatus("旧的提示", true);
  const turn = app.state.room.game.turn;
  app.applyRoomUpdate(snapshot(app, "black"));
  app.renderGame();
  assert.equal(app.state.room.game.turn, turn);
  assert.equal(app.state.preview, null);
  assert.equal(app.state.statusOverride, null);
  assert.match(app.elements.statusText.textContent, /请在弹窗中处理/);
  app.applyRoomUpdate(snapshot(app, null));
  app.renderGame();
  assert.equal(app.elements.undoRequestDialog.open, false);
  assert.doesNotMatch(app.elements.statusText.textContent, /悔棋|等待/);
  assert.equal(app.canAct(), true);
});

test("quota exhaustion and game completion disable undo without renaming it", () => {
  const app = loadGame();
  app.state.room.undo.uses.black = 2;
  expectButton(app, 0, true);
  app.state.room.undo.uses.black = 1;
  app.state.room.game.status = "finished";
  app.state.room.status = "finished";
  expectButton(app, 1, true);
});

test("a player with no undo uses left can still approve the opponent's request", () => {
  const app = loadGame({ playerId: "white" });
  app.state.room.undo.uses.white = 2;
  app.applyRoomUpdate(snapshot(app, "black"));
  app.renderGame();
  expectButton(app, 0, true);
  assert.equal(app.elements.approveUndoButton.disabled, false);
  assert.equal(app.elements.undoRequestDialog.open, true);
});

test("request submission stays locked through rerenders and ignores a second click", async () => {
  const app = loadGame();
  const pending = snapshot(app, "black");
  let calls = 0;
  let resolve;
  app.setFetch(() => {
    calls += 1;
    return new Promise((done) => { resolve = done; });
  });
  const request = app.requestUndo();
  expectButton(app, 2, true);
  app.renderGame();
  await app.requestUndo();
  assert.equal(calls, 1);
  app.applyRoomUpdate(pending);
  app.renderGame();
  assert.equal(app.elements.undoButton.disabled, true);
  resolve(response(pending));
  await request;
  assert.equal(app.elements.undoButton.textContent, "取消悔棋请求");
  assert.equal(app.elements.undoButton.disabled, false);
  assert.equal(app.state.room.undo.uses.black, 0);
});

test("failed request recovers the original action and quota", async () => {
  const app = loadGame();
  app.setFetch(async () => { throw new Error("连接失败"); });
  await app.requestUndo();
  expectButton(app, 2, false);
  assert.equal(app.state.undoInFlight, null);
  assert.equal(app.elements.statusText.textContent, "连接失败");
});

test("confirmation stays visible and disabled until the server accepts", async () => {
  const app = loadGame({ playerId: "white" });
  app.applyRoomUpdate(snapshot(app, "black"));
  const accepted = snapshot(app, null);
  accepted.game.board[7 * 15 + 7] = 0;
  accepted.game.moveHistory = [];
  accepted.game.lastMove = null;
  accepted.game.currentColor = 1;
  accepted.game.turn = 1;
  accepted.undo.uses.black = 1;
  let resolve;
  let calls = 0;
  app.setFetch((_url, options) => {
    assert.equal(JSON.parse(options.body).decision, "accept");
    calls += 1;
    return new Promise((done) => { resolve = done; });
  });
  const decision = app.respondToUndo("accept");
  app.renderGame();
  assert.equal(app.elements.undoRequestDialog.open, true);
  assert.equal(app.elements.approveUndoButton.disabled, true);
  assert.equal(app.elements.rejectUndoButton.disabled, true);
  await app.respondToUndo("accept");
  assert.equal(calls, 1);
  resolve(response(accepted));
  await decision;
  assert.equal(app.elements.undoRequestDialog.open, false);
  expectButton(app, 2, true);
  app.state.session.playerId = "black";
  expectButton(app, 1, true);
  assert.equal(app.canAct(), true);
});

test("late snapshots cannot resurrect a resolved request", () => {
  const app = loadGame({ playerId: "white" });
  const pending = snapshot(app, "black");
  app.applyRoomUpdate(pending);
  const resolved = snapshot(app, null);
  app.applyRoomUpdate(resolved);
  assert.equal(app.applyRoomUpdate(pending), false);
  app.renderGame();
  assert.equal(app.elements.undoRequestDialog.open, false);
  assert.equal(app.state.room.version, resolved.version);
  expectButton(app, 2, true);
});

test("offline approval spends the last mover's quota, rejection and cancellation do not", async () => {
  const app = loadGame({ local: true });
  await app.requestUndo();
  assert.equal(app.state.localGame.undoRequest.requesterColor, 1);
  assert.match(app.elements.statusText.textContent, /白方确认/);
  await app.respondToUndo("reject");
  expectButton(app, 2, false);
  await app.requestUndo();
  await app.requestUndo();
  expectButton(app, 2, false);
  await app.requestUndo();
  await app.respondToUndo("accept");
  assert.equal(app.state.localGame.moveHistory.length, 0);
  assert.equal(app.state.localGame.undoUses[1], 1);
  assert.equal(app.state.localGame.undoUses[2], 0);
  expectButton(app, 1, true);
  assert.equal(app.placeLocal(7, 7).ok, true);
  expectButton(app, 1, false);
  await app.requestUndo();
  await app.respondToUndo("accept");
  assert.equal(app.placeLocal(7, 7).ok, true);
  expectButton(app, 0, true);
  await app.requestUndo();
  assert.equal(app.state.localGame.undoRequest, null);
  app.startOffline("normal");
  expectButton(app, 2, true);
});
