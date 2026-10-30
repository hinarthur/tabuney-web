import React, { useContext, useLayoutEffect, useRef, useState } from "react";
import {
  BaseEdge,
  getBezierPath,
  getStraightPath,
  getSmoothStepPath,
  useReactFlow,
  type EdgeProps,
} from "@xyflow/react";
import { ReadOnlyContext } from "../ReadOnlyContext";

// SVG-native draggable label — no EdgeLabelRenderer needed.
// Coordinate conversion uses svg.getScreenCTM().inverse() which correctly
// accounts for any zoom/pan without needing getViewport().
function SvgDraggableLabel({ edgeId, label, x, y, color }: {
  edgeId: string; label: string; x: number; y: number; color: string;
}) {
  const readOnly = useContext(ReadOnlyContext);
  const { setEdges } = useReactFlow();
  const textRef = useRef<SVGTextElement>(null);
  const [tw, setTw] = useState(0);
  const [th, setTh] = useState(0);

  useLayoutEffect(() => {
    if (textRef.current) {
      const b = textRef.current.getBBox();
      setTw(b.width);
      setTh(b.height);
    }
  }, [label]);

  if (!label) return null;

  const px = 8, py = 4;
  const HIT = 6; // extra invisible margin around the label so it is easier to grab
  const rw = tw + px * 2;
  const rh = th + py * 2;

  const onMouseDown = readOnly ? undefined : (e: React.MouseEvent<SVGGElement>) => {
    e.stopPropagation();
    e.preventDefault();

    const svg = (e.currentTarget as SVGElement).closest("svg") as SVGSVGElement | null;
    if (!svg) return;

    const toFlow = (cx: number, cy: number) => {
      const pt = svg.createSVGPoint();
      pt.x = cx; pt.y = cy;
      const ctm = svg.getScreenCTM();
      return ctm ? pt.matrixTransform(ctm.inverse()) : { x: 0, y: 0 };
    };

    const start = toFlow(e.clientX, e.clientY);
    const ox = x, oy = y;

    const onMove = (me: MouseEvent) => {
      const cur = toFlow(me.clientX, me.clientY);
      setEdges((eds) =>
        eds.map((ed) =>
          ed.id === edgeId
            ? { ...ed, data: { ...(ed.data ?? {}), labelX: ox + cur.x - start.x, labelY: oy + cur.y - start.y } }
            : ed
        )
      );
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const onDblClick = readOnly ? undefined : (e: React.MouseEvent) => {
    e.stopPropagation();
    setEdges((eds) =>
      eds.map((ed) => {
        if (ed.id !== edgeId) return ed;
        const d = { ...(ed.data ?? {}) } as Record<string, unknown>;
        delete d.labelX;
        delete d.labelY;
        return { ...ed, data: d };
      })
    );
  };

  return (
    <g
      data-rf-label={edgeId}
      transform={`translate(${x},${y})`}
      onMouseDown={onMouseDown}
      onDoubleClick={onDblClick}
      title={readOnly ? undefined : "Drag to reposition · Double-click to reset"}
      style={{ cursor: readOnly ? "default" : "move" }}
    >
      {tw > 0 && (
        <rect x={-rw / 2 - HIT} y={-rh / 2 - HIT} width={rw + HIT * 2} height={rh + HIT * 2}
          fill="transparent" stroke="none" style={{ pointerEvents: "all" }} />
      )}
      {tw > 0 && (
        <rect x={-rw / 2} y={-rh / 2} width={rw} height={rh} rx={3}
          style={{ fill: "var(--fc-edge-label-bg, rgba(255,255,255,0.85))" }} stroke="none"
        />
      )}
      <text
        ref={textRef}
        textAnchor="middle" dominantBaseline="middle"
        style={{ fontSize: 12, fontWeight: 600, fill: color, userSelect: "none", pointerEvents: "none" }}
      >
        {label}
      </text>
    </g>
  );
}

export function edgeBody(
  id: string,
  edgePath: string,
  sourceX: number,
  sourceY: number,
  midX: number,
  midY: number,
  { markerEnd, markerStart, style, label, animated, data }: Pick<EdgeProps,
    "markerEnd" | "markerStart" | "style" | "label" | "animated" | "data">
) {
  const strokeColor = (style?.stroke as string | undefined) ?? "var(--fc-edge-stroke, #555)";
  const edgeStyle = {
    strokeWidth: 2,
    stroke: strokeColor,
    ...style,
    ...(animated ? { strokeDasharray: "6 3" } : {}),
  };

  const computedX = sourceX + (midX - sourceX) * 0.5;
  const computedY = sourceY + (midY - sourceY) * 0.5;
  const lx = (data as any)?.labelX ?? computedX;
  const ly = (data as any)?.labelY ?? computedY;

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} markerStart={markerStart} style={edgeStyle} />
      {label && (
        <SvgDraggableLabel edgeId={id} label={String(label)} x={lx} y={ly} color={strokeColor} />
      )}
    </>
  );
}

export function LabeledBezierEdge({
  id, sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, ...rest
}: EdgeProps) {
  const [edgePath, midX, midY] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  return edgeBody(id, edgePath, sourceX, sourceY, midX, midY, rest);
}

export function LabeledStraightEdge({
  id, sourceX, sourceY, targetX, targetY, ...rest
}: EdgeProps) {
  const [edgePath, midX, midY] = getStraightPath({ sourceX, sourceY, targetX, targetY });
  return edgeBody(id, edgePath, sourceX, sourceY, midX, midY, rest);
}

export function LabeledSmoothStepEdge({
  id, sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, ...rest
}: EdgeProps) {
  const [edgePath, midX, midY] = getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  return edgeBody(id, edgePath, sourceX, sourceY, midX, midY, rest);
}

export function LabeledStepEdge({
  id, sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, ...rest
}: EdgeProps) {
  const [edgePath, midX, midY] = getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 0 });
  return edgeBody(id, edgePath, sourceX, sourceY, midX, midY, rest);
}
