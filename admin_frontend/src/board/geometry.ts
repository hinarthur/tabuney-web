/**
 * Board geometry — pure functions, no React.
 *
 * Square boards: cell "x,y"; corner (vertex) "x,y" on the 0..cols × 0..rows
 * lattice; edge "h:x,y" runs from corner (x,y) to (x+1,y), "v:x,y" from (x,y)
 * to (x,y+1).
 *
 * Hex boards use axial coordinates (q,r). An edge is keyed by the two hexes it
 * separates and a vertex by the three hexes meeting there, each sorted and
 * joined with "|". Hexes off the board count too, so the outer rim still has
 * unique keys. Because the keys describe adjacency rather than screen position,
 * switching pointy/flat keeps every mark on the same edge / corner.
 */
import type { Board, CellData } from "./types";

export type Pt = { x: number; y: number };
export type CellGeom = { key: string; center: Pt; points: Pt[] };
export type EdgeGeom = { key: string; a: Pt; b: Pt };
export type VertexGeom = { key: string; p: Pt };

const SQRT3 = Math.sqrt(3);
// Axial neighbour offsets
const HEX_DIRS: Array<[number, number]> = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];

const ck = (a: number, b: number) => `${a},${b}`;

/** Square cell height; a missing cellH means square cells. */
export function squareH(board: Board): number {
  return board.cellH && board.cellH > 0 ? board.cellH : board.cellSize;
}

/** Unit for marks and automatic text size: the shorter side of a cell. */
export function cellUnit(board: Board): number {
  return board.shape === "square" ? Math.min(board.cellSize, squareH(board)) : board.cellSize;
}

export function parseKey(key: string): [number, number] {
  const [a, b] = key.split(",").map(Number);
  return [a, b];
}

function hexRadius(board: Board): number {
  // cellSize is the flat-to-flat width, so a hex sits in the same footprint as a square
  return board.cellSize / SQRT3;
}

function hexCenter(board: Board, q: number, r: number): Pt {
  const s = hexRadius(board);
  return board.hexOrient === "flat"
    ? { x: s * 1.5 * q, y: s * SQRT3 * (r + q / 2) }
    : { x: s * SQRT3 * (q + r / 2), y: s * 1.5 * r };
}

function hexCorners(board: Board, c: Pt): Pt[] {
  const s = hexRadius(board);
  const off = board.hexOrient === "flat" ? 0 : -30;
  return Array.from({ length: 6 }, (_, i) => {
    const a = ((60 * i + off) * Math.PI) / 180;
    return { x: c.x + s * Math.cos(a), y: c.y + s * Math.sin(a) };
  });
}

/** Every cell position the board's dimensions define, hidden ones included. */
export function allCellKeys(board: Board): string[] {
  const out: string[] = [];
  if (board.shape === "square") {
    for (let y = 0; y < board.rows; y++) for (let x = 0; x < board.cols; x++) out.push(ck(x, y));
    return out;
  }
  if (board.layout === "hexagon") {
    const R = Math.max(0, board.radius ?? 2);
    for (let r = -R; r <= R; r++) {
      for (let q = -R; q <= R; q++) {
        if (Math.abs(q + r) <= R) out.push(ck(q, r));
      }
    }
    return out;
  }
  // Rectangular hex layout: odd-r offset rows (pointy) / odd-q offset columns (flat)
  for (let row = 0; row < board.rows; row++) {
    for (let col = 0; col < board.cols; col++) {
      if (board.hexOrient === "flat") out.push(ck(col, row - Math.floor(col / 2)));
      else out.push(ck(col - Math.floor(row / 2), row));
    }
  }
  return out;
}

export function cellGeom(board: Board, key: string): CellGeom {
  const [a, b] = parseKey(key);
  if (board.shape === "square") {
    const w = board.cellSize, h = squareH(board);
    const x = a * w, y = b * h;
    return {
      key,
      center: { x: x + w / 2, y: y + h / 2 },
      points: [{ x, y }, { x: x + w, y }, { x: x + w, y: y + h }, { x, y: y + h }],
    };
  }
  const center = hexCenter(board, a, b);
  return { key, center, points: hexCorners(board, center) };
}

/** Cells that are drawn: inside the board dimensions and not hidden. */
export function visibleCells(board: Board, includeHidden = false): CellGeom[] {
  return allCellKeys(board)
    .filter((k) => includeHidden || !board.cells[k]?.hidden)
    .map((k) => cellGeom(board, k));
}

const dist2 = (p: Pt, q: Pt) => (p.x - q.x) ** 2 + (p.y - q.y) ** 2;

/** The n hex neighbours of (q,r) nearest to point p, as cell keys. */
function nearestNeighbours(board: Board, q: number, r: number, p: Pt, n: number): string[] {
  return HEX_DIRS
    .map(([dq, dr]) => ({ k: ck(q + dq, r + dr), d: dist2(hexCenter(board, q + dq, r + dr), p) }))
    .sort((x, y) => x.d - y.d)
    .slice(0, n)
    .map((x) => x.k);
}

const joinSorted = (keys: string[]) => [...keys].sort().join("|");

export function boardEdges(board: Board): EdgeGeom[] {
  const seen = new Map<string, EdgeGeom>();
  for (const cell of visibleCells(board)) {
    const [a, b] = parseKey(cell.key);
    if (board.shape === "square") {
      const w = board.cellSize, h = squareH(board);
      const x = a * w, y = b * h;
      const add = (key: string, p: Pt, q: Pt) => { if (!seen.has(key)) seen.set(key, { key, a: p, b: q }); };
      add(`h:${ck(a, b)}`,     { x, y },     { x: x + w, y });
      add(`h:${ck(a, b + 1)}`, { x, y: y + h }, { x: x + w, y: y + h });
      add(`v:${ck(a, b)}`,     { x, y },     { x, y: y + h });
      add(`v:${ck(a + 1, b)}`, { x: x + w, y }, { x: x + w, y: y + h });
      continue;
    }
    const pts = cell.points;
    for (let i = 0; i < 6; i++) {
      const p = pts[i], q = pts[(i + 1) % 6];
      const mid = { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 };
      const key = joinSorted([cell.key, ...nearestNeighbours(board, a, b, mid, 1)]);
      if (!seen.has(key)) seen.set(key, { key, a: p, b: q });
    }
  }
  return [...seen.values()];
}

export function boardVertices(board: Board): VertexGeom[] {
  const seen = new Map<string, VertexGeom>();
  for (const cell of visibleCells(board)) {
    const [a, b] = parseKey(cell.key);
    if (board.shape === "square") {
      const w = board.cellSize, h = squareH(board);
      for (const [dx, dy] of [[0, 0], [1, 0], [1, 1], [0, 1]]) {
        const key = ck(a + dx, b + dy);
        if (!seen.has(key)) seen.set(key, { key, p: { x: (a + dx) * w, y: (b + dy) * h } });
      }
      continue;
    }
    for (const p of cell.points) {
      const key = joinSorted([cell.key, ...nearestNeighbours(board, a, b, p, 2)]);
      if (!seen.has(key)) seen.set(key, { key, p });
    }
  }
  return [...seen.values()];
}

export type Bounds = { x: number; y: number; w: number; h: number };

export function boardBounds(board: Board, pad = 16): Bounds {
  const cells = visibleCells(board, true);
  if (!cells.length) return { x: 0, y: 0, w: 100, h: 100 };
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const c of cells) for (const p of c.points) {
    minX = Math.min(minX, p.x); minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y);
  }
  return { x: minX - pad, y: minY - pad, w: maxX - minX + pad * 2, h: maxY - minY + pad * 2 };
}

/**
 * Drop entries that no longer exist on the board (resized away). Run on Apply
 * only, so shrinking and re-growing the board while editing loses nothing.
 */
export function pruneBoard(board: Board): Board {
  const cellKeys = new Set(allCellKeys(board));
  const edgeKeys = new Set(boardEdges(board).map((e) => e.key));
  const vertexKeys = new Set(boardVertices(board).map((v) => v.key));
  const paletteIds = new Set(board.palette.map((p) => p.id));
  const pick = <T,>(rec: Record<string, T>, keep: Set<string>) =>
    Object.fromEntries(Object.entries(rec).filter(([k]) => keep.has(k)));
  const cells: Record<string, CellData> = {};
  for (const [k, v] of Object.entries(board.cells)) {
    if (!cellKeys.has(k)) continue;
    cells[k] = v.p && !paletteIds.has(v.p) ? { ...v, p: undefined } : v;
  }
  return {
    ...board,
    cells,
    edges: pick(board.edges, edgeKeys),
    vertices: pick(board.vertices, vertexKeys),
  };
}
