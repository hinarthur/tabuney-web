/**
 * Starting points for the board editor. Each build() returns a fresh board;
 * adding a template is just another entry here.
 */
import { allCellKeys } from "./geometry";
import { emptyBoard, type Board } from "./types";

export const PLAYER_COLORS = [
  { label: "Red",    color: "#D7263D" },
  { label: "Blue",   color: "#1E5BC6" },
  { label: "White",  color: "#F5F5F5" },
  { label: "Orange", color: "#F28C28" },
  { label: "Green",  color: "#2E9E44" },
  { label: "Brown",  color: "#7A4A23" },
  { label: "Black",  color: "#222222" },
];

const CATAN_PALETTE = [
  { id: "forest",    label: "Forest",    color: "#2E7D32" },
  { id: "hills",     label: "Hills",     color: "#C0622B" },
  { id: "pasture",   label: "Pasture",   color: "#9CCC65" },
  { id: "fields",    label: "Fields",    color: "#F2C14E" },
  { id: "mountains", label: "Mountains", color: "#8D99A6" },
  { id: "desert",    label: "Desert",    color: "#E8D8A8" },
  { id: "sea",       label: "Sea",       color: "#4FA3D9" },
];

// 19 land hexes, outer ring first then inward, desert in the middle. The
// counts match the base game (4 forest / 3 hills / 4 pasture / 4 fields /
// 3 mountains / 1 desert); the arrangement is just a starting point to repaint.
const CATAN_TERRAIN = [
  "mountains", "pasture", "forest", "fields", "hills", "pasture", "hills", "fields", "forest", "forest", "mountains", "fields",
  "fields", "forest", "hills", "pasture", "mountains", "pasture",
  "desert",
];

function ringOrder(radius: number): string[] {
  // Cells of a hexagon-shaped board sorted outer ring → centre, clockwise
  const keys = allCellKeys({ ...emptyBoard(), shape: "hex", layout: "hexagon", radius });
  const ring = (k: string) => {
    const [q, r] = k.split(",").map(Number);
    return Math.max(Math.abs(q), Math.abs(r), Math.abs(q + r));
  };
  const angle = (k: string) => {
    const [q, r] = k.split(",").map(Number);
    return Math.atan2(1.5 * r, Math.sqrt(3) * (q + r / 2));
  };
  return keys.sort((a, b) => ring(b) - ring(a) || angle(a) - angle(b));
}

export const BOARD_TEMPLATES: Array<{ id: string; label: string; build: () => Board }> = [
  {
    id: "catan",
    label: "Catan — base board (19 hexes)",
    build: () => {
      const order = ringOrder(2);
      return {
        ...emptyBoard(),
        shape: "hex", hexOrient: "pointy", layout: "hexagon", radius: 2, cellSize: 60,
        palette: CATAN_PALETTE.map((p) => ({ ...p })),
        cells: Object.fromEntries(order.map((k, i) => [k, { p: CATAN_TERRAIN[i] }])),
      };
    },
  },
  {
    id: "catan-sea",
    label: "Catan — with sea frame (radius 3)",
    build: () => {
      const inner = ringOrder(2);
      const cells: Board["cells"] = Object.fromEntries(inner.map((k, i) => [k, { p: CATAN_TERRAIN[i] }]));
      for (const k of ringOrder(3)) if (!cells[k]) cells[k] = { p: "sea" };
      return {
        ...emptyBoard(),
        shape: "hex", hexOrient: "pointy", layout: "hexagon", radius: 3, cellSize: 56,
        palette: CATAN_PALETTE.map((p) => ({ ...p })),
        cells,
      };
    },
  },
  {
    id: "square-8",
    label: "Square grid 8 × 8",
    build: () => ({ ...emptyBoard(), shape: "square", cols: 8, rows: 8, cellSize: 44 }),
  },
  {
    id: "hex-rect",
    label: "Hex grid 7 × 5",
    build: () => ({ ...emptyBoard(), shape: "hex", hexOrient: "pointy", layout: "rect", cols: 7, rows: 5 }),
  },
];
