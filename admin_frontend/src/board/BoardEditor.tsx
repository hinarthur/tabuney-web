/**
 * Full-screen board editor opened from the flowchart editor's side panel.
 *
 * Works on a private draft; nothing reaches the flowchart until Apply, so a
 * whole editing session is one undo step on the canvas. Entries that fall off
 * the board while resizing are kept in the draft and only pruned on Apply.
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import BoardView from "./BoardView";
import { allCellKeys, boardEdges, boardVertices, cellUnit, pruneBoard } from "./geometry";
import { BOARD_TEMPLATES, PLAYER_COLORS } from "./templates";
import {
  emptyBoard,
  type Board,
  type BoardTarget,
  type CellData,
  type Mark,
  type MarkShape,
} from "./types";

type Tool = "select" | "paint" | "erase" | "hide";

const EDGE_SHAPES: Array<{ id: MarkShape; label: string }> = [
  { id: "none", label: "None" }, { id: "bar", label: "▬ Bar" }, { id: "dot", label: "● Dot" },
];
const VERTEX_SHAPES: Array<{ id: MarkShape; label: string }> = [
  { id: "none", label: "None" }, { id: "dot", label: "● Dot" },
  { id: "house", label: "⌂ House" }, { id: "city", label: "▙ City" },
];

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Math.round(v || 0)));

/** Shared value of `field` across the selected entries, or undefined when mixed. */
function common<T, K extends keyof T>(items: Array<T | undefined>, field: K): T[K] | undefined {
  if (!items.length) return undefined;
  const first = items[0]?.[field];
  return items.every((it) => it?.[field] === first) ? first : undefined;
}

export default function BoardEditor({ initial, nodeLabel, onApply, onRemove, onClose }: {
  initial: Board | null;
  nodeLabel: string;
  onApply: (board: Board) => void;
  onRemove: () => void;
  onClose: () => void;
}) {
  const [board, setBoard] = useState<Board>(() => initial ?? emptyBoard());
  const [tool, setTool] = useState<Tool>("select");
  const [target, setTarget] = useState<BoardTarget>("cell");
  const [selected, setSelected] = useState<string[]>([]);
  const [brush, setBrush] = useState<string | null>(board.palette[0]?.id ?? null);
  const [stamp, setStamp] = useState<{ color: string; edge: MarkShape; vertex: MarkShape }>(
    { color: PLAYER_COLORS[0].color, edge: "bar", vertex: "house" });
  const dragRef = useRef<{ hideTo?: boolean } | null>(null);
  const textRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const up = () => { dragRef.current = null; };
    window.addEventListener("pointerup", up);
    return () => window.removeEventListener("pointerup", up);
  }, []);

  // Selection is per target; switching target or shape starts fresh
  useEffect(() => { setSelected([]); }, [target, board.shape]);

  const isHex = board.shape === "hex";
  const orderedKeys = useMemo(() => {
    if (target === "cell") return allCellKeys(board);
    if (target === "edge") return boardEdges(board).map((e) => e.key);
    return boardVertices(board).map((v) => v.key);
  }, [board, target]);

  // ── mutations ───────────────────────────────────────────────────────────────
  const set = (patch: Partial<Board>) => setBoard((b) => ({ ...b, ...patch }));

  function patchEntries(kind: BoardTarget, keys: string[], patch: Partial<CellData & Mark> | null) {
    setBoard((b) => {
      const field = kind === "cell" ? "cells" : kind === "edge" ? "edges" : "vertices";
      const rec: Record<string, any> = { ...b[field] };
      for (const k of keys) {
        if (patch === null) { delete rec[k]; continue; }
        const next = { ...(rec[k] ?? {}), ...patch };
        // Drop empty fields so the stored JSON stays sparse
        for (const f of Object.keys(next)) {
          if (next[f] === "" || next[f] === undefined || next[f] === false || next[f] === "none") delete next[f];
        }
        if (Object.keys(next).length) rec[k] = next; else delete rec[k];
      }
      return { ...b, [field]: rec };
    });
  }

  function applyTool(kind: BoardTarget, key: string, first: boolean, e: React.PointerEvent) {
    if (tool === "select") {
      if (!first) return;
      const id = key;
      setSelected((cur) => e.shiftKey
        ? (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id])
        : [id]);
      // Keep typing flow: a click then straight into the text box
      setTimeout(() => textRef.current?.focus(), 0);
      return;
    }
    if (tool === "erase") { patchEntries(kind, [key], null); return; }
    if (tool === "hide") {
      if (kind !== "cell") return;
      if (first) dragRef.current = { hideTo: !board.cells[key]?.hidden };
      patchEntries("cell", [key], { hidden: dragRef.current?.hideTo ?? true });
      return;
    }
    // paint
    if (kind === "cell") { if (brush) patchEntries("cell", [key], { p: brush }); return; }
    patchEntries(kind, [key], { color: stamp.color, shape: kind === "edge" ? stamp.edge : stamp.vertex });
  }

  const interactive = {
    target,
    selected: new Set(selected.map((k) => `${target}:${k}`)),
    onDown: (kind: BoardTarget, key: string, e: React.PointerEvent) => {
      e.preventDefault();
      dragRef.current = dragRef.current ?? {};
      applyTool(kind, key, true, e);
    },
    onEnter: (kind: BoardTarget, key: string, e: React.PointerEvent) => {
      if (dragRef.current && (e.buttons & 1) && tool !== "select") applyTool(kind, key, false, e);
    },
  };

  // ── selection panel values ─────────────────────────────────────────────────
  const selEntries: Array<(CellData & Mark) | undefined> = selected.map((k) =>
    target === "cell" ? board.cells[k] : target === "edge" ? board.edges[k] : board.vertices[k]);
  const selText = common(selEntries, "text") ?? "";
  const textMixed = selected.length > 1 && common(selEntries, "text") === undefined && selEntries.some((x) => x?.text);

  function stepSelection(dir: 1 | -1) {
    if (selected.length !== 1) return;
    const i = orderedKeys.indexOf(selected[0]);
    if (i < 0) return;
    setSelected([orderedKeys[(i + dir + orderedKeys.length) % orderedKeys.length]]);
  }

  function applyTemplate(id: string) {
    const t = BOARD_TEMPLATES.find((x) => x.id === id);
    if (!t) return;
    const hasContent = Object.keys(board.cells).length || Object.keys(board.edges).length || Object.keys(board.vertices).length;
    if (hasContent && !confirm("Replace the current board with this template?")) return;
    const next = t.build();
    setBoard(next);
    setBrush(next.palette[0]?.id ?? null);
    setSelected([]);
  }

  function addPaletteEntry() {
    const id = `p${Date.now().toString(36)}`;
    set({ palette: [...board.palette, { id, label: "New", color: "#9CCB9F" }] });
    setBrush(id);
  }

  const numInput = (label: string, value: number, lo: number, hi: number, onChange: (v: number) => void) => (
    <label className="fc-be-field">
      {label}
      <input type="number" min={lo} max={hi} value={value}
        onChange={(e) => onChange(clamp(Number(e.target.value), lo, hi))} />
    </label>
  );

  const seg = <T extends string>(value: T, opts: Array<{ id: T; label: string }>, onChange: (v: T) => void) => (
    <span className="fc-be-seg">
      {opts.map((o) => (
        <button key={o.id} type="button" className={value === o.id ? "active" : ""} onClick={() => onChange(o.id)}>
          {o.label}
        </button>
      ))}
    </span>
  );

  const shapeOpts = target === "edge" ? EDGE_SHAPES : VERTEX_SHAPES;

  return (
    <div className="fc-board-backdrop">
      <div className="fc-be" role="dialog" aria-modal="true" aria-label="Board editor">
        {/* ── header ── */}
        <div className="fc-be-head">
          <strong>Board — {nodeLabel || "step"}</strong>
          <span style={{ flex: 1 }} />
          {initial && (
            <button type="button" className="fc-be-danger"
              onClick={() => { if (confirm("Remove this board from the step?")) onRemove(); }}>🗑 Remove</button>
          )}
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="button" className="fc-be-primary" onClick={() => onApply(pruneBoard(board))}>Apply</button>
        </div>

        {/* ── board settings ── */}
        <div className="fc-be-bar">
          <label className="fc-be-field">
            Template
            <select value="" onChange={(e) => applyTemplate(e.target.value)}>
              <option value="">—</option>
              {BOARD_TEMPLATES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </label>
          {seg(board.shape, [{ id: "square", label: "■ Square" }, { id: "hex", label: "⬡ Hex" }], (v) => set({ shape: v }))}
          {isHex && seg(board.hexOrient ?? "pointy", [{ id: "pointy", label: "Pointy" }, { id: "flat", label: "Flat" }], (v) => set({ hexOrient: v }))}
          {isHex && seg(board.layout, [{ id: "rect", label: "Rect" }, { id: "hexagon", label: "Hexagon" }], (v) => set({ layout: v }))}
          {isHex && board.layout === "hexagon"
            ? numInput("Radius", board.radius ?? 2, 0, 8, (v) => set({ radius: v }))
            : <>
                {numInput("Cols", board.cols, 1, 30, (v) => set({ cols: v }))}
                {numInput("Rows", board.rows, 1, 30, (v) => set({ rows: v }))}
              </>}
          <label className="fc-be-field">
            {isHex ? "Size" : "Width"}
            <input type="range" min={24} max={160} value={board.cellSize}
              onChange={(e) => set({ cellSize: Number(e.target.value) })} />
            <span className="fc-be-minor">{board.cellSize}</span>
          </label>
          {!isHex && (
            <label className="fc-be-field">
              Height
              <input type="range" min={24} max={160} value={board.cellH ?? board.cellSize}
                onChange={(e) => set({ cellH: Number(e.target.value) })} />
              <span className="fc-be-minor">{board.cellH ?? board.cellSize}</span>
              {board.cellH !== undefined && board.cellH !== board.cellSize && (
                <button type="button" title="Make cells square again" onClick={() => set({ cellH: undefined })}>= W</button>
              )}
            </label>
          )}
          <label className="fc-be-field">
            Font
            <input type="range" min={8} max={48} value={Math.round(board.fontSize ?? cellUnit(board) * 0.3)}
              onChange={(e) => set({ fontSize: Number(e.target.value) })} />
            <span className="fc-be-minor">{Math.round(board.fontSize ?? cellUnit(board) * 0.3)}</span>
            {board.fontSize !== undefined && (
              <button type="button" title="Back to automatic (follows cell size)"
                onClick={() => set({ fontSize: undefined })}>Auto</button>
            )}
          </label>
          <label className="fc-be-field">
            Title
            <input type="text" value={board.title ?? ""} placeholder="(step label)"
              onChange={(e) => set({ title: e.target.value })} />
          </label>
        </div>

        <div className="fc-be-body">
          {/* ── canvas ── */}
          <div className="fc-be-canvas-col">
            <div className="fc-be-bar">
              {seg(tool, [
                { id: "select", label: "▢ Select" }, { id: "paint", label: "🖌 Paint" },
                { id: "erase", label: "⌫ Erase" }, { id: "hide", label: "👁 Hide cell" },
              ], (v) => { setTool(v); if (v === "hide") setTarget("cell"); })}
              <span className="fc-be-minor">Target:</span>
              {seg(target, [{ id: "cell", label: "Cell" }, { id: "edge", label: "Edge" }, { id: "vertex", label: "Corner" }],
                (v) => { setTarget(v); if (tool === "hide" && v !== "cell") setTool("select"); })}
            </div>
            <div className="fc-be-hint">
              {tool === "select" && "Click to select · Shift+click to add · Tab in the text box moves to the next one"}
              {tool === "paint" && (target === "cell" ? "Click or drag to paint with the palette colour on the right" : "Click or drag to stamp the colour / shape on the right")}
              {tool === "erase" && "Click or drag to clear"}
              {tool === "hide" && "Click or drag to cut cells out of the board (click a dashed cell to bring it back)"}
            </div>
            <div className="fc-be-canvas">
              <BoardView board={board} interactive={interactive} showHidden />
            </div>
          </div>

          {/* ── side panel ── */}
          <div className="fc-be-side">
            <div className="fc-be-section">
              <div className="fc-be-section-title">Palette (cell types)</div>
              {board.palette.map((p, i) => (
                <div key={p.id} className={`fc-be-pal-row${brush === p.id ? " active" : ""}`}
                  onClick={() => { setBrush(p.id); if (target === "cell" && tool !== "select") setTool("paint"); }}>
                  <input type="color" value={p.color}
                    onChange={(e) => set({ palette: board.palette.map((x, j) => j === i ? { ...x, color: e.target.value } : x) })} />
                  <input type="text" value={p.label}
                    onChange={(e) => set({ palette: board.palette.map((x, j) => j === i ? { ...x, label: e.target.value } : x) })} />
                  <button type="button" title="Delete"
                    onClick={(e) => { e.stopPropagation(); set({ palette: board.palette.filter((_, j) => j !== i) }); }}>✕</button>
                </div>
              ))}
              <button type="button" onClick={addPaletteEntry}>+ Add type</button>
            </div>

            {tool === "paint" && target !== "cell" && (
              <div className="fc-be-section">
                <div className="fc-be-section-title">Stamp</div>
                <ColorPicker value={stamp.color} onChange={(c) => setStamp({ ...stamp, color: c })} />
                {seg(target === "edge" ? stamp.edge : stamp.vertex, shapeOpts,
                  (v) => setStamp(target === "edge" ? { ...stamp, edge: v } : { ...stamp, vertex: v }))}
              </div>
            )}

            <div className="fc-be-section">
              <div className="fc-be-section-title">
                Selected {target === "vertex" ? "corner" : target}{selected.length > 1 ? `s (${selected.length})` : ""}
              </div>
              {!selected.length && <div className="fc-be-minor">Use ▢ Select and click on the board.</div>}
              {selected.length > 0 && (
                <>
                  <label className="fc-be-field fc-be-col">
                    Text
                    <input ref={textRef} type="text" value={selText} placeholder={textMixed ? "(mixed)" : ""}
                      onChange={(e) => patchEntries(target, selected, { text: e.target.value })}
                      onKeyDown={(e) => { if (e.key === "Tab" && selected.length === 1) { e.preventDefault(); stepSelection(e.shiftKey ? -1 : 1); } }} />
                  </label>

                  {target === "cell" && (
                    <>
                      <label className="fc-be-field fc-be-col">
                        Type
                        <select value={common(selEntries, "p") ?? ""}
                          onChange={(e) => patchEntries("cell", selected, { p: e.target.value || undefined })}>
                          <option value="">— none —</option>
                          {board.palette.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                        </select>
                      </label>
                      <label className="fc-be-check">
                        <input type="checkbox" checked={!!common(selEntries, "hidden")}
                          onChange={(e) => patchEntries("cell", selected, { hidden: e.target.checked })} />
                        Hidden (cut out of the board)
                      </label>
                    </>
                  )}

                  {target !== "cell" && (
                    <>
                      <div className="fc-be-field fc-be-col">
                        Colour
                        <ColorPicker value={common(selEntries, "color") ?? ""}
                          onChange={(c) => patchEntries(target, selected, { color: c })} />
                      </div>
                      <div className="fc-be-field fc-be-col">
                        Shape
                        {seg((common(selEntries, "shape") ?? "none") as MarkShape, shapeOpts,
                          (v) => patchEntries(target, selected, { shape: v }))}
                      </div>
                    </>
                  )}

                  <button type="button" onClick={() => patchEntries(target, selected, null)}>Clear selected</button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ColorPicker({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  return (
    <div className="fc-be-colors">
      {PLAYER_COLORS.map((c) => (
        <button key={c.color} type="button" title={c.label}
          className={`fc-be-swatch${value.toLowerCase() === c.color.toLowerCase() ? " active" : ""}`}
          style={{ background: c.color }} onClick={() => onChange(c.color)} />
      ))}
      <input type="color" value={/^#[0-9a-f]{6}$/i.test(value) ? value : "#333333"}
        title="Custom colour" onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
