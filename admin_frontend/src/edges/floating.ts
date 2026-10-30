/**
 * Floating edge geometry.
 *
 * A normal edge is pinned to a handle: it always leaves the node from the same
 * side no matter where the two nodes sit. A floating edge instead recomputes
 * both endpoints from the current node positions every render, so the line
 * always leaves from the side that faces the other node and re-attaches by
 * itself when either node is dragged.
 *
 * Nodes are treated as rectangles (a diamond uses its bounding box, same as the
 * upstream React Flow example) — good enough at these sizes and far cheaper
 * than a real shape intersection.
 */
import { Position, type InternalNode, type Node } from "@xyflow/react";

type Point = { x: number; y: number };

function rectOf(node: InternalNode<Node>) {
  const { x, y } = node.internals.positionAbsolute;
  const w = node.measured?.width ?? (node.width as number | undefined) ?? 0;
  const h = node.measured?.height ?? (node.height as number | undefined) ?? 0;
  return { x, y, w, h, cx: x + w / 2, cy: y + h / 2 };
}

/** Where the line from `node`'s centre towards `target` crosses `node`'s border. */
function borderPoint(node: InternalNode<Node>, target: Point): Point {
  const r = rectOf(node);
  const dx = target.x - r.cx;
  const dy = target.y - r.cy;
  if (dx === 0 && dy === 0) return { x: r.cx, y: r.cy };

  const hw = Math.max(r.w / 2, 1);
  const hh = Math.max(r.h / 2, 1);
  // Scale the direction vector until it lands on whichever border it hits first
  const scale = 1 / Math.max(Math.abs(dx) / hw, Math.abs(dy) / hh);
  return { x: r.cx + dx * scale, y: r.cy + dy * scale };
}

/** Which side of the node a border point sits on — drives the curve's tangent. */
function sideOf(node: InternalNode<Node>, p: Point): Position {
  const r = rectOf(node);
  const EPS = 1;
  if (p.x <= r.x + EPS) return Position.Left;
  if (p.x >= r.x + r.w - EPS) return Position.Right;
  if (p.y <= r.y + EPS) return Position.Top;
  return Position.Bottom;
}

export function getEdgeParams(source: InternalNode<Node>, target: InternalNode<Node>) {
  const sRect = rectOf(source);
  const tRect = rectOf(target);
  const sp = borderPoint(source, { x: tRect.cx, y: tRect.cy });
  const tp = borderPoint(target, { x: sRect.cx, y: sRect.cy });

  return {
    sx: sp.x,
    sy: sp.y,
    tx: tp.x,
    ty: tp.y,
    sourcePos: sideOf(source, sp),
    targetPos: sideOf(target, tp),
  };
}
