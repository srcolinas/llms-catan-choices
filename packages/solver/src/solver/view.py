from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SNAKE = (0, 1, 2, 3, 3, 2, 1, 0)

METRIC_LABELS = {
    "resource_combos": "Resource combos",
    "specific_port": "Specific port",
    "generic_port": "Generic port",
    "production": "Production",
    "diversity": "Diversity",
}

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Choices</title>
<style>
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #0f172a;
    background: #fff;
  }
  .layout { display: flex; min-height: calc(100vh - 45px); }
  aside {
    width: 260px;
    flex: none;
    border-right: 1px solid #e2e8f0;
    padding: 16px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    gap: 16px;
    max-height: calc(100vh - 45px);
    overflow-x: hidden;
    overflow-y: auto;
  }
  aside h1, aside h2 {
    margin: 0 0 8px;
    font-size: 14px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #047857;
  }
  aside h2 { margin-top: 4px; }
  #rows { display: flex; flex-direction: column; gap: 4px; }
  main { flex: 1; min-width: 0; padding: 16px 24px 32px; }
  .toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  #caption { margin: 0; flex: 1; font-weight: 600; }
  button {
    font: inherit;
    border: 1px solid #cbd5e1;
    background: #fff;
    border-radius: 8px;
    padding: 8px 12px;
    cursor: pointer;
    text-align: left;
  }
  button:disabled { opacity: 0.4; cursor: default; }
  #rows button.selected { background: #eff6ff; border-color: #2563eb; font-weight: 700; }
  .roster { display: block; margin-top: 2px; font-size: 12px; font-weight: 400; color: #475569; line-height: 1.3; }
  #rows button.selected .roster { color: #1e3a8a; }
  .board { max-width: 900px; overflow: hidden; border-radius: 8px; background: #017DD5; }
  svg { display: block; width: 100%; height: auto; background: #017DD5; shape-rendering: crispEdges; }
  .hex polygon { opacity: 0.8; }
  .hex:hover polygon { opacity: 1; }
  .hex text, .hex circle { pointer-events: none; }
  .hex .coordinate { display: none; }
  .hex:hover .coordinate { display: inline; }
  .legend { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 12px; font-size: 13px; }
  .legend-seat { display: flex; flex-direction: column; gap: 4px; min-width: 180px; }
  .legend-title { display: flex; align-items: center; font-weight: 600; }
  .swatch { width: 12px; height: 12px; border-radius: 999px; display: inline-block; margin-right: 6px; }
  .heuristics { margin: 0; padding-left: 18px; font-size: 12px; color: #334155; }
  .heuristics .pass { color: #047857; }
  .heuristics .fail { color: #b91c1c; }
  .mode-tabs {
    display: flex;
    gap: 0;
    border-bottom: 1px solid #cbd5e1;
    padding: 0 16px;
    background: #fff;
  }
  .mode-tabs button, .source-tabs button {
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    background: transparent;
    padding: 10px 14px;
    font-weight: 600;
  }
  .mode-tabs button.selected, .source-tabs button.selected {
    border-bottom-color: #111;
    background: transparent;
  }
  .source-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 0;
    border-bottom: 1px solid #e2e8f0;
    margin: -4px -4px 4px;
  }
  .source-tabs button { padding: 8px 10px; font-size: 13px; }
  #summary-view {
    padding: 28px 36px 48px;
    max-width: 1480px;
  }
  #radar-chart, .seat-radar {
    display: block;
    width: 100%;
    height: auto;
    background: #fff;
  }
  #radar-chart { max-width: 640px; }
  #seat-charts {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 4px 0;
    margin-top: 0;
    max-width: 1120px;
  }
  #seat-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 18px;
    margin: 16px 0 8px;
    max-width: 1120px;
  }
  #seat-legend span { display: inline-flex; align-items: center; gap: 6px; }
  .chart-swatch {
    width: 12px;
    height: 12px;
    border: 1px solid #111;
    display: inline-block;
  }
  #chart-caption, #seat-caption, #seat-legend, #skipped-note, #chart-empty, #latency-caption {
    font-family: Palatino, "Palatino Linotype", "Iowan Old Style", "Times New Roman", serif;
    color: #111;
    font-size: 13px;
    line-height: 1.45;
  }
  #chart-caption, #seat-caption, #latency-caption { margin: 12px 0 0; max-width: 720px; }
  #skipped-note { margin: 12px 0 0; }
  #latency-section { margin-top: 28px; max-width: 720px; }
  #latency-section h2 {
    font-family: Palatino, "Palatino Linotype", "Iowan Old Style", "Times New Roman", serif;
    font-size: 16px;
    font-weight: 600;
    margin: 0;
  }
  #latency-charts { display: grid; gap: 8px; margin-top: 8px; }
  .latency-chart {
    display: block;
    width: 100%;
    height: auto;
    background: #fff;
  }
  .hidden { display: none; }
</style>
</head>
<body>
<nav class="mode-tabs">
  <button id="tab-games" type="button" class="selected">Games</button>
  <button id="tab-summary" type="button">Summary</button>
</nav>
<div id="games-view" class="layout">
  <aside>
    <div id="sources" class="source-tabs"></div>
    <div>
      <h1>Rows</h1>
      <div id="rows"></div>
    </div>
  </aside>
  <main>
    <div class="toolbar">
      <button id="back" type="button">Back</button>
      <button id="forward" type="button">Forward</button>
      <p id="caption"></p>
    </div>
    <div class="board">
      <svg id="board" viewBox="0 0 900 800" role="img" aria-label="Catan board"></svg>
    </div>
    <div class="legend" id="legend"></div>
  </main>
</div>
<div id="summary-view" class="hidden">
  <svg id="radar-chart" viewBox="0 0 640 640" role="img" aria-label="Mean heuristic pass rate radar by player"></svg>
  <p id="chart-empty" class="hidden">No finished evaluations to summarize.</p>
  <p id="chart-caption">The radar shows the mean pass rate across all seats. Each spoke is one heuristic, and each translucent polygon is one player.</p>
  <div id="seat-legend"></div>
  <div id="seat-charts">
    <svg id="radar-seat-0" class="seat-radar" viewBox="0 0 640 640" role="img" aria-label="Mean heuristic pass rate when sitting first"></svg>
    <svg id="radar-seat-1" class="seat-radar" viewBox="0 0 640 640" role="img" aria-label="Mean heuristic pass rate when sitting second"></svg>
    <svg id="radar-seat-2" class="seat-radar" viewBox="0 0 640 640" role="img" aria-label="Mean heuristic pass rate when sitting third"></svg>
    <svg id="radar-seat-3" class="seat-radar" viewBox="0 0 640 640" role="img" aria-label="Mean heuristic pass rate when sitting fourth"></svg>
  </div>
  <p id="seat-caption">Each chart includes only players sitting in that turn position. A player with no finished games there is omitted.</p>
  <p id="skipped-note"></p>
  <div id="latency-section" class="hidden">
    <h2>Model call latency</h2>
    <p id="latency-caption">Each bar counts model calls that recorded latency. Placements without latency are omitted. The bins are shared across players.</p>
    <div id="latency-charts"></div>
  </div>
</div>
<script>
const GAMES = __GAMES__;
const PERFORMANCE = __PERFORMANCE__;
const BY_SEAT = __BY_SEAT__;
const LATENCIES = __LATENCIES__;
const HEX_SIZE = 60;
const OFFSET_X = 450;
const OFFSET_Y = 400;
const SEAT_COLORS = ["#ef4444", "#2563eb", "#eab308", "#7c3aed"];
const TERRAIN_COLORS = {
  forest: "#3E6037",
  pasture: "#87C14E",
  fields: "#E5AF4D",
  hills: "#D36E3D",
  mountains: "#808080",
  desert: "#D8AE6F",
};

let source = GAMES.length ? sourceName(GAMES[0]) : "games";
let row = 0;
let step = 0;

function hexToPixel(q, r) {
  return {
    x: HEX_SIZE * Math.sqrt(3) * (q + r / 2),
    y: HEX_SIZE * (3 / 2) * r,
  };
}

function hexVertices(q, r) {
  const center = hexToPixel(q, r);
  const vertices = [];
  for (let index = 0; index < 6; index += 1) {
    const angle = -Math.PI / 2 + (Math.PI / 3) * index;
    vertices.push({
      x: center.x + HEX_SIZE * Math.cos(angle),
      y: center.y + HEX_SIZE * Math.sin(angle),
    });
  }
  return vertices;
}

function screen(point) {
  return { x: point.x + OFFSET_X, y: point.y + OFFSET_Y };
}

function edgeEnds(edge) {
  const vertices = hexVertices(edge.q, edge.r);
  return [vertices[edge.index], vertices[(edge.index + 1) % 6]];
}

function convexHull(points) {
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (origin, a, b) =>
    (a.x - origin.x) * (b.y - origin.y) - (a.y - origin.y) * (b.x - origin.x);
  const half = (source) => {
    const result = [];
    source.forEach((point) => {
      while (
        result.length >= 2 &&
        cross(result[result.length - 2], result[result.length - 1], point) <= 0
      ) {
        result.pop();
      }
      result.push(point);
    });
    return result;
  };
  const lower = half(sorted);
  const upper = half([...sorted].reverse());
  return [...lower.slice(0, -1), ...upper.slice(0, -1)];
}

function polygonPoints(points, scale) {
  return points
    .map((point) => `${point.x * scale + OFFSET_X},${point.y * scale + OFFSET_Y}`)
    .join(" ");
}

function landHexes(board) {
  return [
    ...board.tiles.map((tile) => ({
      q: tile.q,
      r: tile.r,
      terrain: tile.terrain,
      number: tile.number,
    })),
    { q: board.desert.q, r: board.desert.r, terrain: "desert", number: null },
  ];
}

function harbourLabel(kind) {
  return kind === "generic" ? "⛵ 3:1 any" : `⛵ 2:1 ${kind}`;
}

function drawBoard(game, shown) {
  const hexes = landHexes(game.board);
  const hull = convexHull(hexes.flatMap((hex) => hexVertices(hex.q, hex.r)));
  const parts = [
    `<polygon points="${polygonPoints(hull, 1.12)}" fill="#EED5A0"/>`,
    `<polygon points="${polygonPoints(hull, 1.01)}" fill="none" stroke="#EED5A0" stroke-width="14" stroke-linejoin="round"/>`,
  ];
  for (const hex of hexes) {
    const vertices = hexVertices(hex.q, hex.r)
      .map(screen)
      .map((vertex) => `${vertex.x},${vertex.y}`)
      .join(" ");
    const center = screen(hexToPixel(hex.q, hex.r));
    const name = hex.terrain.charAt(0).toUpperCase() + hex.terrain.slice(1);
    parts.push(
      `<g class="hex">`,
      `<polygon points="${vertices}" fill="${TERRAIN_COLORS[hex.terrain]}" stroke="#333" stroke-width="2"/>`,
      `<text x="${center.x}" y="${center.y - 18}" text-anchor="middle" fill="#fff" font-size="13" font-weight="600">${name}</text>`,
    );
    if (hex.number != null) {
      const fill = hex.number === 6 || hex.number === 8 ? "#dc2626" : "#000";
      parts.push(
        `<circle cx="${center.x}" cy="${center.y + 4}" r="15" fill="#fff" stroke="#e2e8f0" stroke-width="1.5"/>`,
        `<text x="${center.x}" y="${center.y + 5}" text-anchor="middle" dominant-baseline="middle" fill="${fill}" font-size="16" font-weight="700">${hex.number}</text>`,
      );
    }
    parts.push(
      `<text class="coordinate" x="${center.x}" y="${center.y + 32}" text-anchor="middle" fill="#0f172a" font-size="12" font-weight="700">(${hex.q}, ${hex.r})</text>`,
      `</g>`,
    );
  }
  for (const harbour of game.board.harbours) {
    const [first, second] = edgeEnds(harbour.edge);
    const middle = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
    const distance = Math.hypot(middle.x, middle.y) || 1;
    const label = screen({
      x: middle.x + (middle.x / distance) * 112,
      y: middle.y + (middle.y / distance) * 112,
    });
    const start = screen(first);
    const end = screen(second);
    parts.push(
      `<line x1="${label.x}" y1="${label.y}" x2="${start.x}" y2="${start.y}" stroke="#ecfeff" stroke-width="2" stroke-dasharray="5 4" stroke-linecap="round"/>`,
      `<line x1="${label.x}" y1="${label.y}" x2="${end.x}" y2="${end.y}" stroke="#ecfeff" stroke-width="2" stroke-dasharray="5 4" stroke-linecap="round"/>`,
      `<circle cx="${start.x}" cy="${start.y}" r="4" fill="#fef3c7" stroke="#92400e"/>`,
      `<circle cx="${end.x}" cy="${end.y}" r="4" fill="#fef3c7" stroke="#92400e"/>`,
      `<rect x="${label.x - 58}" y="${label.y - 14}" width="116" height="28" rx="14" fill="#ecfeff" stroke="#155e75" stroke-width="2"/>`,
      `<text x="${label.x}" y="${label.y}" text-anchor="middle" dominant-baseline="middle" fill="#164e63" font-size="11" font-weight="700">${harbourLabel(harbour.kind)}</text>`,
    );
  }
  for (const placed of shown) {
    const [start, end] = edgeEnds(placed.edge).map(screen);
    const color = SEAT_COLORS[placed.seat];
    parts.push(
      `<line x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}" stroke="${color}" stroke-width="8" stroke-linecap="round"/>`,
    );
  }
  for (const placed of shown) {
    const vertex = screen(hexVertices(placed.vertex.q, placed.vertex.r)[placed.vertex.index]);
    parts.push(
      `<circle cx="${vertex.x}" cy="${vertex.y}" r="14" fill="${SEAT_COLORS[placed.seat]}" stroke="#fff" stroke-width="3"/>`,
    );
  }
  return parts.join("");
}

function playerKind(choice) {
  if (!choice) return "unnamed";
  if (choice.kind) return choice.kind;
  return choice.player === "random" ? "random" : "generative";
}

function playerLabel(choice) {
  if (!choice) return "unnamed";
  const kind = playerKind(choice);
  if (!choice.player || choice.player === kind) return kind;
  return `${kind} · ${choice.player}`;
}

function isIncomplete(game) {
  return Boolean(game.evaluation) && game.evaluation.metrics == null;
}

function sourceName(game) {
  return (game && game.source) || "games";
}

function localRow(index) {
  const name = sourceName(GAMES[index]);
  let count = 0;
  for (let cursor = 0; cursor <= index; cursor += 1) {
    if (sourceName(GAMES[cursor]) === name) count += 1;
  }
  return count;
}

function caption(game, index) {
  const total = game.steps.length;
  const unfinished = isIncomplete(game) ? " — Draft did not finish" : "";
  const prefix = `${sourceName(game)} · Row ${localRow(index)}`;
  if (step === 0) return `${prefix} — Step 0 of ${total} — No placements yet${unfinished}`;
  const current = game.steps[step - 1];
  return `${prefix} — Step ${step} of ${total} — Seat ${current.seat} · ${playerLabel(current)} · placement ${current.placement} of 2${unfinished}`;
}

function metricNames(game) {
  if (!game.evaluation || !game.evaluation.metrics) return [];
  return Object.keys(game.evaluation.metrics);
}

function gamesForSource(name) {
  return GAMES.map((game, index) => ({ game, index })).filter(
    ({ game }) => sourceName(game) === name,
  );
}

function renderSourceTabs() {
  const tabs = document.getElementById("sources");
  tabs.replaceChildren();
  const names = [];
  GAMES.forEach((game) => {
    const name = sourceName(game);
    if (!names.includes(name)) names.push(name);
  });
  names.forEach((name) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = name;
    button.className = name === source ? "selected" : "";
    button.addEventListener("click", () => {
      if (source === name) return;
      source = name;
      const first = gamesForSource(name)[0];
      row = first ? first.index : 0;
      step = 0;
      renderSourceTabs();
      renderList();
      render();
    });
    tabs.appendChild(button);
  });
}

function renderList() {
  const rows = document.getElementById("rows");
  rows.replaceChildren();
  gamesForSource(source).forEach(({ game, index }) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.index = String(index);
    const title = document.createElement("span");
    const number = localRow(index);
    title.textContent = isIncomplete(game) ? `✗ Row ${number}` : `Row ${number}`;
    const roster = document.createElement("span");
    roster.className = "roster";
    roster.textContent = game.choices.map((seat) => playerKind(seat[0])).join(" · ");
    button.append(title, roster);
    button.addEventListener("click", () => {
      row = index;
      step = 0;
      render();
    });
    rows.appendChild(button);
  });
}

function renderLegend(game) {
  const legend = document.getElementById("legend");
  legend.replaceChildren();
  if (!game) return;
  const names = metricNames(game);
  game.choices.forEach((seat, index) => {
    const item = document.createElement("div");
    item.className = "legend-seat";
    const title = document.createElement("div");
    title.className = "legend-title";
    const swatch = document.createElement("i");
    swatch.className = "swatch";
    swatch.style.background = SEAT_COLORS[index];
    title.append(swatch, document.createTextNode(`Seat ${index} · ${playerLabel(seat[0])}`));
    item.append(title);
    if (names.length) {
      const list = document.createElement("ul");
      list.className = "heuristics";
      names.forEach((name) => {
        const passed = game.evaluation.metrics[name][index];
        const li = document.createElement("li");
        li.className = passed ? "pass" : "fail";
        li.textContent = `${passed ? "✓" : "✗"} ${name}`;
        list.appendChild(li);
      });
      item.append(list);
    }
    legend.appendChild(item);
  });
}

function skippedRows() {
  return GAMES.filter(isIncomplete).length;
}

function renderSkippedNote() {
  const note = document.getElementById("skipped-note");
  const skipped = skippedRows();
  if (!skipped) {
    note.textContent = "";
    return;
  }
  const rows = skipped === 1 ? "1 row was" : `${skipped} rows were`;
  note.textContent = `${rows} not scored because the draft did not finish.`;
}

const SERIES_COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9", "#000000"];

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function radarPoint(cx, cy, radius, index, count) {
  const angle = -Math.PI / 2 + (2 * Math.PI * index) / count;
  return {
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle),
    angle,
  };
}

function renderRadar(performance, title, showLegend) {
  if (!performance.length || !performance[0].players.length) return null;
  const players = performance[0].players;
  const scoredSeries = [];
  players.forEach((seed, series) => {
    const scored = performance.some((metric) => {
      const stat = metric.players[series];
      return stat && stat.n && stat.mean != null;
    });
    if (scored) scoredSeries.push(series);
  });
  const radius = 150;
  const reach = radius + 22;
  const count = performance.length;
  const pad = 2;
  let minX = -radius;
  let maxX = radius;
  if (title) {
    const titleWidth = title.length * 8;
    minX = Math.min(minX, -titleWidth / 2);
    maxX = Math.max(maxX, titleWidth / 2);
  }
  performance.forEach((metric, index) => {
    const label = metric.label || metric.metric;
    const point = radarPoint(0, 0, reach, index, count);
    const textWidth = label.length * 6.3;
    const cos = Math.cos(point.angle);
    if (cos > 0.25) maxX = Math.max(maxX, point.x + textWidth);
    else if (cos < -0.25) minX = Math.min(minX, point.x - textWidth);
    else {
      minX = Math.min(minX, point.x - textWidth / 2);
      maxX = Math.max(maxX, point.x + textWidth / 2);
    }
  });
  if (showLegend) {
    scoredSeries.forEach((series) => {
      maxX = Math.max(maxX, 48 + players[series].player.length * 7.4 - (pad - minX));
    });
  }
  const cx = pad - minX;
  const width = maxX - minX + pad * 2;
  const legendRow = 18;
  const legendBlock = showLegend && scoredSeries.length ? 8 + scoredSeries.length * legendRow : 0;
  const cy = reach + (title ? 32 : 8);
  const contentBottom = cy + reach + 16;
  const height = contentBottom + legendBlock;
  const parts = [
    `<rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff"/>`,
  ];
  const labels = [];
  if (title) {
    labels.push(
      `<text x="${cx}" y="14" text-anchor="middle" font-size="15" font-weight="600">${escapeXml(title)}</text>`,
    );
  }
  [0.25, 0.5, 0.75, 1].forEach((level) => {
    const ring = [];
    for (let index = 0; index < count; index += 1) {
      const point = radarPoint(cx, cy, radius * level, index, count);
      ring.push(`${point.x.toFixed(2)},${point.y.toFixed(2)}`);
    }
    const dash = level === 1 ? "" : ` stroke-dasharray="3 3"`;
    parts.push(
      `<polygon points="${ring.join(" ")}" fill="none" stroke="#111" stroke-width="${level === 1 ? "1.1" : "0.6"}"${dash}/>`,
    );
    const tick = radarPoint(cx, cy, radius * level, 0, count);
    const label = level === 1 ? "1" : level.toFixed(2);
    labels.push(
      `<text x="${(tick.x + 6).toFixed(2)}" y="${tick.y.toFixed(2)}" font-size="10" dominant-baseline="middle">${label}</text>`,
    );
  });
  performance.forEach((metric, index) => {
    const end = radarPoint(cx, cy, radius, index, count);
    const labelAt = radarPoint(cx, cy, reach, index, count);
    const label = metric.label || metric.metric;
    let anchor = "middle";
    if (Math.cos(end.angle) > 0.25) anchor = "start";
    else if (Math.cos(end.angle) < -0.25) anchor = "end";
    let baseline = "middle";
    if (Math.sin(end.angle) < -0.4) baseline = "auto";
    else if (Math.sin(end.angle) > 0.4) baseline = "hanging";
    parts.push(
      `<line x1="${cx.toFixed(2)}" y1="${cy.toFixed(2)}" x2="${end.x.toFixed(2)}" y2="${end.y.toFixed(2)}" stroke="#111" stroke-width="0.8"/>`,
    );
    labels.push(
      `<text x="${labelAt.x.toFixed(2)}" y="${labelAt.y.toFixed(2)}" text-anchor="${anchor}" dominant-baseline="${baseline}" font-size="12">${escapeXml(label)}</text>`,
    );
  });
  scoredSeries.forEach((series) => {
    const seed = players[series];
    const color = SERIES_COLORS[series % SERIES_COLORS.length];
    const polygon = performance.map((metric, index) => {
      const stat = metric.players[series];
      const mean = stat && stat.n && stat.mean != null ? stat.mean : 0;
      const point = radarPoint(cx, cy, radius * mean, index, count);
      return `${point.x.toFixed(2)},${point.y.toFixed(2)}`;
    }).join(" ");
    const summary = performance.map((metric) => {
      const stat = metric.players[series];
      const label = metric.label || metric.metric;
      if (!stat || !stat.n || stat.mean == null) return label;
      return `${label} ${Number(stat.mean).toFixed(2)}`;
    }).join(", ");
    parts.push(
      `<g><title>${escapeXml(`${seed.player}: ${summary}`)}</title>`,
      `<polygon points="${polygon}" fill="${color}" fill-opacity="0.32" stroke="${color}" stroke-width="1.6" stroke-linejoin="round"/>`,
      `</g>`,
    );
  });
  if (showLegend) {
    scoredSeries.forEach((series, index) => {
      const y = contentBottom + 4 + index * legendRow;
      const color = SERIES_COLORS[series % SERIES_COLORS.length];
      const name = players[series].player;
      parts.push(
        `<rect x="28" y="${(y - 6).toFixed(2)}" width="12" height="12" fill="${color}" stroke="#111" stroke-width="0.8"/>`,
      );
      labels.push(
        `<text x="48" y="${y.toFixed(2)}" dominant-baseline="middle" font-size="13">${escapeXml(name)}</text>`,
      );
    });
  }
  return { markup: parts.concat(labels).join(""), width, height };
}

const RADAR_FONT = "Palatino, Palatino Linotype, Iowan Old Style, Times New Roman, serif";

function paintRadar(node, performance, title, showLegend) {
  if (!node) return;
  const drawn = renderRadar(performance, title, showLegend);
  if (!drawn) {
    node.innerHTML = "";
    return;
  }
  node.setAttribute("viewBox", `0 0 ${drawn.width} ${drawn.height}`);
  node.setAttribute("font-family", RADAR_FONT);
  node.setAttribute("fill", "#111");
  node.innerHTML = drawn.markup;
}

function renderSeatCharts() {
  BY_SEAT.forEach((seat) => {
    paintRadar(
      document.getElementById(`radar-seat-${seat.seat}`),
      seat.metrics,
      seat.label,
      false,
    );
  });
}

function renderSeatLegend() {
  const legend = document.getElementById("seat-legend");
  legend.replaceChildren();
  if (!PERFORMANCE.length || !PERFORMANCE[0].players.length) return;
  PERFORMANCE[0].players.forEach((seed, series) => {
    const scored = BY_SEAT.some((seat) =>
      (seat.metrics || []).some((metric) => {
        const stat = metric.players[series];
        return stat && stat.n && stat.mean != null;
      }),
    );
    if (!scored) return;
    const item = document.createElement("span");
    const swatch = document.createElement("i");
    swatch.className = "chart-swatch";
    swatch.style.background = SERIES_COLORS[series % SERIES_COLORS.length];
    item.append(swatch, document.createTextNode(seed.player));
    legend.appendChild(item);
  });
}

function histogramLabels(edges) {
  const first = edges[0][0];
  const last = edges[edges.length - 1][1];
  if (edges.length === 1) {
    return [{ at: 0.5, text: String(first), anchor: "middle" }];
  }
  const mid = edges[Math.floor(edges.length / 2)][0];
  return [
    { at: 0, text: String(first), anchor: "start" },
    { at: 0.5, text: String(mid), anchor: "middle" },
    { at: 1, text: String(last), anchor: "end" },
  ];
}

function renderHistogram(player, series, peak) {
  const width = 640;
  const height = 210;
  const left = 44;
  const right = 16;
  const top = 28;
  const bottom = 36;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const bins = player.counts.length;
  const gap = bins > 1 ? 3 : 0;
  const barWidth = bins ? (plotWidth - gap * Math.max(bins - 1, 0)) / bins : plotWidth;
  const color = SERIES_COLORS[series % SERIES_COLORS.length];
  const baseline = top + plotHeight;
  const parts = [
    `<text x="${left}" y="18" font-size="14">${escapeXml(player.player)} (n=${player.n})</text>`,
    `<line x1="${left}" y1="${top}" x2="${left}" y2="${baseline}" stroke="#111" stroke-width="1"/>`,
    `<line x1="${left}" y1="${baseline}" x2="${width - right}" y2="${baseline}" stroke="#111" stroke-width="1"/>`,
    `<text x="${left - 8}" y="${top + 4}" font-size="11" text-anchor="end">${peak}</text>`,
    `<text x="${left - 8}" y="${baseline}" font-size="11" text-anchor="end">0</text>`,
  ];
  player.counts.forEach((count, index) => {
    const edge = LATENCIES.edges[index] || [0, 0];
    const span = edge[0] === edge[1] ? `${edge[0]} ms` : `${edge[0]}–${edge[1]} ms`;
    const barHeight = peak ? (count / peak) * plotHeight : 0;
    const x = left + index * (barWidth + gap);
    const y = baseline - barHeight;
    parts.push(
      `<rect x="${x}" y="${y}" width="${Math.max(barWidth, 0)}" height="${barHeight}" fill="${color}">`,
      `<title>${escapeXml(`${count} calls, ${span}`)}</title></rect>`,
    );
  });
  if (LATENCIES.edges.length) {
    histogramLabels(LATENCIES.edges).forEach((label) => {
      const x = left + label.at * plotWidth;
      parts.push(
        `<text x="${x}" y="${baseline + 18}" font-size="11" text-anchor="${label.anchor}">${escapeXml(label.text)}</text>`,
      );
    });
    parts.push(
      `<text x="${width - right}" y="${baseline + 32}" font-size="11" text-anchor="end">ms</text>`,
    );
  }
  return { markup: parts.join(""), width, height };
}

function renderLatency() {
  const section = document.getElementById("latency-section");
  const charts = document.getElementById("latency-charts");
  charts.replaceChildren();
  if (!LATENCIES.players.length) {
    section.classList.add("hidden");
    return;
  }
  section.classList.remove("hidden");
  const peak = Math.max(1, ...LATENCIES.players.flatMap((player) => player.counts));
  LATENCIES.players.forEach((player, series) => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "latency-chart");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", `Latency histogram for ${player.player}`);
    const drawn = renderHistogram(player, series, peak);
    svg.setAttribute("viewBox", `0 0 ${drawn.width} ${drawn.height}`);
    svg.setAttribute("font-family", RADAR_FONT);
    svg.setAttribute("fill", "#111");
    svg.innerHTML = drawn.markup;
    charts.appendChild(svg);
  });
}

function renderChart() {
  const radar = document.getElementById("radar-chart");
  const empty = document.getElementById("chart-empty");
  const caption = document.getElementById("chart-caption");
  const seatCharts = document.getElementById("seat-charts");
  const seatCaption = document.getElementById("seat-caption");
  const seatLegend = document.getElementById("seat-legend");
  if (!PERFORMANCE.length || !PERFORMANCE[0].players.length) {
    radar.innerHTML = "";
    renderSeatCharts();
    renderSeatLegend();
    empty.classList.remove("hidden");
    caption.classList.add("hidden");
    seatCharts.classList.add("hidden");
    seatCaption.classList.add("hidden");
    seatLegend.classList.add("hidden");
    return;
  }
  empty.classList.add("hidden");
  caption.classList.remove("hidden");
  seatCharts.classList.remove("hidden");
  seatCaption.classList.remove("hidden");
  seatLegend.classList.remove("hidden");
  paintRadar(radar, PERFORMANCE, "All seats", true);
  renderSeatCharts();
  renderSeatLegend();
}

function showMode(mode) {
  document.getElementById("games-view").classList.toggle("hidden", mode !== "games");
  document.getElementById("summary-view").classList.toggle("hidden", mode !== "summary");
  document.getElementById("tab-games").classList.toggle("selected", mode === "games");
  document.getElementById("tab-summary").classList.toggle("selected", mode === "summary");
}

function render() {
  document.querySelectorAll("#rows button").forEach((button) => {
    button.className = Number(button.dataset.index) === row ? "selected" : "";
  });
  const game = GAMES[row];
  const board = document.getElementById("board");
  const captionNode = document.getElementById("caption");
  renderLegend(game);
  if (!game) {
    board.innerHTML = "";
    captionNode.textContent = "No rows";
    document.getElementById("back").disabled = true;
    document.getElementById("forward").disabled = true;
    return;
  }
  board.innerHTML = drawBoard(game, game.steps.slice(0, step));
  captionNode.textContent = caption(game, row);
  document.getElementById("back").disabled = step === 0;
  document.getElementById("forward").disabled = step === game.steps.length;
}

document.getElementById("back").addEventListener("click", () => {
  if (step > 0) {
    step -= 1;
    render();
  }
});
document.getElementById("forward").addEventListener("click", () => {
  const game = GAMES[row];
  if (game && step < game.steps.length) {
    step += 1;
    render();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    document.getElementById("back").click();
  }
  if (event.key === "ArrowRight") {
    event.preventDefault();
    document.getElementById("forward").click();
  }
});

document.getElementById("tab-games").addEventListener("click", () => showMode("games"));
document.getElementById("tab-summary").addEventListener("click", () => showMode("summary"));

renderSourceTabs();
renderList();
renderChart();
renderLatency();
renderSkippedNote();
render();
</script>
</body>
</html>
"""


def draft_steps(choices: list[Any]) -> list[dict[str, Any]]:
    if len(choices) != 4 or any(len(seat) != 2 for seat in choices):
        raise ValueError("expected 4 seats with 2 placements each")
    used = [0, 0, 0, 0]
    steps: list[dict[str, Any]] = []
    for seat in SNAKE:
        choice = choices[seat][used[seat]]
        used[seat] += 1
        if choice is None:
            continue
        steps.append({**choice, "seat": seat, "placement": used[seat]})
    return steps


def load_games(path: Path) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("ok") is False:
            continue
        games.append({**row, "steps": draft_steps(row["choices"])})
    return games


def load_evaluations(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def attach_evaluations(
    games: list[dict[str, Any]], evaluations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if len(evaluations) != len(games):
        raise ValueError(
            f"evaluation has {len(evaluations)} rows but choices has {len(games)}"
        )
    attached: list[dict[str, Any]] = []
    for game, evaluation in zip(games, evaluations, strict=True):
        attached.append({**game, "evaluation": evaluation})
    return attached


def seat_player(game: dict[str, Any], seat: int) -> str:
    evaluation = game.get("evaluation")
    players = evaluation.get("players") if isinstance(evaluation, dict) else None
    if isinstance(players, list) and seat < len(players) and players[seat]:
        return str(players[seat])
    choices = game.get("choices")
    if isinstance(choices, list) and seat < len(choices) and choices[seat]:
        choice = choices[seat][0]
        if isinstance(choice, dict) and choice.get("player"):
            return str(choice["player"])
    return f"seat {seat}"


def _mean(values: list[float]) -> dict[str, Any]:
    count = len(values)
    if count == 0:
        return {"n": 0, "mean": None}
    return {"n": count, "mean": sum(values) / count}


def performance_by_metric(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: dict[str, dict[str, list[float]]] = {}
    order: list[str] = []
    for game in games:
        evaluation = game.get("evaluation")
        if not isinstance(evaluation, dict):
            continue
        metrics = evaluation.get("metrics")
        if not isinstance(metrics, dict):
            continue
        for name, values in metrics.items():
            if name not in samples:
                order.append(str(name))
                samples[str(name)] = {}
            if not isinstance(values, list):
                continue
            bucket = samples[str(name)]
            for seat, passed in enumerate(values):
                player = seat_player(game, seat)
                bucket.setdefault(player, []).append(1.0 if passed else 0.0)
    players = sorted({player for by_player in samples.values() for player in by_player})
    report: list[dict[str, Any]] = []
    for name in order:
        rows: list[dict[str, Any]] = []
        for player in players:
            rows.append({"player": player, **_mean(samples[name].get(player, []))})
        report.append(
            {
                "metric": name,
                "label": METRIC_LABELS.get(name, name),
                "players": rows,
            }
        )
    return report


SEAT_LABELS = ("First", "Second", "Third", "Fourth")


def performance_by_seat(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: dict[int, dict[str, dict[str, list[float]]]] = {
        seat: {} for seat in range(len(SEAT_LABELS))
    }
    order: list[str] = []
    seen_players: set[str] = set()
    for game in games:
        evaluation = game.get("evaluation")
        if not isinstance(evaluation, dict):
            continue
        metrics = evaluation.get("metrics")
        if not isinstance(metrics, dict):
            continue
        for name, values in metrics.items():
            metric = str(name)
            if metric not in order:
                order.append(metric)
            if not isinstance(values, list):
                continue
            for seat, passed in enumerate(values):
                if seat not in samples:
                    continue
                player = seat_player(game, seat)
                seen_players.add(player)
                bucket = samples[seat].setdefault(metric, {})
                bucket.setdefault(player, []).append(1.0 if passed else 0.0)
    players = sorted(seen_players)
    report: list[dict[str, Any]] = []
    for seat, label in enumerate(SEAT_LABELS):
        metric_rows: list[dict[str, Any]] = []
        for name in order:
            by_player = samples[seat].get(name, {})
            metric_rows.append(
                {
                    "metric": name,
                    "label": METRIC_LABELS.get(name, name),
                    "players": [
                        {"player": player, **_mean(by_player.get(player, []))}
                        for player in players
                    ],
                }
            )
        report.append({"seat": seat, "label": label, "metrics": metric_rows})
    return report


def load_directory(directory: Path) -> list[dict[str, Any]]:
    pairs: list[tuple[Path, Path]] = []
    for path in sorted(directory.glob("*.jsonl")):
        if path.name.endswith(".evaluate.jsonl"):
            continue
        eval_path = path.with_name(f"{path.stem}.evaluate.jsonl")
        if not eval_path.is_file():
            print(f"skipping {path.name}: no {eval_path.name}", file=sys.stderr)
            continue
        pairs.append((path, eval_path))
    if not pairs:
        raise ValueError(f"no choices/evaluation pairs in {directory}")
    games: list[dict[str, Any]] = []
    for choices_path, eval_path in pairs:
        loaded = attach_evaluations(
            load_games(choices_path),
            load_evaluations(eval_path),
        )
        for game in loaded:
            game["source"] = choices_path.stem
        games.extend(loaded)
    return games


_LATENCY_BINS = 10


def latency_histograms(games: list[dict[str, Any]]) -> dict[str, Any]:
    samples: dict[str, list[int]] = {}
    for game in games:
        choices = game.get("choices")
        if not isinstance(choices, list):
            continue
        for seat in choices:
            if not isinstance(seat, list):
                continue
            for choice in seat:
                latency = _latency_ms(choice)
                if latency is None or not isinstance(choice, dict):
                    continue
                player = str(choice.get("player") or "")
                samples.setdefault(player, []).append(latency)
    if not samples:
        return {"edges": [], "players": []}
    values = [value for group in samples.values() for value in group]
    edges = _latency_edges(min(values), max(values))
    players: list[dict[str, Any]] = []
    for player in sorted(samples):
        counts = [0] * len(edges)
        for value in samples[player]:
            counts[_latency_bin(value, edges)] += 1
        players.append({"player": player, "counts": counts, "n": len(samples[player])})
    return {"edges": edges, "players": players}


def _latency_ms(choice: object) -> int | None:
    if not isinstance(choice, dict):
        return None
    metadata = choice.get("metadata")
    if not isinstance(metadata, dict):
        return None
    latency = metadata.get("latency_ms")
    if isinstance(latency, bool) or not isinstance(latency, int):
        return None
    return latency


def _latency_edges(low: int, high: int) -> list[list[int]]:
    if low == high:
        return [[low, high]]
    span = high - low
    return [
        [
            low + (span * index) // _LATENCY_BINS,
            low + (span * (index + 1)) // _LATENCY_BINS,
        ]
        for index in range(_LATENCY_BINS)
    ]


def _latency_bin(value: int, edges: list[list[int]]) -> int:
    last = len(edges) - 1
    for index, (start, end) in enumerate(edges):
        if index == last or start <= value < end:
            return index
    return last


def render_page(games: list[dict[str, Any]]) -> str:
    games_payload = json.dumps(games).replace("<", "\\u003c")
    stats_payload = json.dumps(performance_by_metric(games)).replace("<", "\\u003c")
    seats_payload = json.dumps(performance_by_seat(games)).replace("<", "\\u003c")
    latency_payload = json.dumps(latency_histograms(games)).replace("<", "\\u003c")
    page = PAGE.replace("__PERFORMANCE__", stats_payload)
    page = page.replace("__BY_SEAT__", seats_payload)
    page = page.replace("__LATENCIES__", latency_payload)
    return page.replace("__GAMES__", games_payload)


def serve(games: list[dict[str, Any]]) -> None:
    page = render_page(games).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    print(url)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualize choices JSONL files and their evaluations",
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("data"),
        help="Choices file, or a directory of name.jsonl and name.evaluate.jsonl pairs",
    )
    parser.add_argument(
        "--eval",
        type=Path,
        default=None,
        help="Evaluation JSONL aligned with a choices file",
    )
    args = parser.parse_args()
    if args.path.is_dir():
        if args.eval is not None:
            raise SystemExit("--eval cannot be used with a directory")
        try:
            games = load_directory(args.path)
        except ValueError as err:
            raise SystemExit(str(err)) from err
    elif args.path.is_file():
        games = load_games(args.path)
        for game in games:
            game["source"] = args.path.stem
        if args.eval is not None:
            if not args.eval.is_file():
                raise SystemExit(f"evaluation file not found: {args.eval}")
            try:
                games = attach_evaluations(games, load_evaluations(args.eval))
            except ValueError as err:
                raise SystemExit(str(err)) from err
    else:
        raise SystemExit(f"path not found: {args.path}")
    serve(games)


if __name__ == "__main__":
    main()
