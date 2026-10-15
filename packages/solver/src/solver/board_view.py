"""Board drawing shared by the choices viewer and the human player page."""

BOARD_CSS = """\
  .board { max-width: 900px; overflow: hidden; border-radius: 8px; background: #017DD5; }
  svg { display: block; width: 100%; height: auto; background: #017DD5; shape-rendering: crispEdges; }
  .hex polygon { opacity: 0.8; }
  .hex:hover polygon { opacity: 1; }
  .hex text, .hex circle { pointer-events: none; }
  .hex .coordinate { display: none; }
  .hex:hover .coordinate { display: inline; }
"""

BOARD_JS = """\
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
"""
