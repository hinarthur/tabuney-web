import dagre from "@dagrejs/dagre";
import type { Node, Edge } from "@xyflow/react";

const NODE_W = 180;
const NODE_H = 60;
const DECISION_W = 160;
const DECISION_H = 80;
const PHASE_GAP = 90;    // breathing room around each phase block
const LEGEND_GAP = 80;   // gap between main graph right edge and legend column

type NodeData = { kind?: string; phase_id?: string | null; phase_order?: number | null; bg?: string; border?: string };

function nodeSize(n: Node): { w: number; h: number } {
  const kind = (n.data as NodeData).kind;
  return kind === "decision"
    ? { w: DECISION_W, h: DECISION_H }
    : { w: NODE_W, h: NODE_H };
}

function phaseOf(n: Node): string | null {
  const pid = (n.data as NodeData)?.phase_id;
  return pid ? String(pid) : null;
}

/**
 * Apply Dagre layout for a flat graph (no phase grouping).
 * rankdir="LR" for top-level flows; "TB" for nodes inside a phase block.
 */
function layoutFlat(nodes: Node[], edges: Edge[], rankdir: "TB" | "LR" = "LR"): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  const ranksep = rankdir === "LR" ? 120 : 80;
  const nodesep = rankdir === "LR" ? 60 : 50;
  g.setGraph({ rankdir, ranksep, nodesep });

  nodes.forEach((n) => {
    const { w, h } = nodeSize(n);
    g.setNode(n.id, { width: w, height: h });
  });
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);

  return nodes.map((n) => {
    const { x, y } = g.node(n.id);
    const { w, h } = nodeSize(n);
    return { ...n, position: { x: x - w / 2, y: y - h / 2 } };
  });
}

/**
 * Full layout. Phases are a layout hint only — nothing is drawn around them:
 * nodes sharing a phase_id are laid out as one block (top-to-bottom), then the
 * blocks themselves are arranged left-to-right by a second Dagre pass, and
 * every node comes back with absolute coordinates and no parentId.
 * Legend nodes are placed in a column to the right of all other content.
 */
export function applyDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const legendNodes = nodes.filter((n) => n.type === "legend");
  const contentNodes = nodes.filter((n) => n.type !== "legend" && n.type !== "group");

  // Bucket content by phase; nodes without a phase stand alone in the meta graph
  const byPhase: Map<string, Node[]> = new Map();
  const ungrouped: Node[] = [];

  contentNodes.forEach((n) => {
    const pid = phaseOf(n);
    if (pid) {
      if (!byPhase.has(pid)) byPhase.set(pid, []);
      byPhase.get(pid)!.push(n);
    } else {
      ungrouped.push(n);
    }
  });

  // No phases at all → one flat pass + legends
  if (byPhase.size === 0) {
    const laid = layoutFlat(contentNodes, edges);
    return [...appendLegends(legendNodes, laid), ...laid];
  }

  // Step 1: lay out each phase block on its own (top-to-bottom)
  const blockMembers: Map<string, Node[]> = new Map();
  const blockSizes: Map<string, { w: number; h: number }> = new Map();

  byPhase.forEach((members, phaseId) => {
    const internalEdges = edges.filter(
      (e) =>
        members.some((n) => n.id === e.source) &&
        members.some((n) => n.id === e.target)
    );
    const laidMembers = layoutFlat(members, internalEdges, "TB");

    // Normalise to a (0,0)-anchored bounding box so the block can be placed as a unit
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    laidMembers.forEach((n) => {
      const { w, h } = nodeSize(n);
      minX = Math.min(minX, n.position.x);
      minY = Math.min(minY, n.position.y);
      maxX = Math.max(maxX, n.position.x + w);
      maxY = Math.max(maxY, n.position.y + h);
    });

    blockMembers.set(
      phaseId,
      laidMembers.map((n) => ({
        ...n,
        position: { x: n.position.x - minX, y: n.position.y - minY },
      }))
    );
    blockSizes.set(phaseId, { w: maxX - minX + PHASE_GAP, h: maxY - minY + PHASE_GAP });
  });

  // Step 2: arrange the blocks (and any phase-less nodes) left-to-right
  const metaGraph = new dagre.graphlib.Graph();
  metaGraph.setDefaultEdgeLabel(() => ({}));
  metaGraph.setGraph({ rankdir: "LR", ranksep: 140, nodesep: 70 });

  const metaId = (phaseId: string) => `__phase_${phaseId}`;

  blockSizes.forEach((sz, phaseId) => {
    metaGraph.setNode(metaId(phaseId), { width: sz.w, height: sz.h });
  });
  ungrouped.forEach((n) => {
    const { w, h } = nodeSize(n);
    metaGraph.setNode(n.id, { width: w, height: h });
  });

  const nodePhase = new Map(contentNodes.map((n) => [n.id, phaseOf(n)]));
  const metaFor = (nodeId: string): string | null => {
    if (!nodePhase.has(nodeId)) return null;
    const pid = nodePhase.get(nodeId)!;
    return pid ? metaId(pid) : nodeId;
  };

  const seen = new Set<string>();
  edges.forEach((e) => {
    const src = metaFor(e.source);
    const tgt = metaFor(e.target);
    if (!src || !tgt || src === tgt) return;
    const key = `${src}→${tgt}`;
    if (seen.has(key)) return;
    seen.add(key);
    metaGraph.setEdge(src, tgt);
  });

  dagre.layout(metaGraph);

  const positioned: Node[] = [];

  blockMembers.forEach((members, phaseId) => {
    const sz = blockSizes.get(phaseId)!;
    let originX = 0, originY = 0;
    try {
      const { x, y } = metaGraph.node(metaId(phaseId));
      originX = x - sz.w / 2 + PHASE_GAP / 2;
      originY = y - sz.h / 2 + PHASE_GAP / 2;
    } catch {
      /* block has no meta position — leave it at the origin */
    }
    positioned.push(
      ...members.map((n) => ({
        ...n,
        position: { x: n.position.x + originX, y: n.position.y + originY },
      }))
    );
  });

  ungrouped.forEach((n) => {
    const { w, h } = nodeSize(n);
    try {
      const { x, y } = metaGraph.node(n.id);
      positioned.push({ ...n, position: { x: x - w / 2, y: y - h / 2 } });
    } catch {
      positioned.push({ ...n, position: n.position ?? { x: 0, y: 0 } });
    }
  });

  return [...appendLegends(legendNodes, positioned), ...positioned];
}

function appendLegends(legendNodes: Node[], positioned: Node[]): Node[] {
  if (legendNodes.length === 0) return [];

  // Find rightmost x of all positioned nodes
  let maxX = 0;
  positioned.forEach((n) => {
    if (n.position) maxX = Math.max(maxX, n.position.x + NODE_W);
  });

  const startX = maxX + LEGEND_GAP;
  let y = 0;
  return legendNodes.map((lg) => {
    const node = { ...lg, position: { x: startX, y } };
    y += 180;
    return node;
  });
}
