/**
 * A board diagram bound to a flowchart step (node.data.board). Rendered only in
 * a popup opened from the node's ⊞ button, never on the canvas itself.
 *
 * Everything is sparse: a cell / edge / vertex with nothing set has no entry.
 * Keys are orientation-independent (see geometry.ts), so flipping pointy/flat
 * or square/hex never scrambles what was placed.
 */
export type BoardShape = "square" | "hex";
export type HexOrient = "pointy" | "flat";
export type BoardLayout = "rect" | "hexagon";
export type MarkShape = "none" | "dot" | "house" | "city" | "bar";

export type PaletteEntry = { id: string; label: string; color: string };
export type CellData = { p?: string; text?: string; hidden?: boolean };
export type Mark = { text?: string; color?: string; shape?: MarkShape };

export type Board = {
  shape: BoardShape;
  hexOrient?: HexOrient;
  layout: BoardLayout;
  cols: number;
  rows: number;
  radius?: number;
  cellSize: number;       // cell width (hex: flat-to-flat width)
  cellH?: number;         // square boards only: cell height, default = cellSize
  fontSize?: number;      // cell text px; edge / corner text is 75% of it. Default: 30% of cellSize
  title?: string;
  palette: PaletteEntry[];
  cells: Record<string, CellData>;
  edges: Record<string, Mark>;
  vertices: Record<string, Mark>;
};

export type BoardTarget = "cell" | "edge" | "vertex";

export function emptyBoard(): Board {
  return {
    shape: "square", hexOrient: "pointy", layout: "rect",
    cols: 5, rows: 5, radius: 2, cellSize: 48,
    title: "", palette: [], cells: {}, edges: {}, vertices: {},
  };
}

/** Accept whatever is stored in node.data.board; null when it is not a board. */
export function asBoard(raw: unknown): Board | null {
  if (!raw || typeof raw !== "object") return null;
  const b = raw as Partial<Board>;
  if (b.shape !== "square" && b.shape !== "hex") return null;
  return { ...emptyBoard(), ...b } as Board;
}
