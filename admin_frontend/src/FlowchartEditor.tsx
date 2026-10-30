import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  ConnectionMode,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  ReactFlowProvider,
  Panel,
  type Connection,
  type Node,
  type Edge,
  type EdgeChange,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import { applyDagreLayout } from "./layout";
import { nodeTypes, phaseActionTheme } from "./nodes";
import { EDGE_TYPES, edgeShape, edgeTypeFor, isFloatingEdgeType } from "./edges";
import {
  DEFAULT_EDGE_STYLE,
  DEFAULT_MARKER,
  MARKER_SIZE,
  getLabelAutoColor,
  prepareGraph,
} from "./graph";
import { ReadOnlyContext } from "./ReadOnlyContext";
import { BoardContext } from "./board/BoardContext";
import BoardEditor from "./board/BoardEditor";
import BoardModal from "./board/BoardModal";
import { asBoard, type Board } from "./board/types";

interface Config {
  id?: string;
  reactFlowData: { nodes: Node[]; edges: Edge[] } | null;
  adjustedJson: { nodes: Node[]; edges: Edge[] } | null;
  adjustUrl: string;
  csrfToken: string;
  detail: string;
  rulebookTitle: string;
  isAdjusted: boolean;
  readOnly?: boolean;
  gameName?: string | null;
  thumbnailUrl?: string | null;
  logoUrl?: string | null;
}

type Status = "idle" | "saving" | "saved" | "error";

const EDGE_STYLE_OPTS = [
  { id: "default",    label: "Bezier" },
  { id: "smoothstep", label: "Smooth" },
  { id: "straight",   label: "Straight" },
  { id: "step",       label: "Step" },
];

const ARROW_TYPES = [
  { id: "arrowclosed", label: "▶ Filled" },
  { id: "arrow",       label: "→ Open" },
  { id: "",            label: "— None" },
];

const ADD_NODE_OPTIONS = [
  { rfType: "action",  kind: "action",   label: "Action",   icon: "▭" },
  { rfType: "diamond", kind: "decision", label: "Decision", icon: "◇" },
  { rfType: "oval",    kind: "start",    label: "Start",    icon: "⬭" },
  { rfType: "oval",    kind: "end",      label: "End",      icon: "⬭" },
  { rfType: "double",  kind: "parallel", label: "Parallel", icon: "⧈" },
  { rfType: "phase",   kind: "phase",    label: "Phase",    icon: "⬡" },
];

// A3 / A4 / A5 at 72 DPI (PDF points) — 1 canvas px ≈ 1 print pt
const PAGE_FRAME_OPTIONS = [
  { label: "A3 Portrait",  short: "A3↕", w: 842, h: 1191 },
  { label: "A3 Landscape", short: "A3↔", w: 1191, h: 842 },
  { label: "A4 Portrait",  short: "A4↕", w: 595, h: 842 },
  { label: "A4 Landscape", short: "A4↔", w: 842, h: 595 },
  { label: "A5 Portrait",  short: "A5↕", w: 420, h: 595 },
  { label: "A5 Landscape", short: "A5↔", w: 595, h: 420 },
];

const NODE_TYPE_ICONS: Record<string, string> = {
  action: "▭", oval: "⬭", diamond: "◇", double: "⧈",
  phase: "⬡", legend: "☰", page: "📄",
  text: "T", image: "🖼",
};

function Editor({ config }: { config: Config }) {
  const isReadOnly = config.readOnly ?? false;
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<string[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [statusMsg, setStatusMsg] = useState("");
  const [isAdjusted, setIsAdjusted] = useState(config.isAdjusted);
  const [showLayers, setShowLayers] = useState(false);
  const [viewReady, setViewReady] = useState(false);
  // Node whose board popup is open (editor or read-only, depending on mode)
  const [boardNodeId, setBoardNodeId] = useState<string | null>(null);
  const boardCtx = useMemo(() => ({ openBoard: setBoardNodeId }), []);
  const { fitView, screenToFlowPosition } = useReactFlow();
  const initialised = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const historyRef = useRef<Array<{ nodes: Node[]; edges: Edge[] }>>([]);
  const nodesRef = useRef<Node[]>([]);
  const edgesRef = useRef<Edge[]>([]);
  const pendingHistorySaveRef = useRef(false);
  const [canUndo, setCanUndo] = useState(false);
  // 自上次存檔後有沒有改過（所有編輯都會經過 saveHistory）。送審／Django Save 前
  // 的自動存檔只在有改動時才送出，避免沒動過的自動排版圖被存成 adjusted。
  const dirtyRef = useRef(false);
  const saveRef = useRef<() => Promise<boolean>>(async () => true);

  // Re-fit when the container becomes visible after being hidden (e.g., tab reveal).
  // ResizeObserver fires when dimensions change; we act on the 0→non-zero transition.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    let hadSize = false;
    const ro = new ResizeObserver(() => {
      const hasSize = el.offsetWidth > 0 && el.offsetHeight > 0;
      if (hasSize && !hadSize) {
        setTimeout(() => { fitView({ padding: 0.12 }); setViewReady(true); }, 0);
      }
      hadSize = hasSize;
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [fitView]);

  useEffect(() => {
    if (initialised.current) return;
    initialised.current = true;

    const source = config.adjustedJson ?? config.reactFlowData;
    if (!source) return;

    const { nodes: initNodes, edges: initEdges } = prepareGraph(source);

    setNodes(initNodes);
    setEdges(initEdges);
    setTimeout(() => { fitView({ padding: 0.12 }); setViewReady(true); }, 80);
  }, []);

  // Keep refs current synchronously on every render (not via useEffect, which lags one paint)
  nodesRef.current = nodes;
  edgesRef.current = edges;

  // ── Undo history ─────────────────────────────────────────────────────────────
  function saveHistory() {
    dirtyRef.current = true;
    historyRef.current = [
      ...historyRef.current.slice(-49),
      {
        nodes: nodesRef.current.map((n) => ({ ...n, data: { ...(n.data as object) } })),
        edges: [...edgesRef.current],
      },
    ];
    setCanUndo(true);
  }

  function maybeSaveHistory() {
    if (!pendingHistorySaveRef.current) {
      saveHistory();
      pendingHistorySaveRef.current = true;
    }
  }

  const undo = useCallback(() => {
    const stack = historyRef.current;
    if (!stack.length) return;
    const prev = stack[stack.length - 1];
    historyRef.current = stack.slice(0, -1);
    setNodes(prev.nodes as Node[]);
    setEdges(prev.edges as Edge[]);
    setSelectedNodeId(null);
    setSelectedEdgeIds([]);
    setCanUndo(stack.length > 1);
  }, [setNodes, setEdges]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === "z") {
        e.preventDefault();
        undo();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [undo]);

  // Reset pending flag when selection changes so next edit in new context saves
  useEffect(() => { pendingHistorySaveRef.current = false; }, [selectedNodeId, selectedEdgeIds]);

  const onConnect = useCallback(
    (params: Connection) => {
      saveHistory();
      setEdges((eds) =>
        addEdge(
          { ...params, type: "floatbezier", animated: false, markerEnd: DEFAULT_MARKER, style: DEFAULT_EDGE_STYLE },
          eds
        )
      );
    },
    []
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      onEdgesChange(changes);
      setSelectedEdgeIds((prev) => {
        let next = [...prev];
        changes.forEach((c) => {
          if (c.type === "select") {
            if (c.selected) next = [...new Set([...next, c.id])];
            else next = next.filter((id) => id !== c.id);
          }
        });
        return next;
      });
    },
    [onEdgesChange]
  );

  const handleSelectionChange = useCallback(({ nodes: selNodes }: OnSelectionChangeParams) => {
    setSelectedNodeId(selNodes.length === 1 ? selNodes[0].id : null);
  }, []);

  // ── edge toolbar helper (multi-select) ──────────────────────────────────────
  function applyEdgeProp(key: string, value: unknown) {
    saveHistory();
    setEdges((eds) =>
      eds.map((e) => {
        if (!selectedEdgeIds.includes(e.id)) return e;
        if (key === "markerEnd") {
          return { ...e, markerEnd: value ? { type: value as MarkerType, width: MARKER_SIZE, height: MARKER_SIZE } : undefined };
        }
        return { ...e, [key]: value };
      })
    );
  }

  /**
   * Switch the selected edges between fixed-handle and floating endpoints,
   * keeping each one's own path shape (bezier / smooth / straight / step).
   */
  function applyEdgeFloating(floating: boolean) {
    if (!selectedEdgeIds.length) return;
    saveHistory();
    setEdges((eds) =>
      eds.map((e) =>
        selectedEdgeIds.includes(e.id)
          ? { ...e, type: edgeTypeFor(edgeShape(e.type), floating) }
          : e
      )
    );
  }

  // ── single-edge panel update ─────────────────────────────────────────────────
  function updateEdge(patch: Partial<Edge>) {
    const id = selectedEdgeIds.length === 1 ? selectedEdgeIds[0] : null;
    if (!id) return;
    maybeSaveHistory();
    setEdges((eds) =>
      eds.map((e) => {
        if (e.id !== id) return e;
        let updated: Edge = { ...e, ...patch };

        // Auto-color yes/no when label changes (without explicit style in same patch)
        if ("label" in patch && !("style" in patch)) {
          const auto = getLabelAutoColor(patch.label);
          if (auto) {
            updated = {
              ...updated,
              style: { ...(updated.style ?? {}), stroke: auto },
              markerEnd: { ...DEFAULT_MARKER, color: auto },
            };
          }
        }

        // Animated edges turn orange; un-animating restores the label/default colour
        if ("animated" in patch) {
          const color = patch.animated
            ? "#fa8c16"
            : getLabelAutoColor(updated.label) ?? DEFAULT_EDGE_STYLE.stroke as string;
          updated = {
            ...updated,
            style: { ...(updated.style ?? {}), stroke: color },
            ...(updated.markerEnd ? { markerEnd: { ...DEFAULT_MARKER, ...(updated.markerEnd as object), color } } : {}),
          };
        }

        // Keep markerEnd.color in sync when stroke changes
        if ("style" in patch && (patch.style as any)?.stroke) {
          const stroke = (patch.style as any).stroke as string;
          if (updated.markerEnd && typeof updated.markerEnd === "object") {
            updated = { ...updated, markerEnd: { ...DEFAULT_MARKER, ...(updated.markerEnd as object), color: stroke } };
          }
        }

        return updated;
      })
    );
  }

  function deleteSelectedEdge() {
    const id = selectedEdgeIds.length === 1 ? selectedEdgeIds[0] : null;
    if (!id) return;
    saveHistory();
    setEdges((eds) => eds.filter((e) => e.id !== id));
    setSelectedEdgeIds([]);
  }

  // ── node helpers ─────────────────────────────────────────────────────────────
  const RESIZABLE_TYPES = ["action", "diamond", "double", "phase", "oval", "legend"];
  function resizableStyle(rfType: string) {
    return RESIZABLE_TYPES.includes(rfType) ? { width: 140, height: 50 } : undefined;
  }

  function addNode(rfType: string, kind: string, defaultLabel: string) {
    saveHistory();
    const id = `user_${Date.now()}`;
    const container = document.querySelector(".react-flow") as HTMLElement | null;
    const cx = (container?.clientWidth ?? 800) / 2;
    const cy = (container?.clientHeight ?? 600) / 2;
    const pos = screenToFlowPosition({ x: cx, y: cy });
    setNodes((nds) => [
      ...nds,
      {
        id, type: rfType,
        position: { x: pos.x - 70, y: pos.y - 25 },
        style: resizableStyle(rfType),
        data: { label: defaultLabel, kind, phase_id: null },
      },
    ]);
  }

  function addPageFrame(label: string, w: number, h: number) {
    saveHistory();
    const id = `page_${Date.now()}`;
    const container = document.querySelector(".react-flow") as HTMLElement | null;
    const cx = (container?.clientWidth ?? 800) / 2;
    const cy = (container?.clientHeight ?? 600) / 2;
    const pos = screenToFlowPosition({ x: cx, y: cy });
    // Prepend so page frames render behind other nodes
    setNodes((nds) => [
      {
        id, type: "page",
        position: { x: pos.x - w / 2, y: pos.y - h / 2 },
        style: { width: w, height: h },
        data: { label: "", kind: "page" },
      },
      ...nds,
    ]);
  }

  function addTextNode(text: string, fontSize = 24) {
    saveHistory();
    const id = `text_${Date.now()}`;
    const container = document.querySelector(".react-flow") as HTMLElement | null;
    const cx = (container?.clientWidth ?? 800) / 2;
    const cy = (container?.clientHeight ?? 600) / 2;
    const pos = screenToFlowPosition({ x: cx, y: cy });
    setNodes((nds) => [
      ...nds,
      { id, type: "text", position: { x: pos.x - 120, y: pos.y - 20 },
        style: { width: 240, height: 40 },
        data: { label: text, fontSize, kind: "text" } },
    ]);
  }

  function addImageNode(imageUrl: string, label: string, w = 120, h = 120) {
    saveHistory();
    const id = `img_${Date.now()}`;
    const container = document.querySelector(".react-flow") as HTMLElement | null;
    const cx = (container?.clientWidth ?? 800) / 2;
    const cy = (container?.clientHeight ?? 600) / 2;
    const pos = screenToFlowPosition({ x: cx, y: cy });
    setNodes((nds) => [
      ...nds,
      { id, type: "image", position: { x: pos.x - w / 2, y: pos.y - h / 2 },
        style: { width: w, height: h },
        data: { imageUrl, label, kind: "image" } },
    ]);
  }

  function addLegendNode() {
    saveHistory();
    const id = `legend_${Date.now()}`;
    const container = document.querySelector(".react-flow") as HTMLElement | null;
    const cx = (container?.clientWidth ?? 800) / 2;
    const cy = (container?.clientHeight ?? 600) / 2;
    const pos = screenToFlowPosition({ x: cx, y: cy });
    setNodes((nds) => [
      ...nds,
      { id, type: "legend",
        position: { x: pos.x - 80, y: pos.y - 40 },
        style: { width: 160, height: 80 },
        data: { title: "Legend", content: "", kind: "legend" } },
    ]);
  }

  function updateSelectedNodeData(patch: Record<string, unknown>) {
    if (!selectedNodeId) return;
    maybeSaveHistory();
    setNodes((nds) =>
      nds.map((n) => n.id === selectedNodeId ? { ...n, data: { ...n.data, ...patch } } : n)
    );
  }

  function setNodeBoard(nodeId: string, board: Board | null) {
    saveHistory();
    setNodes((nds) => nds.map((n) => {
      if (n.id !== nodeId) return n;
      const { board: _old, ...rest } = n.data as Record<string, unknown>;
      return { ...n, data: board ? { ...rest, board } : rest };
    }));
  }

  function deleteSelectedNode() {
    if (!selectedNodeId) return;
    saveHistory();
    setNodes((nds) => nds.filter((n) => n.id !== selectedNodeId));
    setEdges((eds) => eds.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId));
    setSelectedNodeId(null);
  }

  // ── layers panel helpers ──────────────────────────────────────────────────────
  function swapLayerNodes(i: number, j: number) {
    saveHistory();
    setNodes((nds) => {
      const arr = [...nds];
      [arr[i], arr[j]] = [arr[j], arr[i]];
      return arr;
    });
  }

  function selectNodeInCanvas(nodeId: string) {
    setNodes((nds) => nds.map((n) => ({ ...n, selected: n.id === nodeId })));
    setSelectedNodeId(nodeId);
  }

  // ── save / revert ─────────────────────────────────────────────────────────────
  async function save(): Promise<boolean> {
    setStatus("saving");
    try {
      // Capture React Flow's rendered geometry so other renderers (e.g. the
      // mobile app's SVG viewer) can draw identical paths instead of
      // re-deriving them. Coordinates are in flow space (same as node.position).
      const edgesToSave = edges.map((e) => {
        const pathEl = document.getElementById(e.id);
        const d = pathEl?.getAttribute("d") ?? null;
        let viewLabelX: number | undefined;
        let viewLabelY: number | undefined;
        const lblEl = document.querySelector(`[data-rf-label="${e.id}"]`) as SVGGElement | null;
        const m = lblEl?.transform.baseVal.consolidate()?.matrix;
        if (m) { viewLabelX = m.e; viewLabelY = m.f; }
        if (!d && viewLabelX == null) return e;
        return {
          ...e,
          data: {
            ...(e.data ?? {}),
            ...(d ? { d } : {}),
            ...(viewLabelX != null ? { viewLabelX, viewLabelY } : {}),
          },
        };
      });
      const res = await fetch(config.adjustUrl, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-CSRFToken": config.csrfToken },
        body: JSON.stringify({ detail: config.detail, adjusted_json: { nodes, edges: edgesToSave } }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { error?: string }).error ?? `HTTP ${res.status}`);
      }
      dirtyRef.current = false;
      setStatus("saved"); setIsAdjusted(true); setStatusMsg("Saved ✓");
      setTimeout(() => setStatus("idle"), 3000);
      return true;
    } catch (e: unknown) {
      setStatus("error");
      setStatusMsg(`Save failed: ${e instanceof Error ? e.message : String(e)}`);
      return false;
    }
  }

  // 每次 render 都指向最新的 save（它閉包了最新的 nodes/edges）
  saveRef.current = save;
  useEffect(() => {
    if (isReadOnly || config.id !== "editor") return;
    // 給 Django change form 用：送審或按 Save 前先呼叫。回傳 false 代表存檔失敗。
    window.flowchartEditorAutosave = async () => (dirtyRef.current ? saveRef.current() : true);
    return () => { delete window.flowchartEditorAutosave; };
  }, [isReadOnly, config.id]);

  async function revert() {
    if (!confirm("Revert to auto-generated layout? Manual adjustments will be lost.")) return;
    setStatus("saving");
    try {
      const res = await fetch(config.adjustUrl, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-CSRFToken": config.csrfToken },
        body: JSON.stringify({ detail: config.detail, adjusted_json: null }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const relaid = applyDagreLayout(nodes, edges);
      setNodes(relaid);
      dirtyRef.current = false;
      setIsAdjusted(false);
      setStatus("saved"); setStatusMsg("Reverted ✓");
      setTimeout(() => { setStatus("idle"); fitView({ padding: 0.12 }); }, 300);
    } catch (e: unknown) {
      setStatus("error");
      setStatusMsg(`Revert failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  // ── derived state ─────────────────────────────────────────────────────────────
  const isBusy = status === "saving";
  const hasSelectedEdges = selectedEdgeIds.length > 0;
  const selectedNode = selectedNodeId ? nodes.find((n) => n.id === selectedNodeId) ?? null : null;
  const selectedData = selectedNode?.data as Record<string, unknown> | undefined;
  const allSelectedEdgesFloating =
    selectedEdgeIds.length > 0 &&
    edges.every((e) => !selectedEdgeIds.includes(e.id) || isFloatingEdgeType(e.type));
  const selectedEdgeId = selectedEdgeIds.length === 1 ? selectedEdgeIds[0] : null;
  const selectedEdge = selectedEdgeId ? edges.find((e) => e.id === selectedEdgeId) ?? null : null;
  const boardNode = boardNodeId ? nodes.find((n) => n.id === boardNodeId) ?? null : null;
  const boardOfNode = asBoard((boardNode?.data as Record<string, unknown> | undefined)?.board);

  // ── phases ───────────────────────────────────────────────────────────────────
  // Phases are not drawn on the canvas any more; they live on each node as
  // phase_id / phase_label / phase_order and only surface in the text version of
  // the flowchart (and the HowTo structured data built from it). The name is
  // shared by every node of the phase, so editing it rewrites all of them.
  // Phases are fixed: Preparation / Game Flow / Endgame (ids match the LLM
  // generator in game/rag/flowchart/prompts.py). phase_order is what the
  // renderer keys on, so legacy charts with drifted phase_ids still match.
  const PHASES = [
    { id: "setup",    label: "Preparation", order: 1 },
    { id: "sequence", label: "Game Flow",   order: 2 },
    { id: "endgame",  label: "Endgame",     order: 3 },
  ] as const;

  function assignPhase(order: string) {
    const phase = PHASES.find((p) => String(p.order) === order);
    updateSelectedNodeData(
      phase
        ? { phase_id: phase.id, phase_label: phase.label, phase_order: phase.order }
        : { phase_id: null, phase_label: null, phase_order: null }
    );
  }

  const btn = (disabled = false, extra?: React.CSSProperties): React.CSSProperties => ({
    padding: "4px 9px", fontSize: 12, borderRadius: 4,
    border: "1px solid var(--fc-node-border, #ccc)", cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.6 : 1, background: disabled ? "var(--color-bg-alt, #f5f5f5)" : "var(--color-bg-popup, #fff)",
    ...extra,
  });

  const smBtn = (disabled = false, extra?: React.CSSProperties): React.CSSProperties => ({
    padding: "1px 5px", fontSize: 11, borderRadius: 3,
    border: "1px solid var(--fc-node-border, #ddd)", cursor: disabled ? "default" : "pointer",
    opacity: disabled ? 0.35 : 1, background: "var(--color-bg-popup, #fff)", lineHeight: "16px",
    ...extra,
  });

  return (
    <ReadOnlyContext.Provider value={isReadOnly}>
    <BoardContext.Provider value={boardCtx}>
      <div ref={containerRef} style={{ height: "100%", display: "flex", flexDirection: "column", color: "var(--fc-editor-text, #333)", background: "var(--fc-editor-bg, #fff)" }}>

        {/* ── Toolbar (edit mode only) ────────────────────────────── */}
        {!isReadOnly && <div style={{
          padding: "5px 10px", background: "var(--color-bg-alt, #f8f9fa)", borderBottom: "1px solid var(--fc-node-border, #ddd)",
          display: "flex", alignItems: "center", flexWrap: "wrap", gap: 5, flexShrink: 0,
        }}>
          <span style={{ fontSize: 12, color: "var(--color-text-main, #555)", marginRight: 2 }}>
            <strong>{config.detail}</strong>
            {isAdjusted && <span style={{ color: "var(--color-primary, #1677ff)" }}> [adjusted]</span>}
            {isReadOnly && <span style={{ color: "var(--color-text-disabled, #aaa)", fontStyle: "italic" }}> · read-only</span>}
          </span>

          {!isReadOnly && (
            <>
              <button style={btn(isBusy)} onClick={save} disabled={isBusy}>💾 Save</button>
              {isAdjusted && <button style={btn(isBusy)} onClick={revert} disabled={isBusy}>↩ Revert</button>}
              <button style={btn(!canUndo)} onClick={undo} disabled={!canUndo} title="Undo (Ctrl+Z)">↺ Undo</button>

              <div style={{ width: 1, height: 18, background: "var(--fc-node-border, #ddd)", margin: "0 3px" }} />

              <span style={{ fontSize: 11, color: "var(--color-text-minor, #888)" }}>Add:</span>
              {ADD_NODE_OPTIONS.map((opt) => (
                <button key={opt.kind} style={btn()} title={`Add ${opt.label} node`}
                  onClick={() => addNode(opt.rfType, opt.kind, opt.label)}>
                  {opt.icon} {opt.label}
                </button>
              ))}
              <button style={btn()} title="Add Legend node" onClick={addLegendNode}>
                ☰ Legend
              </button>

              <div style={{ width: 1, height: 18, background: "var(--fc-node-border, #ddd)", margin: "0 3px" }} />
              <span style={{ fontSize: 11, color: "var(--color-text-minor, #888)" }}>Page:</span>
              {PAGE_FRAME_OPTIONS.map((pf) => (
                <button key={pf.label} style={btn()} title={`${pf.label} (${pf.w}×${pf.h} pt)`}
                  onClick={() => addPageFrame(pf.label, pf.w, pf.h)}>
                  {pf.short}
                </button>
              ))}

              {/* Insert game assets */}
              {(config.gameName || config.thumbnailUrl || config.logoUrl) && (
                <>
                  <div style={{ width: 1, height: 18, background: "var(--fc-node-border, #ddd)", margin: "0 3px" }} />
                  <span style={{ fontSize: 11, color: "var(--color-text-minor, #888)" }}>Insert:</span>
                  {config.gameName && (
                    <button style={btn()} title={config.gameName}
                      onClick={() => addTextNode(config.gameName!, 24)}>
                      📝 Edition name
                    </button>
                  )}
                  {config.thumbnailUrl && (
                    <button style={btn()}
                      onClick={() => addImageNode(config.thumbnailUrl!, "", 120, 120)}>
                      🖼 Cover
                    </button>
                  )}
                  {config.logoUrl && (
                    <button style={btn()}
                      onClick={() => addImageNode(config.logoUrl!, "", 80, 80)}>
                      🔷 Logo
                    </button>
                  )}
                </>
              )}

              {hasSelectedEdges && (
                <>
                  <div style={{ width: 1, height: 18, background: "var(--fc-node-border, #ddd)", margin: "0 3px" }} />
                  <span style={{ fontSize: 11, color: "var(--color-text-minor, #888)" }}>Edge:</span>
                  {EDGE_STYLE_OPTS.map((et) => (
                    <button key={et.id} style={btn()}
                      onClick={() => applyEdgeProp("type", edgeTypeFor(et.id, allSelectedEdgesFloating))}>
                      {et.label}
                    </button>
                  ))}
                  <span style={{ fontSize: 11, color: "var(--color-text-minor, #888)", marginLeft: 2 }}>Ends:</span>
                  <button style={btn(false, !allSelectedEdgesFloating ? { background: "var(--color-bg-hover, #e6f4ff)", borderColor: "var(--color-primary, #1677ff)" } : {})}
                    title="Endpoints stay pinned to the handle they were drawn from"
                    onClick={() => applyEdgeFloating(false)}>
                    ⚓ Fixed
                  </button>
                  <button style={btn(false, allSelectedEdgesFloating ? { background: "var(--color-bg-hover, #e6f4ff)", borderColor: "var(--color-primary, #1677ff)" } : {})}
                    title="Endpoints follow the nodes and re-attach to the nearest side"
                    onClick={() => applyEdgeFloating(true)}>
                    🧲 Floating
                  </button>
                  <span style={{ fontSize: 11, color: "var(--color-text-minor, #888)", marginLeft: 2 }}>Arrow:</span>
                  {ARROW_TYPES.map((at) => (
                    <button key={at.id} style={btn()} onClick={() => applyEdgeProp("markerEnd", at.id)}>
                      {at.label}
                    </button>
                  ))}
                  <button style={btn(false, { color: "var(--fc-edge-no, #ff4d4f)" })}
                    onClick={() => { setEdges((eds) => eds.filter((e) => !selectedEdgeIds.includes(e.id))); setSelectedEdgeIds([]); }}>
                    🗑 Delete edge
                  </button>
                </>
              )}

              {status !== "idle" && (
                <span style={{ fontSize: 11, color: status === "error" ? "var(--fc-edge-no, #ff4d4f)" : status === "saved" ? "var(--fc-edge-yes, #52c41a)" : "var(--color-text-minor, #888)", marginLeft: 4 }}>
                  {isBusy ? "Saving…" : statusMsg}
                </span>
              )}
            </>
          )}
        </div>}

        {/* Help hint */}
        {!isReadOnly && (
          <div style={{ fontSize: 10, color: "var(--color-text-disabled, #aaa)", padding: "2px 10px", background: "var(--color-bg-alt, #fafafa)", borderBottom: "1px solid var(--fc-node-border, #eee)", flexShrink: 0 }}>
            Click to select · Edit in right panel · Drag to move (15 px snap) · Drag between handles to connect
          </div>
        )}

        {/* ── Canvas + Side Panel ──────────────────────────────────── */}
        <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

          {/* Canvas */}
          <div style={{ flex: 1, opacity: viewReady ? 1 : 0 }}>
            <ReactFlow
              id={config.id}
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={handleEdgesChange}
              onConnect={onConnect}
              onSelectionChange={handleSelectionChange}
              nodeTypes={nodeTypes}
              edgeTypes={EDGE_TYPES}
              fitView
              nodesDraggable={!isReadOnly}
              nodesConnectable={!isReadOnly}
              elementsSelectable={!isReadOnly}
              connectionMode={ConnectionMode.Loose}
              connectionRadius={30}
              snapToGrid={!isReadOnly}
              snapGrid={[5, 5]}
              onNodeDragStart={() => saveHistory()}
              defaultEdgeOptions={{
                type: "floatbezier",
                markerEnd: DEFAULT_MARKER,
                style: DEFAULT_EDGE_STYLE,
              }}
              attributionPosition="bottom-right"
            >
              {/* 格線只在編輯模式畫：拖曳節點時當對齊參考。唯讀檢視（含公開頁、
                  由公開頁複製 DOM 出去的列印視窗）不需要，滿版小點在紙上很花油墨。 */}
              {!isReadOnly && <Background gap={15} />}
              <Controls showInteractive={!isReadOnly} />
              <MiniMap nodeStrokeWidth={3} zoomable pannable style={{ width: 100, height: 75 }} />
              {!isReadOnly && (
                <Panel position="top-right" style={{ fontSize: 10, color: "var(--color-text-disabled, #aaa)", background: "rgba(255,255,255,.7)", padding: "2px 6px", borderRadius: 4 }}>
                  {nodes.length}n · {edges.length}e
                </Panel>
              )}
            </ReactFlow>
          </div>

          {/* ── Right Panel (always shown in edit mode) ───────────── */}
          {!isReadOnly && (
            <div style={{
              width: 236, flexShrink: 0, borderLeft: "1px solid var(--fc-node-border, #ddd)",
              background: "var(--color-bg-alt, #fafafa)", overflowY: "auto",
              display: "flex", flexDirection: "column",
              fontSize: 12, color: "var(--color-text-main, #333)",
            }}>

              {/* ── PROPERTIES section ───────────────────────────── */}
              <div style={{ padding: "10px 12px", display: "flex", flexDirection: "column", gap: 10, borderBottom: "1px solid var(--fc-node-border, #eee)" }}>

                {/* NODE PANEL */}
                {selectedNode && (() => {
                  const ntype = selectedNode.type;
                  const isLegend = ntype === "legend";
                  const isText   = ntype === "text";
                  const isImage  = ntype === "image";
                  const isPage   = ntype === "page";
                  // Action nodes inside a phase get fixed colours (see nodes/index.tsx)
                  const phaseColors = ntype === "action" ? phaseActionTheme(selectedData) : null;

                  return (
                    <>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>
                        Node
                        <span style={{ float: "right", background: "var(--color-bg-hover, #e6f4ff)", color: "var(--color-primary, #1677ff)", borderRadius: 3, padding: "1px 6px", fontSize: 11, fontWeight: 400 }}>
                          {String(selectedData?.kind ?? ntype ?? "")}
                        </span>
                      </div>

                      {/* ── Legend: title + content ── */}
                      {isLegend && (
                        <>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Title</label>
                            <input type="text"
                              value={String(selectedData?.title ?? "")}
                              onChange={(e) => updateSelectedNodeData({ title: e.target.value })}
                              style={{ width: "100%", boxSizing: "border-box", fontSize: 12, padding: "4px 6px", border: "1px solid var(--fc-node-border, #d9d9d9)", borderRadius: 4, background: "var(--color-bg-popup, #fff)", color: "var(--color-text-main, #333)" }}
                            />
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Content</label>
                            <textarea
                              value={String(selectedData?.content ?? "")}
                              rows={5}
                              onChange={(e) => updateSelectedNodeData({ content: e.target.value })}
                              style={{ width: "100%", boxSizing: "border-box", fontSize: 11, padding: "4px 6px", border: "1px solid var(--fc-node-border, #d9d9d9)", borderRadius: 4, resize: "vertical", fontFamily: "inherit", background: "var(--color-bg-popup, #fff)", color: "var(--color-text-main, #333)" }}
                              placeholder={"One line per item\nLine 2\nLine 3"}
                            />
                          </div>
                        </>
                      )}

                      {/* ── Bind legends: Tour shows a button on this node ── */}
                      {["oval", "diamond", "double", "phase", "action"].includes(String(ntype)) && (() => {
                        const legendNodes = nodes.filter((n) => n.type === "legend");
                        if (!legendNodes.length) return null;
                        const bound = Array.isArray(selectedData?.legend_ids)
                          ? (selectedData!.legend_ids as string[]) : [];
                        return (
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Legends (Tour button)</label>
                            {legendNodes.map((l) => {
                              const title = String((l.data as any)?.title ?? "").trim() || l.id;
                              return (
                                <label key={l.id} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, color: "var(--color-text-main, #333)", cursor: "pointer" }}>
                                  <input type="checkbox" checked={bound.includes(l.id)}
                                    onChange={(e) => updateSelectedNodeData({
                                      legend_ids: e.target.checked
                                        ? [...bound, l.id]
                                        : bound.filter((x) => x !== l.id),
                                    })} />
                                  {title}
                                </label>
                              );
                            })}
                          </div>
                        );
                      })()}

                      {/* ── Board: grid diagram opened from a button on this node ── */}
                      {["oval", "diamond", "double", "phase", "action"].includes(String(ntype)) && (() => {
                        const hasBoard = !!asBoard(selectedData?.board);
                        return (
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Board (button on node)</label>
                            <div style={{ display: "flex", gap: 4 }}>
                              <button style={btn()} onClick={() => setBoardNodeId(selectedNode.id)}>
                                {hasBoard ? "✎ Edit board" : "⊞ Add board"}
                              </button>
                              {hasBoard && (
                                <button style={btn(false, { color: "var(--fc-edge-no, #ff4d4f)" })}
                                  onClick={() => { if (confirm("Remove this board?")) setNodeBoard(selectedNode.id, null); }}>
                                  🗑
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })()}

                      {/* ── Image: URL + caption + fit ── */}
                      {isImage && (
                        <>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Image URL</label>
                            <input type="text"
                              value={String(selectedData?.imageUrl ?? "")}
                              onChange={(e) => updateSelectedNodeData({ imageUrl: e.target.value })}
                              style={{ width: "100%", boxSizing: "border-box", fontSize: 11, padding: "4px 6px", border: "1px solid var(--fc-node-border, #d9d9d9)", borderRadius: 4, background: "var(--color-bg-popup, #fff)", color: "var(--color-text-main, #333)" }}
                              placeholder="/media/...  or https://..."
                            />
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Caption</label>
                            <input type="text"
                              value={String(selectedData?.label ?? "")}
                              onChange={(e) => updateSelectedNodeData({ label: e.target.value })}
                              style={{ width: "100%", boxSizing: "border-box", fontSize: 12, padding: "4px 6px", border: "1px solid var(--fc-node-border, #d9d9d9)", borderRadius: 4, background: "var(--color-bg-popup, #fff)", color: "var(--color-text-main, #333)" }}
                            />
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Fit</label>
                            <div style={{ display: "flex", gap: 4 }}>
                              {(["contain", "cover", "fill"] as const).map((f) => (
                                <button key={f} style={btn(false, selectedData?.imgFit === f ? { background: "var(--color-bg-hover, #e6f4ff)", borderColor: "var(--color-primary, #1677ff)" } : {})}
                                  onClick={() => updateSelectedNodeData({ imgFit: f })}>
                                  {f}
                                </button>
                              ))}
                            </div>
                          </div>
                        </>
                      )}

                      {/* ── Text: label + font options ── */}
                      {isText && (
                        <>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Text</label>
                            <textarea
                              value={String(selectedData?.label ?? "")}
                              rows={2}
                              onChange={(e) => updateSelectedNodeData({ label: e.target.value })}
                              style={{ width: "100%", boxSizing: "border-box", fontSize: 12, padding: "4px 6px", border: "1px solid var(--fc-node-border, #d9d9d9)", borderRadius: 4, resize: "vertical", fontFamily: "inherit", background: "var(--color-bg-popup, #fff)", color: "var(--color-text-main, #333)" }}
                            />
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500, flexShrink: 0 }}>Size</label>
                            <input type="range" min={10} max={72} step={1}
                              value={Number(selectedData?.fontSize ?? 22)}
                              onChange={(e) => updateSelectedNodeData({ fontSize: Number(e.target.value) })}
                              style={{ flex: 1 }}
                            />
                            <span style={{ fontSize: 11, color: "var(--color-text-minor, #888)", width: 26, textAlign: "right" }}>
                              {Number(selectedData?.fontSize ?? 22)}
                            </span>
                          </div>
                          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--color-text-main, #555)", cursor: "pointer" }}>
                              <input type="checkbox" checked={!!selectedData?.bold}
                                onChange={(e) => updateSelectedNodeData({ bold: e.target.checked })} />
                              Bold
                            </label>
                            <div style={{ display: "flex", gap: 3 }}>
                              {(["left", "center", "right"] as const).map((a) => (
                                <button key={a} style={btn(false, selectedData?.align === a || (!selectedData?.align && a === "center") ? { background: "var(--color-bg-hover, #e6f4ff)", borderColor: "var(--color-primary, #1677ff)" } : {})}
                                  onClick={() => updateSelectedNodeData({ align: a })}>
                                  {a === "left" ? "⬅" : a === "center" ? "↔" : "➡"}
                                </button>
                              ))}
                            </div>
                          </div>
                        </>
                      )}

                      {/* ── Page: label only ── */}
                      {isPage && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Label</label>
                          <input type="text"
                            value={String(selectedData?.label ?? "")}
                            onChange={(e) => updateSelectedNodeData({ label: e.target.value })}
                            style={{ width: "100%", boxSizing: "border-box", fontSize: 12, padding: "4px 6px", border: "1px solid var(--fc-node-border, #d9d9d9)", borderRadius: 4, background: "var(--color-bg-popup, #fff)", color: "var(--color-text-main, #333)" }}
                          />
                        </div>
                      )}

                      {/* ── Standard nodes: label + bg + text color ── */}
                      {!isLegend && !isImage && !isText && !isPage && (
                        <>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Label</label>
                            <textarea
                              value={String(selectedData?.label ?? "")}
                              rows={3}
                              onChange={(e) => updateSelectedNodeData({ label: e.target.value })}
                              style={{ width: "100%", boxSizing: "border-box", fontSize: 12, padding: "4px 6px", border: "1px solid var(--fc-node-border, #d9d9d9)", borderRadius: 4, resize: "vertical", fontFamily: "inherit", background: "var(--color-bg-popup, #fff)", color: "var(--color-text-main, #333)" }}
                            />
                          </div>
                          {phaseColors && (
                            /* Action nodes in a phase are colour-locked so they read
                               the same in light and dark mode — no pickers to offer. */
                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                              <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Colours</label>
                              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span style={{
                                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                                  width: 58, height: 24, borderRadius: 4, fontSize: 10, fontWeight: 600,
                                  background: phaseColors.bg, color: phaseColors.text,
                                  border: `1.5px solid ${phaseColors.border}`,
                                }}>Action</span>
                                <span style={{ fontSize: 10, color: "var(--color-text-disabled, #aaa)", lineHeight: 1.4 }}>
                                  set by phase · follows theme
                                </span>
                              </div>
                            </div>
                          )}
                        </>
                      )}

                      {/* ── Phase — not drawn on the canvas; sections the text
                             version and the HowTo structured data built from it ── */}
                      {!isLegend && !isImage && !isText && !isPage && (() => {
                        const currentOrder = typeof selectedData?.phase_order === "number" ? String(selectedData.phase_order) : "";
                        return (
                          <div style={{ display: "flex", flexDirection: "column", gap: 4, borderTop: "1px dashed var(--fc-node-border, #e0e0e0)", paddingTop: 8 }}>
                            <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>
                              Phase
                              <span style={{ color: "var(--color-text-disabled, #aaa)", fontWeight: 400, marginLeft: 4 }}>(text version only)</span>
                            </label>
                            <select
                              value={currentOrder}
                              onChange={(e) => assignPhase(e.target.value)}
                              style={{ width: "100%", boxSizing: "border-box", fontSize: 12, padding: "3px 5px", border: "1px solid var(--fc-node-border, #d9d9d9)", borderRadius: 4, background: "var(--color-bg-popup, #fff)", color: "var(--color-text-main, #333)" }}
                            >
                              <option value="">— none —</option>
                              {PHASES.map((p) => (
                                <option key={p.id} value={String(p.order)}>{p.label}</option>
                              ))}
                            </select>
                          </div>
                        );
                      })()}

                      <button onClick={deleteSelectedNode}
                        style={btn(false, { color: "var(--fc-edge-no, #ff4d4f)", borderColor: "var(--fc-oval-end-border, #ffccc7)", background: "var(--fc-oval-end-bg, #fff1f0)" })}>
                        🗑 Delete node
                      </button>
                    </>
                  );
                })()}

                {/* EDGE PANEL */}
                {!selectedNode && selectedEdge && (
                  <>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>
                      Edge
                      <span style={{ float: "right", background: "var(--fc-phase-bg, #fff7e6)", color: "#fa8c16", borderRadius: 3, padding: "1px 6px", fontSize: 11, fontWeight: 400 }}>
                        {selectedEdge.type ?? "default"}
                      </span>
                    </div>

                    {/* Source → Target */}
                    {(() => {
                      const srcNode = nodes.find((n) => n.id === selectedEdge.source);
                      const tgtNode = nodes.find((n) => n.id === selectedEdge.target);
                      const srcLabel = String((srcNode?.data as any)?.label ?? selectedEdge.source);
                      const tgtLabel = String((tgtNode?.data as any)?.label ?? selectedEdge.target);
                      return (
                        <div style={{ fontSize: 11, color: "var(--color-text-minor, #666)", background: "var(--color-bg-alt, #f5f5f5)", borderRadius: 4, padding: "5px 8px", display: "flex", flexDirection: "column", gap: 3 }}>
                          <div><span style={{ color: "var(--color-text-disabled, #aaa)", marginRight: 4 }}>from</span><span style={{ color: "var(--color-text-main, #333)", fontWeight: 500 }}>{srcLabel}</span></div>
                          <div><span style={{ color: "var(--color-text-disabled, #aaa)", marginRight: 4 }}>to</span><span style={{ color: "var(--color-text-main, #333)", fontWeight: 500 }}>{tgtLabel}</span></div>
                        </div>
                      );
                    })()}

                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Label</label>
                      <input type="text"
                        value={String(selectedEdge.label ?? "")}
                        placeholder='"yes" / "no" → auto-color'
                        onChange={(e) => updateEdge({ label: e.target.value || undefined })}
                        style={{
                          width: "100%", boxSizing: "border-box",
                          fontSize: 12, padding: "4px 6px",
                          border: "1px solid var(--fc-node-border, #d9d9d9)", borderRadius: 4,
                          background: "var(--color-bg-popup, #fff)", color: "var(--color-text-main, #333)",
                        }}
                      />
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Line style</label>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {EDGE_STYLE_OPTS.map((et) => (
                          <button key={et.id}
                            style={btn(false, edgeShape(selectedEdge.type) === et.id ? { background: "var(--color-bg-hover, #e6f4ff)", borderColor: "var(--color-primary, #1677ff)" } : {})}
                            onClick={() => updateEdge({ type: edgeTypeFor(et.id, isFloatingEdgeType(selectedEdge.type)) })}>
                            {et.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Fixed = the endpoint stays on the handle the edge was drawn
                        from. Floating = both ends are recomputed from the node
                        positions, so the line re-attaches to whichever side faces
                        the other node when either node moves. */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Endpoints</label>
                      <div style={{ display: "flex", gap: 4 }}>
                        <button
                          style={btn(false, !isFloatingEdgeType(selectedEdge.type) ? { background: "var(--color-bg-hover, #e6f4ff)", borderColor: "var(--color-primary, #1677ff)" } : {})}
                          onClick={() => updateEdge({ type: edgeShape(selectedEdge.type) })}>
                          ⚓ Fixed
                        </button>
                        <button
                          style={btn(false, isFloatingEdgeType(selectedEdge.type) ? { background: "var(--color-bg-hover, #e6f4ff)", borderColor: "var(--color-primary, #1677ff)" } : {})}
                          onClick={() => updateEdge({ type: edgeTypeFor(edgeShape(selectedEdge.type), true) })}>
                          🧲 Floating
                        </button>
                      </div>
                      <div style={{ fontSize: 10, color: "var(--color-text-disabled, #aaa)", lineHeight: 1.4 }}>
                        {isFloatingEdgeType(selectedEdge.type)
                          ? "Both ends re-attach to the nearest side when a node moves."
                          : "Both ends stay pinned to their handle."}
                      </div>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <label style={{ fontSize: 11, color: "var(--color-text-minor, #666)", fontWeight: 500 }}>Arrow</label>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {ARROW_TYPES.map((at) => {
                          const curType = (selectedEdge.markerEnd as any)?.type ?? "";
                          const active = curType === at.id || (!selectedEdge.markerEnd && at.id === "");
                          return (
                            <button key={at.id}
                              style={btn(false, active ? { background: "var(--color-bg-hover, #e6f4ff)", borderColor: "var(--color-primary, #1677ff)" } : {})}
                              onClick={() => {
                                const stroke = (selectedEdge.style as any)?.stroke ?? "var(--color-text-main, #555)";
                                const me = at.id
                                  ? { type: at.id as MarkerType, width: MARKER_SIZE, height: MARKER_SIZE, color: stroke }
                                  : undefined;
                                updateEdge({ markerEnd: me });
                              }}>
                              {at.label}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--color-text-main, #555)", cursor: "pointer" }}>
                      <input type="checkbox" checked={!!selectedEdge.animated}
                        onChange={(e) => updateEdge({ animated: e.target.checked })} />
                      Animated (dashed)
                    </label>

                    <button onClick={deleteSelectedEdge}
                      style={btn(false, { color: "var(--fc-edge-no, #ff4d4f)", borderColor: "var(--fc-oval-end-border, #ffccc7)", background: "var(--fc-oval-end-bg, #fff1f0)" })}>
                      🗑 Delete edge
                    </button>
                  </>
                )}

                {/* Empty state */}
                {!selectedNode && !selectedEdge && (
                  <div style={{ color: "var(--color-text-disabled, #bbb)", fontSize: 11, textAlign: "center", padding: "8px 0" }}>
                    Select a node or edge to edit
                  </div>
                )}
              </div>

              {/* ── LAYERS section ───────────────────────────────── */}
              <div style={{ flexShrink: 0 }}>
                {/* Section header */}
                <button
                  onClick={() => setShowLayers((v) => !v)}
                  style={{
                    width: "100%", textAlign: "left",
                    padding: "7px 12px", fontSize: 12, fontWeight: 600,
                    background: "var(--color-bg-alt, #f0f0f0)", border: "none", borderBottom: "1px solid var(--fc-node-border, #ddd)",
                    cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center",
                  }}
                >
                  <span>Layers ({nodes.length})</span>
                  <span style={{ fontSize: 10, color: "var(--color-text-minor, #888)" }}>{showLayers ? "▲" : "▼"}</span>
                </button>

                {showLayers && (
                  <div style={{ padding: "4px 6px", display: "flex", flexDirection: "column", gap: 1 }}>
                    <div style={{ fontSize: 10, color: "var(--color-text-disabled, #aaa)", padding: "2px 4px 4px" }}>
                      Top = front · ↑↓ to reorder z-order
                    </div>
                    {/* Reversed: top of list = highest array index = frontmost */}
                    {[...nodes].reverse().map((n, revI) => {
                      const realIdx = nodes.length - 1 - revI;
                      const label = (n.data as any)?.label ?? n.id;
                      const icon = (n.data as any)?.board ? "⊞" : NODE_TYPE_ICONS[n.type ?? ""] ?? "●";
                      const isSelected = n.id === selectedNodeId;
                      return (
                        <div
                          key={n.id}
                          onClick={() => selectNodeInCanvas(n.id)}
                          style={{
                            display: "flex", alignItems: "center", gap: 3,
                            padding: "3px 4px", borderRadius: 3, cursor: "pointer",
                            background: isSelected ? "var(--color-bg-hover, #e6f4ff)" : "transparent",
                          }}
                        >
                          <span style={{ fontSize: 12, color: "var(--color-text-disabled, #aaa)", flexShrink: 0 }}>{icon}</span>
                          <span style={{
                            flex: 1, fontSize: 11, overflow: "hidden",
                            textOverflow: "ellipsis", whiteSpace: "nowrap",
                            color: isSelected ? "var(--color-primary, #1677ff)" : "var(--color-text-main, #333)",
                          }}>
                            {String(label)}
                          </span>
                          <span style={{ fontSize: 9, color: "var(--fc-node-border, #ccc)", flexShrink: 0, marginRight: 2 }}>
                            {n.type}
                          </span>
                          <button
                            onClick={(e) => { e.stopPropagation(); swapLayerNodes(realIdx, realIdx + 1); }}
                            disabled={realIdx === nodes.length - 1}
                            style={smBtn(realIdx === nodes.length - 1)}
                            title="Move forward"
                          >↑</button>
                          <button
                            onClick={(e) => { e.stopPropagation(); swapLayerNodes(realIdx, realIdx - 1); }}
                            disabled={realIdx === 0}
                            style={smBtn(realIdx === 0)}
                            title="Move backward"
                          >↓</button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {boardNode && (isReadOnly
        ? boardOfNode && <BoardModal board={boardOfNode} fallbackTitle={String((boardNode.data as any)?.label ?? "")}
            onClose={() => setBoardNodeId(null)} />
        : <BoardEditor initial={boardOfNode} nodeLabel={String((boardNode.data as any)?.label ?? "")}
            onApply={(b) => { setNodeBoard(boardNode.id, b); setBoardNodeId(null); }}
            onRemove={() => { setNodeBoard(boardNode.id, null); setBoardNodeId(null); }}
            onClose={() => setBoardNodeId(null)} />
      )}
    </BoardContext.Provider>
    </ReadOnlyContext.Provider>
  );
}

export default function FlowchartEditor({ config }: { config: Config }) {
  if (!config?.reactFlowData && !config?.adjustedJson) {
    return (
      <div style={{ padding: 24, color: "var(--color-text-minor, #888)", fontStyle: "italic" }}>
        No flowchart data. Generate one via the Rulebook admin action first.
      </div>
    );
  }
  return (
    <ReactFlowProvider>
      <Editor config={config} />
    </ReactFlowProvider>
  );
}
