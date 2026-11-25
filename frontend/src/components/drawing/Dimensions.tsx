import { useRef, useState } from "react";
import type {
  CircleDim,
  DimOverride,
  Dimension,
  LinearDim,
  Part,
  SheetLayout,
  ViewPlacement,
} from "../../api/types";
import { useStore } from "../../state/store";
import { INK } from "./lineStyles";

// ISO 129 / ISO 3098 proportions, paper mm
const FONT = "Arial, Helvetica, sans-serif";
const TEXT = 3.5;
const ARROW_L = 3;
const ARROW_W = 0.5; // half width
const EXT_GAP = 1; // gap between object and extension line
const EXT_OVER = 2; // extension beyond the dimension line
const TEXT_LIFT = 1.2; // text baseline clearance above the dimension line
const SNAP = 2.5;
const HOVER = "#0284c7";

type Pt = [number, number];
type Box = [number, number, number, number]; // x0, y0, x1, y1

const fmtValue = (v: number) => String(Number(v.toFixed(2)));
const textWidth = (s: string) => s.length * TEXT * 0.56;
const snap = (v: number, on: boolean) => (on ? Math.round(v / SNAP) * SNAP : v);
const overlaps = (a: Box, b: Box) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];

interface Geo {
  placement: ViewPlacement;
  w: number;
  h: number;
}

const toPaper = (g: Geo, x: number, y: number): Pt => [
  g.placement.x_offset + x * g.placement.scale,
  g.placement.y_offset + y * g.placement.scale,
];

// ---------------------------------------------------------------------------
// Pure geometry (shared by rendering, dragging and the collision pass)
// ---------------------------------------------------------------------------
function linearGeom(d: LinearDim, ov: DimOverride, g: Geo) {
  const off = ov.offset_mm ?? d.offset_mm;
  const shift = ov.text_shift_mm ?? d.text_shift_mm;
  const P1 = toPaper(g, d.x1, d.y1);
  const P2 = toPaper(g, d.x2, d.y2);
  const p = g.placement;
  const horiz = d.orientation === "horizontal";
  // Reference the offset is measured from — fixed by the ORIGINAL side so drags are stable.
  const positive = d.offset_mm >= 0;
  const ref = horiz
    ? d.offset_from === "edge"
      ? positive ? p.y_offset : p.y_offset + g.h * p.scale
      : positive ? Math.min(P1[1], P2[1]) : Math.max(P1[1], P2[1])
    : d.offset_from === "edge"
      ? positive ? p.x_offset + g.w * p.scale : p.x_offset
      : positive ? Math.max(P1[0], P2[0]) : Math.min(P1[0], P2[0]);
  const along = (pt: Pt) => (horiz ? pt[0] : pt[1]);
  const line = horiz ? ref - off : ref + off;
  const a1 = Math.min(along(P1), along(P2));
  const a2 = Math.max(along(P1), along(P2));
  const mid = (a1 + a2) / 2 + shift;
  const label = `${d.prefix}${fmtValue(d.value_mm)}${d.tolerance_text ? ` ${d.tolerance_text}` : ""}`;
  const tw = textWidth(label);
  const box: Box = horiz
    ? [mid - tw / 2, line - TEXT_LIFT - TEXT, mid + tw / 2, line - 0.4]
    : [line - TEXT_LIFT - TEXT, mid - tw / 2, line - 0.4, mid + tw / 2];
  return { P1, P2, horiz, ref, line, a1, a2, mid, label, box };
}

function circleGeom(d: CircleDim, ov: DimOverride, g: Geo, autoLen?: number) {
  const C = toPaper(g, d.cx, d.cy);
  const R = d.radius * g.placement.scale;
  const theta = ((ov.leader_angle_deg ?? d.leader_angle_deg) * Math.PI) / 180;
  const L = ov.leader_len_mm ?? autoLen ?? d.leader_len_mm;
  const u: Pt = [Math.cos(theta), -Math.sin(theta)]; // paper y-down
  const E: Pt = [C[0] + u[0] * R, C[1] + u[1] * R]; // arrow tip on the circle / arc
  const s = d.inside ? -1 : 1; // inside: leader runs back through the centre
  const K: Pt = [E[0] + s * u[0] * L, E[1] + s * u[1] * L];
  const sx = K[0] - E[0] >= 0 ? 1 : -1;
  const tw = textWidth(d.label_text);
  const textX = K[0] + sx * (tw / 2 + 1);
  const textY = K[1] - TEXT_LIFT;
  const box: Box = [textX - tw / 2, textY - TEXT, textX + tw / 2, textY + 0.8];
  return { C, R, u, E, K, s, sx, tw, textX, textY, box };
}

// ---------------------------------------------------------------------------
function Arrow({ tip, dir }: { tip: Pt; dir: Pt }) {
  // dir: unit vector pointing from tail toward the tip
  const [tx, ty] = tip;
  const bx = tx - dir[0] * ARROW_L;
  const by = ty - dir[1] * ARROW_L;
  const nx = -dir[1] * ARROW_W;
  const ny = dir[0] * ARROW_W;
  return <path d={`M${tx} ${ty}L${bx + nx} ${by + ny}L${bx - nx} ${by - ny}Z`} fill="currentColor" stroke="none" />;
}

/** Paper-space position of the pointer. */
function paperPoint(e: React.PointerEvent, el: SVGGraphicsElement): Pt {
  const svg = el.ownerSVGElement!;
  const pt = svg.createSVGPoint();
  pt.x = e.clientX;
  pt.y = e.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM()!.inverse());
  return [p.x, p.y];
}

/** Drag + hover + double-click-to-reset handlers for a dimension label. */
function useLabelInteraction(id: string, onDrag: (p: Pt) => void) {
  const resetOverride = useStore((s) => s.resetOverride);
  const dragging = useRef(false);
  const [hover, setHover] = useState(false);
  const props = {
    style: { cursor: "move", userSelect: "none" } as const,
    onPointerDown: (e: React.PointerEvent<SVGGraphicsElement>) => {
      e.stopPropagation(); // don't pan the canvas
      e.preventDefault();
      dragging.current = true;
      try {
        e.currentTarget.setPointerCapture(e.pointerId);
      } catch {
        /* pen/touch emulation or synthetic events: dragging still works without capture */
      }
    },
    onPointerMove: (e: React.PointerEvent<SVGGraphicsElement>) => {
      if (dragging.current) onDrag(paperPoint(e, e.currentTarget));
    },
    onPointerUp: (e: React.PointerEvent<SVGGraphicsElement>) => {
      dragging.current = false;
      e.currentTarget.releasePointerCapture?.(e.pointerId);
    },
    onPointerEnter: () => setHover(true),
    onPointerLeave: () => setHover(false),
    onDoubleClick: (e: React.MouseEvent) => {
      e.stopPropagation();
      resetOverride(id);
    },
  };
  return { hover, props };
}

const textProps = {
  fontSize: TEXT,
  fontFamily: FONT,
  stroke: "#fff",
  strokeWidth: 0.9,
  paintOrder: "stroke" as const,
};

// ---------------------------------------------------------------------------
function Linear({ d, ov, g, thin, snapOn }: { d: LinearDim; ov: DimOverride; g: Geo; thin: number; snapOn: boolean }) {
  const setOverride = useStore((s) => s.setOverride);
  const geo = linearGeom(d, ov, g);
  const { P1, P2, horiz, ref, line, a1, a2, mid, label } = geo;
  const { hover, props } = useLabelInteraction(d.id, ([x, y]) => {
    if (horiz) {
      const newLine = snap(y + TEXT_LIFT, snapOn);
      setOverride(d.id, { offset_mm: ref - newLine, text_shift_mm: snap(x - (a1 + a2) / 2, snapOn) });
    } else {
      const newLine = snap(x + TEXT_LIFT, snapOn);
      setOverride(d.id, { offset_mm: newLine - ref, text_shift_mm: snap(y - (a1 + a2) / 2, snapOn) });
    }
  });

  // local frame: "along" the dimension / "across" it
  const along = (pt: Pt) => (horiz ? pt[0] : pt[1]);
  const across = (pt: Pt) => (horiz ? pt[1] : pt[0]);
  const mk = (a: number, b: number): Pt => (horiz ? [a, b] : [b, a]);
  const unit = (s: number): Pt => (horiz ? [s, 0] : [0, s]);
  const outside = a2 - a1 < 2 * ARROW_L + 2; // too short: arrows outside, pointing in

  const exts = [P1, P2].flatMap((P, i) => {
    const b = across(P);
    if (Math.abs(b - line) < 0.5) return [];
    const dir = Math.sign(line - b);
    const from = mk(along(P), b + dir * EXT_GAP);
    const to = mk(along(P), line + dir * EXT_OVER);
    return [<line key={i} x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]} />];
  });
  const lineStart = mk(outside ? a1 - ARROW_L - 2 : a1, line);
  const lineEnd = mk(outside ? a2 + ARROW_L + 2 : a2, line);
  const tp: Pt = horiz ? [mid, line - TEXT_LIFT] : [line - TEXT_LIFT, mid];
  const color = hover ? HOVER : INK;

  return (
    <g stroke="currentColor" color={color} strokeWidth={thin} data-dim={d.id}>
      {exts}
      <line x1={lineStart[0]} y1={lineStart[1]} x2={lineEnd[0]} y2={lineEnd[1]} />
      <Arrow tip={mk(a1, line)} dir={unit(outside ? 1 : -1)} />
      <Arrow tip={mk(a2, line)} dir={unit(outside ? -1 : 1)} />
      <text
        x={tp[0]}
        y={tp[1]}
        transform={horiz ? undefined : `rotate(-90 ${tp[0]} ${tp[1]})`}
        textAnchor="middle"
        fill={color}
        {...textProps}
        {...props}
      >
        {label}
      </text>
    </g>
  );
}

function Circle({
  d,
  ov,
  g,
  thin,
  snapOn,
  autoLen,
}: {
  d: CircleDim;
  ov: DimOverride;
  g: Geo;
  thin: number;
  snapOn: boolean;
  autoLen?: number;
}) {
  const setOverride = useStore((s) => s.setOverride);
  const { C, R, u, E, K, s, sx, tw, textX, textY } = circleGeom(d, ov, g, autoLen);
  const { hover, props } = useLabelInteraction(d.id, ([x, y]) => {
    // The text sits on the shoulder: map the pointer back to the leader end K.
    const kx = x - sx * (tw / 2 + 1);
    const dv: Pt = [kx - C[0], y + TEXT_LIFT - C[1]];
    const dist = Math.hypot(dv[0], dv[1]);
    if (dist < 1e-6) return;
    let ang = (Math.atan2(d.inside ? dv[1] : -dv[1], d.inside ? -dv[0] : dv[0]) * 180) / Math.PI;
    if (snapOn) ang = Math.round(ang / 15) * 15;
    const len = d.inside ? R + dist : Math.max(3, dist - R);
    setOverride(d.id, { leader_angle_deg: ang, leader_len_mm: snap(len, snapOn) });
  });
  const shoulderEnd: Pt = [K[0] + sx * (tw + 2), K[1]];
  const color = hover ? HOVER : INK;

  return (
    <g stroke="currentColor" color={color} strokeWidth={thin} data-dim={d.id}>
      <line x1={E[0]} y1={E[1]} x2={K[0]} y2={K[1]} />
      <line x1={K[0]} y1={K[1]} x2={shoulderEnd[0]} y2={shoulderEnd[1]} />
      <Arrow tip={E} dir={[-s * u[0], -s * u[1]]} />
      <text x={textX} y={textY} textAnchor="middle" fill={color} {...textProps} {...props}>
        {d.label_text}
      </text>
    </g>
  );
}

// ---------------------------------------------------------------------------
type Annotated = { dimensions: Dimension[] };

function geoFor(part: Part, layout: SheetLayout, d: Dimension): Geo | null {
  const placement = layout.placements.find((p) => p.view === d.view);
  const v = part.views[d.view];
  return placement && v ? { placement, w: v.width, h: v.height } : null;
}

/** Collision pass: linear labels are fixed; each callout's leader grows until its
 *  label clears every label placed before it (user-dragged callouts are left alone). */
function autoLeaderLengths(
  annotations: Annotated,
  overrides: Record<string, DimOverride>,
  part: Part,
  layout: SheetLayout,
): Record<string, number> {
  const geoOf = (d: Dimension) => geoFor(part, layout, d);
  const boxes: Box[] = [];
  const autoLen: Record<string, number> = {};
  for (const d of annotations.dimensions) {
    const g = geoOf(d);
    if (g && d.type === "linear") boxes.push(linearGeom(d, overrides[d.id] ?? {}, g).box);
  }
  for (const d of annotations.dimensions) {
    const g = geoOf(d);
    if (!g || d.type === "linear") continue;
    const ov = overrides[d.id] ?? {};
    let len = d.leader_len_mm;
    let box = circleGeom(d, ov, g, len).box;
    if (ov.leader_len_mm === undefined) {
      for (let i = 0; i < 8 && boxes.some((b) => overlaps(b, box)); i++) {
        len += 5;
        box = circleGeom(d, ov, g, len).box;
      }
      autoLen[d.id] = len;
    }
    boxes.push(box);
  }
  return autoLen;
}

/** Final dimensions exactly as drawn (drag overrides + auto leader lengths) — what export receives. */
export function resolveDimensions(
  annotations: Annotated,
  overrides: Record<string, DimOverride>,
  part: Part,
  layout: SheetLayout,
): Dimension[] {
  const autoLen = autoLeaderLengths(annotations, overrides, part, layout);
  return annotations.dimensions.map((d) => {
    const ov = overrides[d.id] ?? {};
    if (d.type === "linear") {
      return { ...d, offset_mm: ov.offset_mm ?? d.offset_mm, text_shift_mm: ov.text_shift_mm ?? d.text_shift_mm };
    }
    return {
      ...d,
      leader_angle_deg: ov.leader_angle_deg ?? d.leader_angle_deg,
      leader_len_mm: ov.leader_len_mm ?? autoLen[d.id] ?? d.leader_len_mm,
    };
  });
}

export function DimensionLayer({ part, layout, thin }: { part: Part; layout: SheetLayout; thin: number }) {
  const annotations = useStore((s) => s.annotations);
  const overrides = useStore((s) => s.overrides);
  const snapOn = useStore((s) => s.display.grid);
  if (!annotations) return null;
  const geoOf = (d: Dimension) => geoFor(part, layout, d);
  const autoLen = autoLeaderLengths(annotations, overrides, part, layout);

  return (
    <g data-layer="dimensions">
      {annotations.dimensions.map((d) => {
        const g = geoOf(d);
        if (!g) return null;
        const ov = overrides[d.id] ?? {};
        return d.type === "linear" ? (
          <Linear key={d.id} d={d} ov={ov} g={g} thin={thin} snapOn={snapOn} />
        ) : (
          <Circle key={d.id} d={d} ov={ov} g={g} thin={thin} snapOn={snapOn} autoLen={autoLen[d.id]} />
        );
      })}
    </g>
  );
}

export function NotesBlock({ layout, notes }: { layout: SheetLayout; notes: string[] }) {
  if (!notes.length) return null;
  const tb = layout.title_block;
  const lineH = 4.5;
  const top = tb.y - 4 - notes.length * lineH;
  return (
    <g fontFamily={FONT} fill={INK}>
      <text x={tb.x} y={top} fontSize={3.5} fontWeight={700}>
        NOTES
      </text>
      {notes.map((n, i) => (
        <text key={i} x={tb.x} y={top + (i + 1) * lineH} fontSize={3}>
          {`${i + 1}. ${n}`}
        </text>
      ))}
    </g>
  );
}
