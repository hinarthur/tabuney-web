/**
 * Graph data preparation shared by every mount point (admin editor, public
 * read-only viewers, step-by-step tour).
 *
 * The backend emits every node at position (0,0) — layout is a frontend
 * concern (Dagre). Anything that renders a flowchart must go through
 * prepareGraph() so all of them land on the same coordinates.
 */
import { MarkerType, type Edge, type Node } from "@xyflow/react";
import type React from "react";
import { applyDagreLayout } from "./layout";

export const MARKER_SIZE = 14;
export const DEFAULT_MARKER = {
  type: MarkerType.ArrowClosed,
  width: MARKER_SIZE,
  height: MARKER_SIZE,
  color: "var(--fc-edge-stroke, #555)",
};
export const DEFAULT_EDGE_STYLE: React.CSSProperties = {
  strokeWidth: 2,
  stroke: "var(--fc-edge-stroke, #555)",
};

export function getLabelAutoColor(label: unknown): string | undefined {
  if (!label || typeof label !== "string") return undefined;
  const l = label.toLowerCase().trim();
  if (l === "yes" || l === "y") return "var(--fc-edge-yes, #52c41a)";
  if (l === "no"  || l === "n") return "var(--fc-edge-no, #ff4d4f)";
  return undefined;
}

// Retire the OLD floating type names. They were never true floating edges (the
// component just drew a fixed-handle bezier under another name), so they map to
// the built-in equivalent. The current floating edges use different names —
// "float*", see edges/index.ts — and are deliberately not listed here.
export const TYPE_MIGRATE: Record<string, string> = {
  floating:         "default",
  floatingstraight: "straight",
  floatingstep:     "step",
  floatingsimple:   "smoothstep",
};

// Literal colors baked into saved edges by earlier versions of withDefaults
// (before stroke became a CSS var). Treat these as "unset" so old saved
// flowcharts pick up the current --fc-edge-stroke default instead of being
// stuck on a hardcoded gray forever.
const LEGACY_DEFAULT_STROKES = new Set(["#555", "#aaa"]);

export function withDefaults(edges: Edge[]): Edge[] {
  const baseStroke = "var(--fc-edge-stroke, #555)";
  return edges.map((e) => {
    const autoColor = getLabelAutoColor(e.label);
    const savedStroke = (e.style as { stroke?: string } | undefined)?.stroke;
    const mergedStyle = {
      strokeWidth: 2,
      stroke: baseStroke,
      ...(e.style ?? {}),
      ...(savedStroke && LEGACY_DEFAULT_STROKES.has(savedStroke) ? { stroke: baseStroke } : {}),
      ...(autoColor ? { stroke: autoColor } : {}),
    };
    const stroke = (mergedStyle as { stroke?: string }).stroke ?? baseStroke;
    const rawType = e.type ?? "default";
    const type = TYPE_MIGRATE[rawType] ?? rawType;
    return {
      ...e,
      type,
      markerEnd: e.markerEnd && typeof e.markerEnd === "object"
        ? { ...(e.markerEnd as object), width: MARKER_SIZE, height: MARKER_SIZE, color: stroke }
        : { ...DEFAULT_MARKER, color: stroke },
      style: mergedStyle,
    };
  });
}

export type GraphSource = { nodes?: Node[]; edges?: Edge[] } | null | undefined;

/**
 * Phase regions (Preparation / Gameflow / Endgame) are no longer rendered.
 * Flowcharts saved before that change still carry `group` nodes plus children
 * with `parentId` + parent-relative positions, so drop the containers and lift
 * every child back to absolute coordinates — the diagram keeps the exact same
 * layout, just without the boxes around it.
 *
 * The container's name/order is copied down onto each child as phase_label /
 * phase_order first. That is the ONLY copy of it left: the text outline and the
 * HowTo structured data still section by phase, and saving an edited legacy
 * chart writes these nodes back without the group node to read it from.
 */
export function flattenGroups(nodes: Node[]): Node[] {
  const groups = new Map<string, Node>();
  nodes.forEach((n) => { if (n.type === "group") groups.set(n.id, n); });
  if (groups.size === 0) return nodes;

  return nodes
    .filter((n) => n.type !== "group")
    .map((n) => {
      const parentId = (n as { parentId?: string }).parentId;
      const parent = parentId ? groups.get(parentId) : undefined;
      if (!parent) return n;
      const { parentId: _p, extent: _e, ...rest } = n as Node & { parentId?: string };
      const pd = (parent.data ?? {}) as { label?: unknown; order?: unknown; phase_id?: unknown };
      const d = (n.data ?? {}) as Record<string, unknown>;
      return {
        ...rest,
        data: {
          ...d,
          phase_id: d.phase_id ?? pd.phase_id ?? parent.id.replace("__group_", ""),
          phase_label: d.phase_label ?? (typeof pd.label === "string" ? pd.label : undefined),
          phase_order: d.phase_order ?? (typeof pd.order === "number" ? pd.order : undefined),
        },
        position: {
          x: (parent.position?.x ?? 0) + (n.position?.x ?? 0),
          y: (parent.position?.y ?? 0) + (n.position?.y ?? 0),
        },
      } as Node;
    });
}

/**
 * Turn a stored react_flow_json / adjusted_json payload into render-ready
 * nodes + edges: run Dagre when the backend left everything at (0,0), then
 * migrate legacy node shapes (type="default" + kind="action", missing sizes).
 */
export function prepareGraph(source: GraphSource): { nodes: Node[]; edges: Edge[] } {
  if (!source) return { nodes: [], edges: [] };

  let nodes: Node[] = flattenGroups((source.nodes ?? []) as Node[]);
  const edges: Edge[] = withDefaults((source.edges ?? []) as Edge[]);

  const needsLayout = nodes.every(
    (n) => !n.position || (n.position.x === 0 && n.position.y === 0)
  );
  if (needsLayout) nodes = applyDagreLayout(nodes, edges);

  // Migrate old stored nodes: type="default" with kind="action" → type="action"
  // and ensure action nodes have explicit dimensions so NodeResizer works
  nodes = nodes.map((n) => {
    const kind = (n.data as any)?.kind;
    const type = (n.type === "default" && kind === "action") ? "action" : n.type;
    const needsDims = ["action", "diamond", "double", "phase", "oval", "legend"].includes(type as string)
      && !(n.style as any)?.width;
    return {
      ...n,
      type,
      ...(needsDims ? { style: { ...(n.style ?? {}), width: 140, height: 50 } } : {}),
    };
  });

  return { nodes, edges };
}
