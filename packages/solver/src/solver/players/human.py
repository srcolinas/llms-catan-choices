"""A seat that waits for a click on the local board page."""

from __future__ import annotations

import contextvars
import json
import threading
import time
import webbrowser
from collections.abc import Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from simulation import Board, Edge, PriorPlacement, Vertex
from solver.board_view import BOARD_CSS, BOARD_JS
from solver.dataset import board_record
from solver.settings import Settings

game_seed: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "game_seed",
    default=None,
)


@dataclass
class _Row:
    seed: int
    status: str = "queued"
    board: dict[str, Any] | None = None
    placements: list[dict[str, Any]] = field(default_factory=list)
    pairs: list[tuple[Vertex, Edge]] = field(default_factory=list)
    seat: int | None = None
    errors: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    choice: tuple[Vertex, Edge] | None = None
    waiting: threading.Event | None = None
    choice_taken: bool = False


class HumanTable:
    """One page for every row in a batch, shared by the worker threads."""

    def __init__(self, heuristics: str, *, beat: float = 0.4) -> None:
        self.heuristics = heuristics
        self.beat = beat
        self.url = ""
        self._lock = threading.Lock()
        self._rows: dict[int, _Row] = {}
        self._order: list[int] = []
        self._version = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def prepare(self, seeds: Sequence[int]) -> None:
        with self._lock:
            for seed in seeds:
                self._ensure(seed)

    def begin(self, seed: int, board: Board) -> None:
        recorded = board_record(board)
        with self._lock:
            row = self._ensure(seed)
            row.board = recorded
            self._version += 1

    def note_waiting_random(self, seed: int) -> None:
        with self._lock:
            row = self._ensure(seed)
            row.status = "waiting_random"
            row.pairs = []
            row.errors = []
            row.choice_taken = False
            row.history.append("waiting_random")
            self._version += 1
        self._pause()

    def note_placement(
        self,
        seed: int,
        seat: int,
        vertex: Vertex,
        edge: Edge,
        kind: str,
    ) -> None:
        with self._lock:
            row = self._ensure(seed)
            row.placements.append(
                {
                    "seat": seat,
                    "kind": kind,
                    "vertex": _coordinate(vertex),
                    "edge": _coordinate(edge),
                }
            )
            self._version += 1

    def wait_human(
        self,
        seed: int,
        seat: int,
        available: list[tuple[Vertex, Edge]],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        event = threading.Event()
        with self._lock:
            row = self._ensure(seed)
            if errors:
                _retract(row, seat)
            row.status = "pending_human"
            row.seat = seat
            row.pairs = list(available)
            row.errors = list(errors)
            row.choice = None
            row.choice_taken = False
            row.waiting = event
            row.history.append("pending_human")
            self._version += 1
        event.wait()
        with self._lock:
            row = self._rows[seed]
            choice = row.choice
            row.waiting = None
            row.choice = None
        if choice is None:
            raise RuntimeError(f"human choice for seed {seed} was cleared")
        return choice

    def submit(self, payload: object) -> str | None:
        parsed = _parse_submission(payload)
        if isinstance(parsed, str):
            return parsed
        seed, vertex, edge = parsed
        with self._lock:
            row = self._rows.get(seed)
            if row is None or row.status != "pending_human" or row.choice_taken:
                return "this row is not waiting for you"
            match = _match_pair(row.pairs, vertex, edge)
            if match is None:
                return "not a legal placement"
            row.choice_taken = True
            row.choice = match
            event = row.waiting
            self._version += 1
        if event is not None:
            event.set()
        return None

    def finish(self, seed: int, *, ok: bool) -> None:
        with self._lock:
            row = self._ensure(seed)
            row.status = "done" if ok else "failed"
            row.pairs = []
            row.history.append(row.status)
            self._version += 1
            event = row.waiting
            row.waiting = None
        if event is not None:
            event.set()

    def statuses(self, seed: int) -> list[str]:
        with self._lock:
            row = self._rows.get(seed)
            if row is None:
                return []
            return list(row.history)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            rows = [_public_row(self._rows[seed]) for seed in self._order]
            version = self._version
        return {"heuristics": self.heuristics, "version": version, "rows": rows}

    def serve(self, *, open_browser: bool) -> None:
        table = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0]
                if path == "/state":
                    _send_json(self, table.snapshot())
                    return
                if path == "/":
                    _send_bytes(self, 200, _PAGE_BYTES, "text/html; charset=utf-8")
                    return
                _send_bytes(self, 404, b"not found", "text/plain; charset=utf-8")

            def do_POST(self) -> None:
                if self.path.split("?", 1)[0] != "/choose":
                    _send_bytes(self, 404, b"not found", "text/plain; charset=utf-8")
                    return
                length = int(self.headers.get("Content-Length", "0") or "0")
                try:
                    payload = json.loads(self.rfile.read(length))
                except json.JSONDecodeError:
                    _send_bytes(
                        self, 400, b"expected JSON", "text/plain; charset=utf-8"
                    )
                    return
                message = table.submit(payload)
                if message is None:
                    _send_json(self, {"ok": True})
                    return
                _send_bytes(
                    self,
                    400,
                    message.encode(),
                    "text/plain; charset=utf-8",
                )

            def log_message(self, format: str, *args: Any) -> None:
                del format, args

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        port = int(self._server.server_address[1])
        self.url = f"http://127.0.0.1:{port}/"
        print(self.url)
        if open_browser:
            webbrowser.open(self.url)

    def close(self) -> None:
        server = self._server
        if server is None:
            return
        self._server = None
        server.shutdown()
        server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _ensure(self, seed: int) -> _Row:
        row = self._rows.get(seed)
        if row is None:
            row = _Row(seed=seed)
            self._rows[seed] = row
            self._order.append(seed)
        return row

    def _pause(self) -> None:
        if self.beat > 0:
            time.sleep(self.beat)


class HumanPlayer:
    def __init__(
        self,
        settings: Settings,
        rng: object | None = None,
    ) -> None:
        del settings, rng
        self.kind = "human"
        self.name = "human"
        self._seat: int | None = None

    def bind_seat(self, seat: int) -> None:
        self._seat = seat

    def choose(
        self,
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[PriorPlacement],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        del board, prior
        table = active_table()
        seed = game_seed.get()
        if table is None or seed is None or self._seat is None:
            raise RuntimeError("human player is not seated at a table")
        choice = table.wait_human(seed, self._seat, available, errors)
        table.note_placement(seed, self._seat, choice[0], choice[1], self.kind)
        return choice


_active: HumanTable | None = None


def active_table() -> HumanTable | None:
    return _active


def activate(table: HumanTable) -> None:
    global _active
    _active = table


def deactivate(table: HumanTable) -> None:
    global _active
    if _active is table:
        _active = None


def open_table(
    seeds: Sequence[int],
    heuristics: str,
    *,
    open_browser: bool = True,
    beat: float = 0.4,
) -> HumanTable:
    previous = _active
    if previous is not None:
        previous.close()
        deactivate(previous)
    table = HumanTable(heuristics, beat=beat)
    table.prepare(seeds)
    table.serve(open_browser=open_browser)
    activate(table)
    return table


def _public_row(row: _Row) -> dict[str, Any]:
    return {
        "seed": row.seed,
        "status": row.status,
        "board": row.board,
        "placements": list(row.placements),
        "seat": row.seat,
        "available": [
            {"vertex": _coordinate(vertex), "edge": _coordinate(edge)}
            for vertex, edge in row.pairs
        ],
        "errors": list(row.errors),
    }


def _retract(row: _Row, seat: int) -> None:
    for index in range(len(row.placements) - 1, -1, -1):
        if row.placements[index].get("seat") == seat:
            del row.placements[index]
            return


def _parse_submission(
    payload: object,
) -> str | tuple[int, tuple[int, int, int], tuple[int, int, int]]:
    if not isinstance(payload, dict):
        return "expected an object"
    seed = payload.get("seed")
    vertex = _point(payload.get("vertex"))
    edge = _point(payload.get("edge"))
    if type(seed) is not int:
        return "expected a seed"
    if vertex is None or edge is None:
        return "expected a vertex and an edge"
    return seed, vertex, edge


def _point(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, dict):
        return None
    q = value.get("q")
    r = value.get("r")
    index = value.get("index")
    if type(q) is not int or type(r) is not int or type(index) is not int:
        return None
    return q, r, index


def _match_pair(
    pairs: list[tuple[Vertex, Edge]],
    vertex: tuple[int, int, int],
    edge: tuple[int, int, int],
) -> tuple[Vertex, Edge] | None:
    wanted_vertex = Vertex(*vertex)
    wanted_edge = Edge(*edge)
    for pair in pairs:
        if pair[0] == wanted_vertex and pair[1] == wanted_edge:
            return pair
    return None


def _coordinate(point: Vertex | Edge) -> dict[str, int]:
    return {"q": point.q, "r": point.r, "index": point.index}


def _send_json(handler: BaseHTTPRequestHandler, payload: object) -> None:
    body = json.dumps(payload).encode()
    _send_bytes(handler, 200, body, "application/json")


def _send_bytes(
    handler: BaseHTTPRequestHandler,
    status: int,
    body: bytes,
    content_type: str,
) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    if body:
        handler.wfile.write(body)


_HUMAN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your turn</title>
<style>
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #0f172a;
    background: #fff;
  }
  .layout { display: flex; min-height: 100vh; }
  aside {
    flex: none;
    box-sizing: border-box;
    max-height: 100vh;
    overflow: auto;
  }
  .rows {
    width: 220px;
    border-right: 1px solid #e2e8f0;
    padding: 16px;
  }
  .rules-panel {
    width: 360px;
    padding: 16px 18px 32px;
  }
  .split {
    flex: none;
    width: 9px;
    margin: 0 -4px;
    cursor: col-resize;
    touch-action: none;
    position: relative;
    z-index: 1;
  }
  .split::after {
    content: "";
    position: absolute;
    top: 0;
    bottom: 0;
    left: 4px;
    width: 1px;
    background: #e2e8f0;
  }
  .split:hover::after, body.resizing .split::after {
    width: 2px;
    left: 3px;
    background: #64748b;
  }
  body.resizing { cursor: col-resize; user-select: none; }
  h1 {
    margin: 0 0 8px;
    font-size: 14px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #047857;
  }
  #rows { display: flex; flex-direction: column; gap: 4px; }
  button {
    font: inherit;
    border: 1px solid #cbd5e1;
    background: #fff;
    border-radius: 8px;
    padding: 8px 12px;
    cursor: pointer;
    text-align: left;
  }
  #rows button.queued { background: #fff; }
  #rows button.waiting_random { background: #dbeafe; border-color: #2563eb; }
  #rows button.pending_human { background: #fef3c7; border-color: #d97706; }
  #rows button.done { background: #dcfce7; border-color: #16a34a; }
  #rows button.failed { background: #fee2e2; border-color: #dc2626; }
  #rows button.selected { outline: 2px solid #0f172a; outline-offset: 1px; font-weight: 700; }
  .detail {
    display: block;
    margin-top: 2px;
    font-size: 12px;
    font-weight: 400;
    color: #475569;
  }
  main { flex: 1; min-width: 0; padding: 16px 24px 32px; }
  #caption { margin: 0 0 8px; font-weight: 600; }
  #errors { margin: 0 0 12px; min-height: 1.2em; color: #b91c1c; }
/*__BOARD_CSS__*/
  .choice-vertex { fill: #fff; stroke: #0f172a; stroke-width: 2; cursor: pointer; }
  .choice-vertex.picked { fill: #fde68a; }
  .choice-edge {
    stroke: #0f172a;
    stroke-width: 14;
    stroke-linecap: round;
    opacity: 0.55;
    cursor: pointer;
  }
  #rules {
    margin: 0;
    font: 13px/1.45 Palatino, "Palatino Linotype", "Times New Roman", serif;
    color: #0f172a;
  }
  #rules h1, #rules h2, #rules h3 {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    letter-spacing: 0;
    text-transform: none;
    color: #0f172a;
    margin: 16px 0 8px;
  }
  #rules h1 { font-size: 18px; }
  #rules h2 { font-size: 15px; }
  #rules h3 { font-size: 14px; }
  #rules p { margin: 0 0 10px; }
  #rules ul { margin: 0 0 10px; padding-left: 18px; }
  #rules li { margin: 0 0 8px; }
  #rules code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
  }
</style>
</head>
<body>
<div class="layout">
  <aside class="rows">
    <h1>Rows</h1>
    <div id="rows"></div>
  </aside>
  <main>
    <p id="caption"></p>
    <p id="errors"></p>
    <div class="board">
      <svg id="board" viewBox="0 0 900 800" role="img" aria-label="Catan board"></svg>
    </div>
  </main>
  <div id="rules-split" class="split" role="separator" aria-orientation="vertical" aria-label="Resize heuristics"></div>
  <aside class="rules-panel" id="rules-panel">
    <h1>Heuristics</h1>
    <div id="rules"></div>
  </aside>
</div>
<script>
/*__BOARD_JS__*/
let state = { heuristics: "", rows: [], version: -1 };
let selected = 0;
let pinned = false;
let picked = "";
let activeTurn = "";
let drawn = "";
let listed = "";
let shownRules = null;

function pointKey(point) {
  return `${point.q},${point.r},${point.index}`;
}

function statusLabel(status) {
  if (status === "pending_human") return "Needs an answer";
  if (status === "waiting_random") return "Waiting for random";
  if (status === "done") return "Finished";
  if (status === "failed") return "Failed";
  return "Queued";
}

function renderRows() {
  const rows = state.rows || [];
  if (!pinned) {
    const pending = rows.findIndex((row) => row.status === "pending_human");
    if (pending >= 0) selected = pending;
  }
  if (selected >= rows.length) selected = 0;
  const signature = rows
    .map((row) => `${row.seed}:${row.status}:${row.placements.length}`)
    .join("|") + ":" + selected;
  if (signature === listed) return;
  listed = signature;
  const list = document.getElementById("rows");
  list.replaceChildren();
  rows.forEach((row, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = row.status + (index === selected ? " selected" : "");
    const title = document.createElement("span");
    title.textContent = `Row ${index + 1}`;
    const detail = document.createElement("span");
    detail.className = "detail";
    detail.textContent = statusLabel(row.status);
    button.append(title, detail);
    button.addEventListener("click", () => {
      pinned = true;
      selected = index;
      picked = "";
      activeTurn = "";
      listed = "";
      drawn = "";
      render();
    });
    list.appendChild(button);
  });
}

function caption(row, index) {
  const prefix = `Row ${index + 1} · seed ${row.seed}`;
  if (row.status === "pending_human") {
    const seat = row.seat == null ? "" : `, seat ${row.seat}`;
    if (picked) {
      return `${prefix} — seat ${row.seat}. Click a road from the selected settlement.`;
    }
    return `${prefix} — your turn${seat}. Click a settlement, then a road.`;
  }
  if (row.status === "waiting_random") {
    return `${prefix} — waiting for the random player.`;
  }
  if (row.status === "done") return `${prefix} — draft finished.`;
  if (row.status === "failed") return `${prefix} — this row failed.`;
  return `${prefix} — queued.`;
}

function drawChoices(row) {
  if (!row || row.status !== "pending_human") return "";
  const parts = [];
  const vertices = new Map();
  for (const option of row.available || []) {
    vertices.set(pointKey(option.vertex), option.vertex);
  }
  if (picked) {
    for (const option of row.available || []) {
      if (pointKey(option.vertex) !== picked) continue;
      const [start, end] = edgeEnds(option.edge).map(screen);
      const key = pointKey(option.edge);
      parts.push(
        `<line class="choice-edge" data-edge="${key}" x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}"/>`,
      );
    }
  }
  for (const vertex of vertices.values()) {
    const at = screen(hexVertices(vertex.q, vertex.r)[vertex.index]);
    const key = pointKey(vertex);
    const on = key === picked ? " picked" : "";
    parts.push(
      `<circle class="choice-vertex${on}" data-vertex="${key}" cx="${at.x}" cy="${at.y}" r="12"/>`,
    );
  }
  return parts.join("");
}

function renderBoard(row) {
  const board = document.getElementById("board");
  if (!row || !row.board) {
    if (drawn !== "") {
      board.innerHTML = "";
      drawn = "";
    }
    return;
  }
  const turnKey = `${row.status}:${row.placements.length}:${(row.errors || []).length}`;
  if (activeTurn && turnKey !== activeTurn) picked = "";
  activeTurn = turnKey;
  const markup = drawBoard({ board: row.board }, row.placements) + drawChoices(row);
  const token = markup + "|" + picked;
  if (token === drawn) return;
  drawn = token;
  board.innerHTML = markup;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function inlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\\*\\*([^*]+)\\*\\*/g, "<strong>$1</strong>");
}

function renderMarkdown(source) {
  const lines = String(source).replaceAll("\\r\\n", "\\n").split("\\n");
  const parts = [];
  let paragraph = [];
  let list = [];
  const flushParagraph = () => {
    if (!paragraph.length) return;
    parts.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (!list.length) return;
    const items = list.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("");
    parts.push(`<ul>${items}</ul>`);
    list = [];
  };
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = /^(#{1,3})\\s+(.*)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      parts.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    const item = /^[*+-]\\s+(.*)$/.exec(trimmed);
    if (item) {
      flushParagraph();
      list.push(item[1]);
      continue;
    }
    if (list.length) {
      list[list.length - 1] += ` ${trimmed}`;
      continue;
    }
    paragraph.push(trimmed);
  }
  flushParagraph();
  flushList();
  return parts.join("");
}

function render() {
  const rules = document.getElementById("rules");
  const text = state.heuristics || "";
  if (shownRules !== text) {
    shownRules = text;
    rules.innerHTML = renderMarkdown(text);
  }
  renderRows();
  const rows = state.rows || [];
  const row = rows[selected];
  const captionNode = document.getElementById("caption");
  const errors = document.getElementById("errors");
  if (!row) {
    captionNode.textContent = "No rows.";
    errors.textContent = "";
    renderBoard(null);
    return;
  }
  captionNode.textContent = caption(row, selected);
  errors.textContent = (row.errors || []).join(" ");
  renderBoard(row);
}

async function choose(edgeKey) {
  const row = (state.rows || [])[selected];
  if (!row || !picked) return;
  const option = (row.available || []).find(
    (item) => pointKey(item.vertex) === picked && pointKey(item.edge) === edgeKey,
  );
  if (!option) return;
  const response = await fetch("/choose", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      seed: row.seed,
      vertex: option.vertex,
      edge: option.edge,
    }),
  });
  if (!response.ok) {
    document.getElementById("errors").textContent = await response.text();
    return;
  }
  picked = "";
  drawn = "";
}

const rulesPanel = document.getElementById("rules-panel");
const rulesSplit = document.getElementById("rules-split");

function clampRulesWidth(width) {
  const maxWidth = Math.max(160, window.innerWidth - 280);
  return Math.min(maxWidth, Math.max(160, width));
}

rulesSplit.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  rulesSplit.setPointerCapture(event.pointerId);
  const startX = event.clientX;
  const startWidth = rulesPanel.getBoundingClientRect().width;
  document.body.classList.add("resizing");
  const move = (next) => {
    const width = clampRulesWidth(startWidth + startX - next.clientX);
    rulesPanel.style.width = width + "px";
  };
  const stop = () => {
    document.body.classList.remove("resizing");
    rulesSplit.removeEventListener("pointermove", move);
    rulesSplit.removeEventListener("pointerup", stop);
    rulesSplit.removeEventListener("pointercancel", stop);
  };
  rulesSplit.addEventListener("pointermove", move);
  rulesSplit.addEventListener("pointerup", stop);
  rulesSplit.addEventListener("pointercancel", stop);
});

document.getElementById("board").addEventListener("click", (event) => {
  const target = event.target;
  if (!target || !target.closest) return;
  const vertex = target.closest("[data-vertex]");
  if (vertex) {
    picked = vertex.getAttribute("data-vertex") || "";
    drawn = "";
    render();
    return;
  }
  const edge = target.closest("[data-edge]");
  if (edge) choose(edge.getAttribute("data-edge") || "");
});

async function refresh() {
  try {
    const response = await fetch("/state");
    if (!response.ok) return;
    state = await response.json();
    render();
  } catch (err) {
    // The page stops polling when the batch server closes.
  }
}

refresh();
setInterval(refresh, 300);
</script>
</body>
</html>
"""

HUMAN_PAGE = _HUMAN_PAGE.replace("/*__BOARD_CSS__*/", BOARD_CSS).replace(
    "/*__BOARD_JS__*/", BOARD_JS
)
_PAGE_BYTES = HUMAN_PAGE.encode()
