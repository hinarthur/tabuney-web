/**
 * Floating edge variants — the endpoints are not pinned to a handle. Both ends
 * are recomputed from the live node positions (see ./floating.ts), so the line
 * always leaves from the side facing the other node and follows along when
 * either node is dragged.
 *
 * Same label rendering as the fixed-handle edges: they share edgeBody(), so the
 * label can still be dragged along the edge and reset with a double-click.
 *
 * Falls back to the fixed-handle edge when the geometry cannot be computed — a
 * node still being measured, or a self-loop, where "the side facing the other
 * node" is undefined.
 */
import {
  getBezierPath,
  getStraightPath,
  getSmoothStepPath,
  useInternalNode,
  type EdgeProps,
  type Position,
} from "@xyflow/react";
import { getEdgeParams } from "./floating";
import {
  edgeBody,
  LabeledBezierEdge,
  LabeledStraightEdge,
  LabeledSmoothStepEdge,
  LabeledStepEdge,
} from "./LabeledEdge";

type PathParams = {
  sourceX: number; sourceY: number; sourcePosition: Position;
  targetX: number; targetY: number; targetPosition: Position;
};
type PathFn = (p: PathParams) => [string, number, number, ...number[]];

const bezierPath: PathFn = (p) => getBezierPath(p);
const straightPath: PathFn = ({ sourceX, sourceY, targetX, targetY }) =>
  getStraightPath({ sourceX, sourceY, targetX, targetY });
const smoothPath: PathFn = (p) => getSmoothStepPath(p);
const stepPath: PathFn = (p) => getSmoothStepPath({ ...p, borderRadius: 0 });

/** Returns the rendered edge, or null when it should fall back to fixed handles. */
function useFloatingEdge(props: EdgeProps, pathFn: PathFn) {
  const source = useInternalNode(props.source);
  const target = useInternalNode(props.target);
  if (!source || !target || props.source === props.target) return null;

  const { sx, sy, tx, ty, sourcePos, targetPos } = getEdgeParams(source, target);
  const [path, midX, midY] = pathFn({
    sourceX: sx, sourceY: sy, sourcePosition: sourcePos,
    targetX: tx, targetY: ty, targetPosition: targetPos,
  });
  return edgeBody(props.id, path, sx, sy, midX, midY, props);
}

export function FloatingBezierEdge(props: EdgeProps) {
  return useFloatingEdge(props, bezierPath) ?? <LabeledBezierEdge {...props} />;
}

export function FloatingStraightEdge(props: EdgeProps) {
  return useFloatingEdge(props, straightPath) ?? <LabeledStraightEdge {...props} />;
}

export function FloatingSmoothStepEdge(props: EdgeProps) {
  return useFloatingEdge(props, smoothPath) ?? <LabeledSmoothStepEdge {...props} />;
}

export function FloatingStepEdge(props: EdgeProps) {
  return useFloatingEdge(props, stepPath) ?? <LabeledStepEdge {...props} />;
}
