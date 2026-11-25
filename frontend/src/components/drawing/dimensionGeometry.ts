// Pure paper-space dimension geometry (no React, no store) — shared by the SVG
// renderer (Dimensions.tsx) and the export request (store.exportDrawing).
// Keep in sync with backend/app/export/builder.py.
import type { CircleDim, DimOverride, Dimension, LinearDim, Part, SheetLayout, ViewPlacement } from "../../api/types";

export const FONT = "Arial, Helvetica, sans-serif";
export const TEXT = 3.5;
export const ARROW_L = 3;
export const ARROW_W = 0.5; // half width
export const EXT_GAP = 1; // gap between object and extension line
export const EXT_OVER = 2; // extension beyond the dimension line
export const TEXT_LIFT = 1.2; // text baseline clearance above the dimension line
export const SNAP = 2.5;
export const HOVER = "#0284c7";

export type Pt = [number, number];
export type Box = [number, number, number, number]; // x0, y0, x1, y1

export const fmtValue = (v: number) => String(Number(v.toFixed(2)));
export const textWidth = (s: string) => s.length * TEXT * 0.56;
export const snap = (v: number, on: boolean) => (on ? Math.round(v / SNAP) * SNAP : v);
export const overlaps = (a: Box, b: Box) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];

export interface Geo {
  placement: ViewPlacement;
  w: number;
  h: number;
}

export const toPaper = (g: Geo, x: number, y: number): Pt => [
  g.placement.x_offset + x * g.placement.scale,
  g.placement.y_offset + y * g.placement.scale,
];

// ---------------------------------------------------------------------------
// Pure geometry (shared by rendering, dragging and the collision pass)
// ---------------------------------------------------------------------------
export function linearGeom(d: LinearDim, ov: DimOverride, g: Geo) {
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

export function circleGeom(d: CircleDim, ov: DimOverride, g: Geo, autoLen?: number) {
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
export type Annotated = { dimensions: Dimension[] };

export function geoFor(part: Part, layout: SheetLayout, d: Dimension): Geo | null {
  const placement = layout.placements.find((p) => p.view === d.view);
  const v = part.views[d.view];
  return placement && v ? { placement, w: v.width, h: v.height } : null;
}

/** Collision pass: linear labels are fixed; each callout's leader grows until its
 *  label clears every label placed before it (user-dragged callouts are left alone). */
export function autoLeaderLengths(
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
