/**
 * SVG renderer for a Board. Read-only by default; the editor passes
 * `interactive` to get hit areas, hover and selection highlighting from the
 * very same drawing, so what you edit is exactly what the reader sees.
 *
 * Layers, bottom to top: cells (+ cell text) → edges → vertices → hit areas.
 */
import React, { useMemo } from "react";
import type { Board, BoardTarget, Mark, MarkShape } from "./types";
import { boardBounds, boardEdges, boardVertices, cellUnit, visibleCells, type Pt } from "./geometry";

export type Interactive = {
  target: BoardTarget;
  selected: Set<string>;        // "cell:<key>" / "edge:<key>" / "vertex:<key>"
  onDown: (kind: BoardTarget, key: string, e: React.PointerEvent) => void;
  onEnter?: (kind: BoardTarget, key: string, e: React.PointerEvent) => void;
};

const DEFAULT_MARK_COLOR = "#333333";

function MarkerShape({ shape, at, u, color }: { shape: MarkShape; at: Pt; u: number; color: string }) {
  const common = {
    fill: color,
    stroke: "var(--fc-board-mark-outline, #222)",
    strokeWidth: Math.max(1, u * 0.08),
    strokeLinejoin: "round" as const,
  };
  const poly = (pts: Array<[number, number]>) =>
    pts.map(([x, y]) => `${at.x + x * u},${at.y + y * u}`).join(" ");
  if (shape === "dot") return <circle cx={at.x} cy={at.y} r={u * 0.5} {...common} />;
  if (shape === "house") {
    return <polygon {...common} points={poly([[-0.5, 0.45], [0.5, 0.45], [0.5, -0.05], [0, -0.5], [-0.5, -0.05]])} />;
  }
  if (shape === "city") {
    return <polygon {...common} points={poly([[-0.7, 0.45], [0.7, 0.45], [0.7, -0.15], [0.1, -0.15], [0.1, -0.35], [-0.3, -0.7], [-0.7, -0.35]])} />;
  }
  return null;
}

function Label({ at, text, size, dy = 0 }: { at: Pt; text: string; size: number; dy?: number }) {
  return (
    <text x={at.x} y={at.y + dy} fontSize={size} textAnchor="middle" dominantBaseline="central"
      fontWeight={600} fill="var(--fc-board-text, #222)"
      stroke="var(--fc-board-text-halo, #fff)" strokeWidth={size * 0.22} paintOrder="stroke"
      strokeLinejoin="round" style={{ pointerEvents: "none", userSelect: "none" }}>
      {text}
    </text>
  );
}

export default function BoardView({ board, interactive, scale = 1, showHidden = false }: {
  board: Board;
  interactive?: Interactive;
  scale?: number;
  showHidden?: boolean;   // editor: draw hidden cells as dashed ghosts so they can be un-hidden
}) {
  const cells = useMemo(() => visibleCells(board, showHidden), [board, showHidden]);
  const edges = useMemo(() => boardEdges(board), [board]);
  const vertices = useMemo(() => boardVertices(board), [board]);
  const b = useMemo(() => boardBounds(board), [board]);
  const colorOf = useMemo(() => new Map(board.palette.map((p) => [p.id, p.color])), [board.palette]);

  const s = cellUnit(board);
  const fs = board.fontSize ?? s * 0.3;   // cell text; edge / corner text is smaller
  const fsSmall = fs * 0.75;
  const sel = interactive?.selected;
  const hl = "var(--color-primary, #168BC3)";

  const markColor = (m: Mark) => m.color || DEFAULT_MARK_COLOR;
  const usedPalette = board.palette.filter((p) =>
    Object.values(board.cells).some((c) => c.p === p.id && !c.hidden));

  const hit = (kind: BoardTarget, key: string) => interactive?.target === kind ? {
    onPointerDown: (e: React.PointerEvent) => interactive.onDown(kind, key, e),
    onPointerEnter: (e: React.PointerEvent) => interactive.onEnter?.(kind, key, e),
    style: { cursor: "pointer" },
  } : {};

  return (
    <div className="fc-board-view">
      <svg viewBox={`${b.x} ${b.y} ${b.w} ${b.h}`} width={b.w * scale} height={b.h * scale}
           style={{ maxWidth: "100%", height: "auto", touchAction: interactive ? "none" : undefined }}>
        {/* Cells */}
        {cells.map((c) => {
          const data = board.cells[c.key];
          const isSel = sel?.has(`cell:${c.key}`);
          const ghost = !!data?.hidden;
          return (
            <polygon key={c.key} className={interactive?.target === "cell" ? "fc-board-hit" : undefined}
              points={c.points.map((p) => `${p.x},${p.y}`).join(" ")}
              fill={ghost ? "transparent" : (data?.p && colorOf.get(data.p)) || "var(--fc-board-cell, #F4F1EA)"}
              stroke={isSel ? hl : "var(--fc-board-line, #8C8577)"}
              strokeWidth={isSel ? 3 : 1}
              strokeDasharray={ghost ? "4 4" : undefined}
              {...hit("cell", c.key)} />
          );
        })}
        {cells.map((c) => {
          const t = board.cells[c.key]?.hidden ? "" : board.cells[c.key]?.text;
          return t ? <Label key={`t${c.key}`} at={c.center} text={t} size={fs} /> : null;
        })}

        {/* Edges */}
        {edges.map((e) => {
          const m = board.edges[e.key];
          const isSel = sel?.has(`edge:${e.key}`);
          if (!m && !isSel) return null;
          const mid = { x: (e.a.x + e.b.x) / 2, y: (e.a.y + e.b.y) / 2 };
          return (
            <g key={e.key} style={{ pointerEvents: "none" }}>
              {isSel && <line x1={e.a.x} y1={e.a.y} x2={e.b.x} y2={e.b.y} stroke={hl} strokeWidth={s * 0.2} strokeLinecap="round" opacity={0.45} />}
              {m?.shape === "bar" && (
                <line x1={e.a.x} y1={e.a.y} x2={e.b.x} y2={e.b.y}
                  stroke={markColor(m)} strokeWidth={s * 0.12} strokeLinecap="round" />
              )}
              {m?.shape && m.shape !== "bar" && <MarkerShape shape={m.shape} at={mid} u={s * 0.22} color={markColor(m)} />}
              {m?.text && <Label at={mid} text={m.text} size={fsSmall} />}
            </g>
          );
        })}

        {/* Vertices */}
        {vertices.map((v) => {
          const m = board.vertices[v.key];
          const isSel = sel?.has(`vertex:${v.key}`);
          if (!m && !isSel) return null;
          const hasShape = m?.shape && m.shape !== "none" && m.shape !== "bar";
          return (
            <g key={v.key} style={{ pointerEvents: "none" }}>
              {isSel && <circle cx={v.p.x} cy={v.p.y} r={s * 0.2} fill={hl} opacity={0.45} />}
              {hasShape && <MarkerShape shape={m!.shape!} at={v.p} u={s * 0.28} color={markColor(m!)} />}
              {m?.text && <Label at={v.p} text={m.text} size={fsSmall} dy={hasShape ? -s * 0.32 - Math.max(0, fsSmall - s * 0.22) / 2 : 0} />}
            </g>
          );
        })}

        {/* Hit areas for edges / vertices, drawn last so they sit above the cells */}
        {interactive?.target === "edge" && edges.map((e) => (
          <line key={`h${e.key}`} className="fc-board-hit" x1={e.a.x} y1={e.a.y} x2={e.b.x} y2={e.b.y}
            stroke="transparent" strokeWidth={s * 0.25} strokeLinecap="round" {...hit("edge", e.key)} />
        ))}
        {interactive?.target === "vertex" && vertices.map((v) => (
          <circle key={`h${v.key}`} className="fc-board-hit" cx={v.p.x} cy={v.p.y} r={s * 0.18}
            fill="transparent" {...hit("vertex", v.key)} />
        ))}
      </svg>

      {usedPalette.length > 0 && (
        <div className="fc-board-legend">
          {usedPalette.map((p) => (
            <span key={p.id} className="fc-board-legend-item">
              <span className="fc-board-swatch" style={{ background: p.color }} />
              {p.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
