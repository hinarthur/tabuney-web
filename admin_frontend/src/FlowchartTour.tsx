/**
 * Step-by-step guided tour over a published flowchart.
 *
 * Mounted in the popup window opened by the 👣 toolbar button on
 * edition_detail.html. Shows the same chart the viewer pane shows (same
 * prepareGraph → same Dagre layout), but focuses one node at a time: the
 * current node stays sharp, everything else is blurred back, and the viewport
 * pans/zooms between nodes.
 *
 * Navigation follows edges rather than a flattened list, because flowcharts
 * branch and loop. Where you have been is a visited stack, so stepping back
 * out of a branch returns the way you came.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Controls,
  MiniMap,
  Panel,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { nodeTypes } from "./nodes";
import { EDGE_TYPES } from "./edges";
import { prepareGraph } from "./graph";
import { ReadOnlyContext } from "./ReadOnlyContext";
import { BoardContext } from "./board/BoardContext";
import BoardModal from "./board/BoardModal";
import { asBoard } from "./board/types";

// Per-node feedback goes to the same endpoint as the page's 🚩 suggestion
// button (FlowchartSuggestionCreateView), with node_id / node_label added.
// csrfToken is only present for signed-in readers: anonymous requests are
// exempt server-side, so the page never has to hand out a csrftoken cookie.
export interface TourFeedbackConfig {
  enabled: boolean;
  url: string;
  flowchartId: string;
  editionId?: string;
  csrfToken?: string;
}

export interface TourConfig {
  reactFlowData: { nodes: Node[]; edges: Edge[] } | null;
  title?: string;
  labels?: Record<string, string>;
  feedback?: TourFeedbackConfig;
}

// Matches SUGGESTION_MAX_LENGTH in game/views/suggestion_views.py
const FEEDBACK_MAX_LEN = 2000;

// Decorative node types that are never a tour stop — they stay blurred
// throughout so the legend / captions still read as background context.
const NON_STOP_TYPES = new Set(["legend", "page", "text", "image"]);

// The tour is meant to be readable across a table, so each step is zoomed in
// as far as it will go: fitBounds fills the window with the focused node and
// TOUR_MAX_ZOOM is the only thing holding it back on small nodes.
const TOUR_MAX_ZOOM = 4;
const TOUR_PADDING = 0.2;
const PAN_MS = 600;

const FALLBACK_LABELS: Record<string, string> = {
  first: "Back to start",
  prev: "Previous step",
  next: "Next step",
  last: "Jump to end",
  choose: "Choose a branch:",
  notes: "Notes",
  branch_unnamed: "(unnamed branch)",
  fb_button: "Feedback on this step",
  fb_placeholder: "What is wrong or unclear about this step?",
  fb_success: "Thanks! We'll take a look.",
  fb_empty: "Please write your suggestion",
  fb_error: "Something went wrong. Please try again.",
  fb_submit: "Submit",
  fb_cancel: "Cancel",
};

type FeedbackState =
  | { phase: "closed" }
  | { phase: "editing" | "sending"; text: string; error?: string }
  | { phase: "sent" };

function nodeLabel(n: Node | undefined): string {
  const raw = (n?.data as { label?: unknown } | undefined)?.label;
  return typeof raw === "string" ? raw.replace(/\s+/g, " ").trim() : "";
}

function truncate(s: string, max = 16): string {
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

// LegendNode keeps its text in data.title / data.content, not data.label
function noteTitle(n: Node | undefined): string {
  const raw = (n?.data as { title?: unknown } | undefined)?.title;
  return typeof raw === "string" ? raw.trim() : "";
}

function noteContent(n: Node | undefined): string {
  const raw = (n?.data as { content?: unknown } | undefined)?.content;
  return typeof raw === "string" ? raw : "";
}

function boundIdsOf(n: Node): string[] {
  const raw = (n.data as { legend_ids?: unknown } | undefined)?.legend_ids;
  return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string") : [];
}

function Tour({ config }: { config: TourConfig }) {
  // getNodesBounds comes off the hook rather than the bare import so bounds are
  // read through React Flow's internal node lookup (measured sizes included).
  const { fitBounds, getNodesBounds } = useReactFlow();

  const graph = useMemo(() => prepareGraph(config.reactFlowData), [config.reactFlowData]);
  const { nodes: baseNodes, edges: baseEdges } = graph;

  const t = useCallback(
    (key: string) => config.labels?.[key] ?? FALLBACK_LABELS[key] ?? key,
    [config.labels]
  );

  const nodeById = useMemo(() => {
    const m = new Map<string, Node>();
    baseNodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [baseNodes]);

  const outgoingBySource = useMemo(() => {
    const m = new Map<string, Edge[]>();
    baseEdges.forEach((e) => {
      const list = m.get(e.source);
      if (list) list.push(e);
      else m.set(e.source, [e]);
    });
    return m;
  }, [baseEdges]);

  const { startId, endId } = useMemo(() => {
    const stops = baseNodes.filter((n) => !NON_STOP_TYPES.has(n.type ?? ""));
    const kindOf = (n: Node) => (n.data as { kind?: unknown } | undefined)?.kind;
    const hasIncoming = new Set(baseEdges.map((e) => e.target));
    const hasOutgoing = new Set(baseEdges.map((e) => e.source));

    const start =
      stops.find((n) => kindOf(n) === "start") ??
      stops.find((n) => !hasIncoming.has(n.id)) ??
      stops[0];
    const end =
      stops.find((n) => kindOf(n) === "end") ??
      [...stops].reverse().find((n) => !hasOutgoing.has(n.id)) ??
      stops[stops.length - 1];

    return { startId: start?.id ?? null, endId: end?.id ?? null };
  }, [baseNodes, baseEdges]);

  // ~15% of generated decision nodes have unlabeled outgoing edges. Falling
  // straight back to a generic string would render several identical buttons
  // with nothing to choose between, so name the branch after where it goes.
  const branchText = useCallback(
    (e: Edge): string => {
      if (typeof e.label === "string" && e.label.trim()) return e.label.trim();
      return nodeLabel(nodeById.get(e.target)) || t("branch_unnamed");
    },
    [nodeById, t]
  );

  // Legend nodes sit outside the flow and stay blurred, but they hold rules
  // notes the reader may want mid-tour. Surface each one as a panel button
  // that opens the text in place, so checking a note never costs your place.
  const allLegends = useMemo(
    () => baseNodes.filter((n) => n.type === "legend"),
    [baseNodes]
  );
  // Legends bound to a node (data.legend_ids) open from a button on that node
  // instead, so they drop out of the Notes row.
  const boundLegendIds = useMemo(() => {
    const legendIds = new Set(allLegends.map((n) => n.id));
    const s = new Set<string>();
    baseNodes.forEach((n) => {
      boundIdsOf(n).forEach((id) => { if (legendIds.has(id)) s.add(id); });
    });
    return s;
  }, [baseNodes, allLegends]);
  const legends = useMemo(
    () => allLegends.filter((n) => !boundLegendIds.has(n.id)),
    [allLegends, boundLegendIds]
  );
  const [openNoteIds, setOpenNoteIds] = useState<string[]>([]);
  const openNotes = openNoteIds
    .map((id) => nodeById.get(id))
    .filter((n): n is Node => !!n);

  const [path, setPath] = useState<string[]>(() => (startId ? [startId] : []));
  const currentId = path[path.length - 1] ?? null;

  const [boardNodeId, setBoardNodeId] = useState<string | null>(null);
  const boardCtx = useMemo(() => ({ openBoard: setBoardNodeId }), []);
  const boardNode = boardNodeId ? nodeById.get(boardNodeId) : undefined;
  const openBoard = asBoard((boardNode?.data as { board?: unknown } | undefined)?.board);

  const fbConfig = config.feedback?.enabled && config.feedback.flowchartId ? config.feedback : null;
  const [feedback, setFeedback] = useState<FeedbackState>({ phase: "closed" });

  // A note, board or feedback form opened from the previous node must not
  // follow the reader along.
  useEffect(() => {
    setOpenNoteIds([]);
    setBoardNodeId(null);
    setFeedback({ phase: "closed" });
  }, [currentId]);

  const submitFeedback = useCallback(async () => {
    if (!fbConfig || !currentId || feedback.phase !== "editing") return;
    const text = feedback.text.trim();
    if (!text) {
      setFeedback({ ...feedback, error: t("fb_empty") });
      return;
    }
    setFeedback({ phase: "sending", text: feedback.text });
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (fbConfig.csrfToken) headers["X-CSRFToken"] = fbConfig.csrfToken;
      const res = await fetch(fbConfig.url, {
        method: "POST",
        headers,
        credentials: "same-origin",
        body: JSON.stringify({
          flowchart_id: fbConfig.flowchartId,
          edition_id: fbConfig.editionId ?? "",
          node_id: currentId,
          node_label: nodeLabel(nodeById.get(currentId)),
          content: text,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.success) {
        setFeedback({ phase: "sent" });
      } else {
        const errs = data.errors ? Object.values(data.errors).join(" ") : "";
        setFeedback({ phase: "editing", text: feedback.text, error: errs || t("fb_error") });
      }
    } catch {
      setFeedback({ phase: "editing", text: feedback.text, error: t("fb_error") });
    }
  }, [fbConfig, currentId, feedback, nodeById, t]);
  // Memoised so activeEdgeIds/viewEdges don't rebuild on every render
  const outs = useMemo(
    () => (currentId ? outgoingBySource.get(currentId) ?? [] : []),
    [currentId, outgoingBySource]
  );
  const isBranch = outs.length >= 2;

  // ── navigation ──────────────────────────────────────────────────────────────
  const goFirst = useCallback(() => { if (startId) setPath([startId]); }, [startId]);
  const goPrev = useCallback(() => setPath((p) => (p.length > 1 ? p.slice(0, -1) : p)), []);
  const goNext = useCallback(() => {
    setPath((p) => {
      const cur = p[p.length - 1];
      const o = cur ? outgoingBySource.get(cur) ?? [] : [];
      return o.length === 1 ? [...p, o[0].target] : p;
    });
  }, [outgoingBySource]);
  // Append rather than reset so "previous" still walks back to where you were.
  const goLast = useCallback(() => {
    setPath((p) => (endId && p[p.length - 1] !== endId ? [...p, endId] : p));
  }, [endId]);
  const goBranch = useCallback((target: string) => setPath((p) => [...p, target]), []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // Arrow/Home/End inside the feedback textarea move the caret, not the tour
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "TEXTAREA" || el.tagName === "INPUT")) return;
      if (e.key === "ArrowRight") { e.preventDefault(); goNext(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); goPrev(); }
      else if (e.key === "Home") { e.preventDefault(); goFirst(); }
      else if (e.key === "End") { e.preventDefault(); goLast(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goNext, goPrev, goFirst, goLast]);

  // ── focus / blur ────────────────────────────────────────────────────────────
  const activeEdgeIds = useMemo(() => new Set(outs.map((e) => e.id)), [outs]);

  const viewNodes = useMemo(
    () => baseNodes.map((n) => {
      const isCurrent = n.id === currentId;
      const ids = isCurrent ? boundIdsOf(n).filter((id) => nodeById.get(id)?.type === "legend") : [];
      return {
        ...n,
        className: isCurrent ? "fc-tour-focus" : "fc-tour-dim",
        ...(ids.length
          ? { data: { ...n.data, onShowLegend: () => setOpenNoteIds((cur) => (cur.length ? [] : ids)) } }
          : {}),
      };
    }),
    [baseNodes, currentId, nodeById]
  );

  // Keep the current node's outgoing edges sharp — that is how the reader sees
  // which branches exist and where they lead.
  const viewEdges = useMemo(
    () => baseEdges.map((e) => ({
      ...e,
      className: activeEdgeIds.has(e.id) ? "fc-tour-edge-active" : "fc-tour-dim",
    })),
    [baseEdges, activeEdgeIds]
  );

  // ── pan to the current node ─────────────────────────────────────────────────
  // Node dimensions are only known after the first paint, so wait for the
  // measure pass — fitting before it would use a zero-sized box at the origin.
  //
  // Deliberately no `fitView` prop on <ReactFlow>: its initial fit is driven by
  // the same measure pass and lands after this effect, so it would overwrite
  // the first fitBounds and leave the start node zoomed out. Instead the canvas
  // is held invisible until the first fit lands, which also hides the jump.
  const nodesInitialized = useNodesInitialized();
  const [viewReady, setViewReady] = useState(false);
  const firstFitRef = useRef(true);
  useEffect(() => {
    if (!currentId || !nodesInitialized) return;
    const b = getNodesBounds([currentId]);
    if (!b.width && !b.height) return;
    const isFirst = firstFitRef.current;
    firstFitRef.current = false;
    fitBounds(b, { padding: TOUR_PADDING, duration: isFirst ? 0 : PAN_MS });
    if (isFirst) setViewReady(true);
  }, [currentId, nodesInitialized, getNodesBounds, fitBounds]);

  if (!currentId) {
    return <div className="fc-tour-empty">—</div>;
  }

  const btn = (
    key: string,
    icon: string,
    onClick: () => void,
    disabled: boolean
  ) => (
    <button type="button" className="fc-tour-btn" onClick={onClick}
            disabled={disabled} title={t(key)} aria-label={t(key)}>
      <span aria-hidden="true">{icon}</span>
    </button>
  );

  return (
    <ReadOnlyContext.Provider value={true}>
    <BoardContext.Provider value={boardCtx}>
      <ReactFlow
        id="fc-tour"
        nodes={viewNodes}
        edges={viewEdges}
        nodeTypes={nodeTypes}
        edgeTypes={EDGE_TYPES}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        minZoom={0.1}
        maxZoom={TOUR_MAX_ZOOM}
        proOptions={{ hideAttribution: false }}
        style={{ opacity: viewReady ? 1 : 0, transition: "opacity .2s ease" }}
      >
        <Controls showInteractive={false} />
        <MiniMap nodeStrokeWidth={3} zoomable pannable style={{ width: 100, height: 75 }} />

        <Panel position="bottom-center" className="fc-tour-panel">
          {openNotes.length > 0 && (
            <div className="fc-tour-note" role="note">
              <button type="button" className="fc-tour-note-close"
                      aria-label="Close" onClick={() => setOpenNoteIds([])}>×</button>
              {openNotes.map((n) => (
                <div key={n.id}>
                  {noteTitle(n) && <div className="fc-tour-note-title">{noteTitle(n)}</div>}
                  <div className="fc-tour-note-text">{noteContent(n)}</div>
                </div>
              ))}
            </div>
          )}

          {isBranch && (
            <div className="fc-tour-branches">
              <span className="fc-tour-branches-label">{t("choose")}</span>
              {outs.map((e) => {
                const label = branchText(e);
                return (
                  <button key={e.id} type="button" className="fc-tour-branch"
                          title={label} onClick={() => goBranch(e.target)}>
                    {truncate(label, 28)}
                  </button>
                );
              })}
            </div>
          )}

          {fbConfig && feedback.phase !== "closed" && (
            <div className="fc-tour-note fc-tour-feedback" role="dialog" aria-label={t("fb_button")}>
              <button type="button" className="fc-tour-note-close"
                      aria-label={t("fb_cancel")}
                      onClick={() => setFeedback({ phase: "closed" })}>×</button>
              <div className="fc-tour-note-title">
                {t("fb_button")}
                {nodeLabel(nodeById.get(currentId)) && (
                  <span className="fc-tour-feedback-target">
                    {" · "}{truncate(nodeLabel(nodeById.get(currentId)), 40)}
                  </span>
                )}
              </div>
              {feedback.phase === "sent" ? (
                <div className="fc-tour-feedback-msg success" role="status">{t("fb_success")}</div>
              ) : (
                <>
                  <textarea className="fc-tour-feedback-text" rows={3} autoFocus
                            maxLength={FEEDBACK_MAX_LEN}
                            placeholder={t("fb_placeholder")}
                            value={feedback.text}
                            disabled={feedback.phase === "sending"}
                            onChange={(e) => setFeedback({ phase: "editing", text: e.target.value })} />
                  {feedback.phase === "editing" && feedback.error && (
                    <div className="fc-tour-feedback-msg error" role="status">{feedback.error}</div>
                  )}
                  <div className="fc-tour-feedback-actions">
                    <button type="button" className="fc-tour-feedback-submit"
                            disabled={feedback.phase === "sending"}
                            onClick={submitFeedback}>{t("fb_submit")}</button>
                  </div>
                </>
              )}
            </div>
          )}

          <div className="fc-tour-nav">
            {btn("first", "⏮", goFirst, path.length === 1)}
            {btn("prev", "◀", goPrev, path.length === 1)}
            {btn("next", "▶", goNext, outs.length !== 1)}
            {btn("last", "⏭", goLast, !endId || currentId === endId)}
            {fbConfig && (
              <button type="button"
                      className={`fc-tour-btn fc-tour-feedback-btn${feedback.phase !== "closed" ? " active" : ""}`}
                      title={t("fb_button")} aria-label={t("fb_button")}
                      onClick={() => setFeedback(
                        feedback.phase === "closed" ? { phase: "editing", text: "" } : { phase: "closed" }
                      )}>
                <span aria-hidden="true">💬</span>
              </button>
            )}
          </div>

          {legends.length > 0 && (
            <div className="fc-tour-notes">
              <span className="fc-tour-notes-label">{t("notes")}</span>
              {legends.map((n, i) => {
                const label = noteTitle(n) || `${t("notes")} ${i + 1}`;
                return (
                  <button key={n.id} type="button" title={label}
                          className={`fc-tour-note-btn${openNoteIds[0] === n.id ? " active" : ""}`}
                          onClick={() => setOpenNoteIds(openNoteIds[0] === n.id ? [] : [n.id])}>
                    <i className="fa-solid fa-circle-info" aria-hidden="true" />
                    {truncate(label, 20)}
                  </button>
                );
              })}
            </div>
          )}
        </Panel>
      </ReactFlow>
      {openBoard && (
        <BoardModal board={openBoard} fallbackTitle={nodeLabel(boardNode)}
          onClose={() => setBoardNodeId(null)} />
      )}
    </BoardContext.Provider>
    </ReadOnlyContext.Provider>
  );
}

export default function FlowchartTour({ config }: { config: TourConfig }) {
  return (
    <ReactFlowProvider>
      <Tour config={config} />
    </ReactFlowProvider>
  );
}
