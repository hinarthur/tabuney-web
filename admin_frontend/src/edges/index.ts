import {
  LabeledBezierEdge,
  LabeledStraightEdge,
  LabeledSmoothStepEdge,
  LabeledStepEdge,
} from "./LabeledEdge";
import {
  FloatingBezierEdge,
  FloatingStraightEdge,
  FloatingSmoothStepEdge,
  FloatingStepEdge,
} from "./FloatingEdge";

// Two families of the same four path shapes:
//   - the built-in names stay pinned to whichever handle the edge was drawn from
//   - the "float*" names recompute both endpoints from the node positions
// Built-in names are overridden so labels render near the source, not the centre.
export const EDGE_TYPES = {
  default:    LabeledBezierEdge,
  straight:   LabeledStraightEdge,
  smoothstep: LabeledSmoothStepEdge,
  step:       LabeledStepEdge,
  floatbezier:   FloatingBezierEdge,
  floatstraight: FloatingStraightEdge,
  floatsmooth:   FloatingSmoothStepEdge,
  floatstep:     FloatingStepEdge,
};

/** Fixed-handle type → its floating counterpart. */
export const FIXED_TO_FLOAT: Record<string, string> = {
  default:    "floatbezier",
  straight:   "floatstraight",
  smoothstep: "floatsmooth",
  step:       "floatstep",
};

/** Floating type → its fixed-handle counterpart. */
export const FLOAT_TO_FIXED: Record<string, string> = Object.fromEntries(
  Object.entries(FIXED_TO_FLOAT).map(([fixed, float]) => [float, fixed])
);

export function isFloatingEdgeType(type: string | undefined): boolean {
  return !!type && type in FLOAT_TO_FIXED;
}

/** The path shape of an edge, floating or not — one of the built-in names. */
export function edgeShape(type: string | undefined): string {
  const t = type ?? "default";
  return FLOAT_TO_FIXED[t] ?? t;
}

/** Same shape, switched to (or away from) floating endpoints. */
export function edgeTypeFor(shape: string, floating: boolean): string {
  return floating ? FIXED_TO_FLOAT[shape] ?? shape : shape;
}
