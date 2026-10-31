import React, { useContext, useLayoutEffect, useRef } from "react";
import {
  Handle,
  Position,
  NodeResizer,
  useNodeId,
  useReactFlow,
  type NodeProps,
} from "@xyflow/react";
import { ReadOnlyContext } from "../ReadOnlyContext";
import { BoardContext } from "../board/BoardContext";

type NodeData = {
  label: string;
  kind: string;
  phase_id: string | null;
  phase_label?: string | null;
  phase_order?: number | null;
  customBorder?: string;
};

// Per-node border colour. `data.customBorder` is set from the editor's
// "Border color" picker; when unset each shape falls back to its own default.
function borderColor(data: unknown, fallback: string): string {
  void data;
  return fallback;
}

// ── Phase colours for action nodes ───────────────────────────────────────────
// Theme variables (--fc-phaseN-*) defined in theme.css, with light and dark sets.
export type PhaseTheme = { bg: string; border: string; text: string };

const PHASE_ACTION_THEMES: Record<number, PhaseTheme> = {
  1: { bg: "var(--fc-phase1-bg, #E8F4E5)", border: "var(--fc-phase1-border, #9CCB9F)", text: "var(--fc-phase1-text, #2F6B3A)" }, // Preparation
  2: { bg: "var(--fc-phase2-bg, #E3EEFA)", border: "var(--fc-phase2-border, #8FB3D9)", text: "var(--fc-phase2-text, #2F5E8E)" }, // Game Flow
  3: { bg: "var(--fc-phase3-bg, #FBE9E7)", border: "var(--fc-phase3-border, #E0A9A2)", text: "var(--fc-phase3-text, #8A4A44)" }, // Endgame
};

// phase_order is the reliable signal: every chart in the corpus uses 1/2/3 for
// Preparation / Game Flow / Endgame, while phase_id has drifted across ten
// different spellings ("sequence", "gameflow", "round_play", "play_phase", …).
// The id/label keywords are only a fallback for data with no order.
function phaseSlot(d: NodeData): number | null {
  const order = d.phase_order;
  if (order === 1 || order === 2 || order === 3) return order;

  const hay = `${d.phase_id ?? ""} ${d.phase_label ?? ""}`.toLowerCase();
  if (!hay.trim()) return null;
  if (/setup|prepar/.test(hay)) return 1;
  if (/end|final|scor/.test(hay)) return 3;
  if (/sequence|flow|play|round|turn/.test(hay)) return 2;
  return null;
}

/** The fixed colour set for an action node's phase, or null when it has none. */
export function phaseActionTheme(data: unknown): PhaseTheme | null {
  const d = data as NodeData | undefined;
  if (!d) return null;
  const slot = phaseSlot(d);
  return slot ? PHASE_ACTION_THEMES[slot] : null;
}

// Tour-only: FlowchartTour injects data.onShowLegend into the current node when
// it has legends bound (data.legend_ids). Never present in the editor.
function LegendButton({ data }: { data: unknown }) {
  const fn = (data as { onShowLegend?: () => void } | undefined)?.onShowLegend;
  if (typeof fn !== "function") return null;
  return (
    <button
      type="button"
      className="fc-node-legend-btn nodrag nopan"
      aria-label="Legend"
      onClick={(e) => { e.stopPropagation(); fn(); }}
    >
      <i className="fa-solid fa-circle-info" aria-hidden="true" />
    </button>
  );
}

// A board diagram bound to this step (data.board) opens from this button in
// every mount — the editor opens the board editor, viewers the read-only popup.
function BoardButton({ data }: { data: unknown }) {
  const ctx = useContext(BoardContext);
  const id = useNodeId();
  const board = (data as { board?: unknown } | undefined)?.board;
  if (!ctx || !id || !board || typeof board !== "object") return null;
  return (
    <button
      type="button"
      className="fc-node-board-btn nodrag nopan"
      aria-label="Board"
      onClick={(e) => { e.stopPropagation(); ctx.openBoard(id); }}
    >
      {/* Text glyph, not Font Awesome: the admin pages don't load FA */}
      <span aria-hidden="true">⊞</span>
    </button>
  );
}

// ── OvalNode (start / end) ────────────────────────────────────────────────────
export function OvalNode({ data, selected }: NodeProps) {
  const readOnly = useContext(ReadOnlyContext);
  const d = data as unknown as NodeData;
  const isEnd = d.kind === "end";
  const bg = (isEnd ? "var(--fc-oval-end-bg, #ff4d4f)" : "var(--fc-oval-start-bg, #52c41a)");
  const kindVar = isEnd ? "end" : "start";
  const textColor = `var(--fc-oval-${kindVar}-text, var(--fc-oval-text, #fff))`;
  const hStyle = readOnly ? { visibility: "hidden" as const } : undefined;

  return (
    <>
      {selected && !readOnly && <NodeResizer minWidth={80} minHeight={36} />}
      <div
        data-fc-node="oval"
        data-fc-kind={d.kind}
        style={{
          position: "relative",
          backgroundColor: bg, color: textColor,
          border: selected && !readOnly
            ? "2px solid var(--fc-select)"
            : `2px solid ${borderColor(d, `var(--fc-oval-${kindVar}-border, transparent)`)}`,
          boxShadow: "var(--fc-node-shadow, none)",
          borderRadius: 9999, fontWeight: 600, fontSize: 12, userSelect: "none",
          width: "100%", height: "100%", boxSizing: "border-box",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}
      >
        <Handle type="source" position={Position.Left}   id="left"   style={hStyle} />
        <Handle type="source" position={Position.Top}    id="top"    style={hStyle} />
        <Handle type="source" position={Position.Right}  id="right"  style={hStyle} />
        <Handle type="source" position={Position.Bottom} id="bottom" style={hStyle} />
        <span style={{ whiteSpace: "pre-wrap", padding: "8px 16px", textAlign: "center" }}>{d.label}</span>
        <LegendButton data={d} />
        <BoardButton data={d} />
      </div>
    </>
  );
}

// Fixed 11px font. Instead of shrinking text, the diamond grows (never shrinks)
// until the label fits the inscribed text box (60% x 40% of the node).
const DIAMOND_FONT = 11;
function DiamondLabel({ text, color }: { text: string; color: string }) {
  const id = useNodeId();
  const { getNode, updateNode } = useReactFlow();
  const measureRef = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const m = measureRef.current;
    const node = id ? getNode(id) : undefined;
    if (!m || !node) return;
    const curW = Number(node.style?.width ?? node.width ?? 140);
    const curH = Number(node.style?.height ?? node.height ?? 50);
    const needH = (w: number) => {
      m.style.width = `${w * 0.6}px`;
      return Math.ceil(m.scrollHeight / 0.4) + 2;
    };
    let w = curW;
    let h = needH(w);
    // keep the shape reasonable: widen instead of getting very tall
    while (h > w * 0.8 && w < 420) { w += 10; h = needH(w); }
    h = Math.max(h, curH);
    if (w > curW + 0.5 || h > curH + 0.5) {
      updateNode(id!, { style: { ...(node.style ?? {}), width: w, height: h } });
    }
  }, [text, id]);
  return (
    <>
      <span ref={measureRef} aria-hidden style={{ position: "absolute", visibility: "hidden", pointerEvents: "none", fontSize: DIAMOND_FONT, lineHeight: 1.2, whiteSpace: "pre-wrap", overflowWrap: "anywhere", boxSizing: "border-box" }}>{text}</span>
      <div style={{ position: "absolute", top: "27%", bottom: "27%", left: "20%", right: "20%", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontSize: DIAMOND_FONT, lineHeight: 1.2, textAlign: "center", overflowWrap: "anywhere", whiteSpace: "pre-wrap", color, maxWidth: "100%" }}>{text}</span>
      </div>
    </>
  );
}

// ── DiamondNode (decision) ────────────────────────────────────────────────────
export function DiamondNode({ data, selected }: NodeProps) {
  const readOnly = useContext(ReadOnlyContext);
  const d = data as unknown as NodeData;
  const bg = "var(--fc-diamond-bg, #1677ff)";
  const textColor = "var(--fc-diamond-text, #fff)";
  const hv = readOnly ? "hidden" as const : "visible" as const;

  return (
    <>
      {selected && !readOnly && <NodeResizer minWidth={80} minHeight={50} />}
      <div data-fc-node="diamond" style={{ position: "relative", width: "100%", height: "100%" }}>
        <Handle type="source" position={Position.Left}   id="left"   style={{ left: 2,   visibility: hv }} />
        <Handle type="source" position={Position.Top}    id="top"    style={{ top: 2,    visibility: hv }} />
        <Handle type="source" position={Position.Right}  id="right"  style={{ right: 2,  visibility: hv }} />
        <Handle type="source" position={Position.Bottom} id="bottom" style={{ bottom: 2, visibility: hv }} />
        {/* viewBox 0 0 100 100 + preserveAspectRatio="none" makes the diamond fill any size */}
        <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none"
             style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}>
          <polygon points="50,1 99,50 50,99 1,50" fill={bg}
            stroke={selected && !readOnly ? "var(--fc-select)" : borderColor(d, "var(--fc-diamond-border, #666)")}
            strokeWidth={selected && !readOnly ? 2.5 : 1.5}
            vectorEffect="non-scaling-stroke" />
        </svg>
        <div className="fc-diamond-texture" />
        {/* Text lives in the rectangle inscribed in the diamond (60% x 40%);
            the font shrinks until the label fits, so long / translated text stays inside. */}
        <DiamondLabel text={d.label} color={textColor} />
        <LegendButton data={d} />
        <BoardButton data={d} />
      </div>
    </>
  );
}

// ── DoubleNode (parallel) ─────────────────────────────────────────────────────
export function DoubleNode({ data, selected }: NodeProps) {
  const readOnly = useContext(ReadOnlyContext);
  const d = data as unknown as NodeData;
  const bg = "var(--fc-double-bg, #722ed1)";
  const textColor = "var(--fc-double-text, #fff)";
  const hStyle = readOnly ? { visibility: "hidden" as const } : undefined;

  return (
    <>
      {selected && !readOnly && <NodeResizer minWidth={100} minHeight={36} />}
      <div data-fc-node="double" style={{ position: "relative", backgroundColor: bg, color: textColor, border: selected && !readOnly ? "3px solid var(--fc-select)" : `3px double ${borderColor(d, "var(--fc-double-border, #fff)")}`, boxShadow: "var(--fc-node-shadow, none)", borderRadius: 6, fontSize: 12, textAlign: "center", userSelect: "none", width: "100%", height: "100%", boxSizing: "border-box", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Handle type="source" position={Position.Left}   id="left"   style={hStyle} />
        <Handle type="source" position={Position.Top}    id="top"    style={hStyle} />
        <Handle type="source" position={Position.Right}  id="right"  style={hStyle} />
        <Handle type="source" position={Position.Bottom} id="bottom" style={hStyle} />
        <span style={{ position: "relative", zIndex: 1, padding: "8px 12px", whiteSpace: "pre-wrap" }}>{d.label}</span>
        <LegendButton data={d} />
        <BoardButton data={d} />
      </div>
    </>
  );
}

// ── PhaseNode ─────────────────────────────────────────────────────────────────
export function PhaseNode({ data, selected }: NodeProps) {
  const readOnly = useContext(ReadOnlyContext);
  const d = data as unknown as NodeData;
  const hStyle = readOnly ? { visibility: "hidden" as const } : undefined;
  return (
    <>
      {selected && !readOnly && <NodeResizer minWidth={80} minHeight={30} />}
      <div data-fc-node="phase" style={{ position: "relative", backgroundColor: "var(--fc-phase-bg, #ffc53d)", color: "var(--fc-phase-text, #3d2600)", border: selected && !readOnly ? "2px solid var(--fc-select)" : `2px solid ${borderColor(d, "var(--fc-phase-border, #d48806)")}`, boxShadow: "var(--fc-node-shadow, none)", borderRadius: "0 16px 0 16px", fontSize: 12, textAlign: "center", userSelect: "none", width: "100%", height: "100%", boxSizing: "border-box", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Handle type="source" position={Position.Left}   id="left"   style={hStyle} />
        <Handle type="source" position={Position.Top}    id="top"    style={hStyle} />
        <Handle type="source" position={Position.Right}  id="right"  style={hStyle} />
        <Handle type="source" position={Position.Bottom} id="bottom" style={hStyle} />
        <span style={{ position: "relative", zIndex: 1, padding: "6px 14px", whiteSpace: "pre-wrap" }}>{d.label}</span>
        <LegendButton data={d} />
        <BoardButton data={d} />
      </div>
    </>
  );
}

// ── ActionNode — resizable, all-sides handles ─────────────────────────────────
export function ActionNode({ data, selected }: NodeProps) {
  const readOnly = useContext(ReadOnlyContext);
  const d = data as unknown as NodeData;
  const theme = phaseActionTheme(d);
  const bg = theme?.bg ?? "var(--fc-action-bg, #ffffff)";
  const textColor = theme?.text ?? "var(--fc-action-text, #333)";
  const hStyle = readOnly ? { visibility: "hidden" as const } : undefined;

  return (
    <>
      {selected && !readOnly && <NodeResizer minWidth={100} minHeight={36} />}
      {/* position:relative makes this div the positioned ancestor for the handles */}
      <div
        data-fc-node="action"
        style={{
          position: "relative",
          backgroundColor: bg, color: textColor,
          border: selected && !readOnly
            ? "2px solid var(--fc-select)"
            : `1.5px solid ${theme?.border ?? borderColor(d, "var(--fc-action-border, var(--fc-node-border, #bbb))")}`,
          boxShadow: "var(--fc-node-shadow, none)",
          borderRadius: 6,
          textAlign: "center", fontSize: 12, userSelect: "none",
          width: "100%", height: "100%", boxSizing: "border-box",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}
      >
        <Handle type="source" position={Position.Left}   id="left"   style={hStyle} />
        <Handle type="source" position={Position.Top}    id="top"    style={hStyle} />
        <Handle type="source" position={Position.Right}  id="right"  style={hStyle} />
        <Handle type="source" position={Position.Bottom} id="bottom" style={hStyle} />
        <span style={{ position: "relative", zIndex: 1, padding: "8px 12px", whiteSpace: "pre-wrap" }}>{d.label}</span>
        <LegendButton data={d} />
        <BoardButton data={d} />
      </div>
    </>
  );
}

// ── LegendNode ────────────────────────────────────────────────────────────────
export function LegendNode({ data, selected }: NodeProps) {
  const readOnly = useContext(ReadOnlyContext);
  const d = data as any;
  const lines: string[] = (d.content ?? "").split("\n").filter(Boolean);
  return (
    <>
      {selected && !readOnly && <NodeResizer minWidth={120} minHeight={60} />}
      <div data-fc-node="legend" style={{
        width: "100%", height: "100%", boxSizing: "border-box",
        backgroundColor: "var(--fc-legend-bg, #f0f0f0)",
        border: selected && !readOnly
          ? "2px solid var(--fc-select)"
          : `1.5px dashed ${borderColor(d, "var(--fc-node-border, #bbb)")}`,
        borderRadius: 6, padding: "6px 10px", fontSize: 11, userSelect: "none",
      }}>
        {d.title && (
          <div style={{ fontWeight: 700, marginBottom: 3, color: "var(--fc-legend-title, #444)", whiteSpace: "pre-wrap" }}>
            {d.title}
          </div>
        )}
        {lines.map((l, i) => (
          <div key={i} style={{ color: "var(--fc-legend-content, #666)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{l}</div>
        ))}
      </div>
    </>
  );
}

// ── TextNode (decorative label / heading) ─────────────────────────────────────
export function TextNode({ data, selected }: NodeProps) {
  const readOnly = useContext(ReadOnlyContext);
  const d = data as any;
  const fontSize = d.fontSize ?? 22;
  const color = "var(--fc-text-color, #333)";
  const fontWeight = d.bold ? 700 : 600;
  const textAlign = (d.align ?? "center") as React.CSSProperties["textAlign"];
  const justify = textAlign === "right" ? "flex-end" : textAlign === "left" ? "flex-start" : "center";

  return (
    <>
      {selected && !readOnly && <NodeResizer minWidth={80} minHeight={24} />}
      <div style={{
        width: "100%", height: "100%", boxSizing: "border-box",
        display: "flex", alignItems: "center", justifyContent: justify,
        border: selected && !readOnly ? "1px dashed var(--fc-select)" : "1px solid transparent",
        padding: "2px 8px", background: "transparent", userSelect: "none",
      }}>
        <span style={{ fontSize, color, fontWeight, textAlign, lineHeight: 1.3, whiteSpace: "pre-wrap" }}>
          {d.label ?? "Text"}
        </span>
      </div>
    </>
  );
}

// ── ImageNode (game thumbnail / logo / any image) ─────────────────────────────
export function ImageNode({ data, selected }: NodeProps) {
  const readOnly = useContext(ReadOnlyContext);
  const d = data as any;
  const src = d.imageUrl ?? "";
  const caption = d.label ?? "";

  return (
    <>
      {selected && !readOnly && <NodeResizer minWidth={40} minHeight={40} />}
      <div style={{
        width: "100%", height: "100%", boxSizing: "border-box",
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        border: selected && !readOnly
          ? "2px solid var(--fc-select)"
          : `2px solid ${borderColor(d, "transparent")}`,
        borderRadius: 6, padding: 4, background: "transparent", userSelect: "none", overflow: "hidden",
      }}>
        {src
          ? <img src={src} alt={caption || "image"} style={{ flex: 1, width: "100%", objectFit: d.imgFit ?? "contain", minHeight: 0 }} />
          : <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--fc-legend-content, #999)", fontSize: 11, border: "1.5px dashed var(--fc-placeholder)", borderRadius: 4, width: "100%" }}>No URL</div>
        }
        {caption && <span style={{ fontSize: 10, color: "var(--fc-legend-content, #666)", marginTop: 3, textAlign: "center", flexShrink: 0 }}>{caption}</span>}
      </div>
    </>
  );
}

// ── PageNode (A4 / A5 print frame — fixed size, no resizer) ──────────────────
// A page frame is huge and sits under everything, but React Flow gives every
// node wrapper `pointer-events: all` across its whole box — so the frame used to
// swallow every click aimed at the edges beneath it (node z-order doesn't help:
// edges live in their own SVG layer below ALL nodes). editor.css turns pointer
// events off for `.react-flow__node-page`; the border strips and the corner
// label below opt back in, so the frame is still selectable and draggable by its
// edge while its interior stays click-through.
const PAGE_HIT = 12;

export function PageNode({ data, selected }: NodeProps) {
  const d = data as any;
  const grab: React.CSSProperties = { position: "absolute", pointerEvents: "auto", cursor: "move" };
  return (
    <div style={{
      width: "100%", height: "100%", boxSizing: "border-box",
      border: selected ? "2px dashed var(--fc-select, #1677ff)" : "1.5px dashed var(--fc-handle-bg, #95A4B7)",
      borderRadius: 3,
      background: "rgba(255,255,255,0.02)",
      position: "relative",
      pointerEvents: "none",
    }}>
      <div style={{ ...grab, top: -PAGE_HIT / 2, left: 0, right: 0, height: PAGE_HIT }} />
      <div style={{ ...grab, bottom: -PAGE_HIT / 2, left: 0, right: 0, height: PAGE_HIT }} />
      <div style={{ ...grab, left: -PAGE_HIT / 2, top: 0, bottom: 0, width: PAGE_HIT }} />
      <div style={{ ...grab, right: -PAGE_HIT / 2, top: 0, bottom: 0, width: PAGE_HIT }} />
      <div style={{
        ...grab, bottom: 5, right: 8,
        fontSize: 9, color: "var(--fc-handle-bg, #95A4B7)", fontStyle: "italic", userSelect: "none",
      }}>
        {d.label ?? "Page"}
      </div>
    </div>
  );
}

export const nodeTypes = {
  oval:    OvalNode,
  diamond: DiamondNode,
  double:  DoubleNode,
  phase:   PhaseNode,
  action:  ActionNode,
  legend:  LegendNode,
  page:    PageNode,
  text:    TextNode,
  image:   ImageNode,
};
