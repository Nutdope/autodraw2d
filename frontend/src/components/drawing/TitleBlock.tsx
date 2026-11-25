import type { Rect, SheetLayout } from "../../api/types";
import type { TitleBlockFields } from "../../state/store";
import { INK } from "./lineStyles";
import { ProjectionSymbol } from "./ProjectionSymbol";

interface Props {
  rect: Rect;
  layout: SheetLayout;
  fields: TitleBlockFields;
  tolerance: string;
  thick: number;
  thin: number;
}

const LABEL = 1.8;
const VALUE = 3.2;
const FONT = "Arial, Helvetica, sans-serif";

/** Shrink font so `text` fits in `width` mm (Arial ≈ 0.55 em average advance). */
function fitSize(text: string, width: number, size: number) {
  const est = text.length * size * 0.56;
  return est > width ? Math.max(1.6, (width / est) * size) : size;
}

function Cell({ x, y, w, h, label, value, size = VALUE }: {
  x: number; y: number; w: number; h: number; label: string; value: string; size?: number;
}) {
  const v = value || "—";
  return (
    <g>
      <text x={x + 1.2} y={y + 2.6} fontSize={LABEL} fill="#64748b" fontFamily={FONT}>
        {label}
      </text>
      <text x={x + 1.5} y={y + h - 2.2} fontSize={fitSize(v, w - 3, size)} fill={INK} fontFamily={FONT}>
        {v}
      </text>
    </g>
  );
}

/** ISO 7200-style title block, 180 mm wide, anchored bottom-right of the frame. */
export function TitleBlock({ rect, layout, fields, tolerance, thick, thin }: Props) {
  const { x, y, w, h } = rect;
  const r = h / 4;
  const L = Math.min(108, w * 0.6); // left block width
  const X = (v: number) => x + v;
  const Y = (row: number) => y + row * r;

  const lines: [number, number, number, number][] = [
    // horizontal row lines (left block all rows; right block below title)
    [X(0), Y(1), X(L), Y(1)],
    [X(0), Y(2), X(w), Y(2)],
    [X(0), Y(3), X(w), Y(3)],
    // vertical: left/right split
    [X(L), Y(0), X(L), Y(4)],
    // left block internal
    [X(L / 2), Y(0), X(L / 2), Y(1)],
    [X(L * 0.667), Y(1), X(L * 0.667), Y(3)],
    [X(L * 0.37), Y(3), X(L * 0.37), Y(4)],
    [X(L * 0.685), Y(3), X(L * 0.685), Y(4)],
    // right block: drawing no | rev
    [X(w - 20), Y(2), X(w - 20), Y(4)],
  ];

  return (
    <g>
      <rect x={x} y={y} width={w} height={h} fill="#fff" stroke={INK} strokeWidth={thick} />
      <g stroke={INK} strokeWidth={thin}>
        {lines.map(([x1, y1, x2, y2], i) => (
          <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} />
        ))}
      </g>

      <Cell x={X(0)} y={Y(0)} w={L / 2} h={r} label="DRAWN BY" value={fields.drawnBy} />
      <Cell x={X(L / 2)} y={Y(0)} w={L / 2} h={r} label="DATE" value={fields.date} />
      <Cell x={X(0)} y={Y(1)} w={L * 0.667} h={r} label="MATERIAL" value={fields.material} />
      <Cell x={X(L * 0.667)} y={Y(1)} w={L * 0.333} h={r} label="SURFACE" value={fields.roughness} />
      <Cell x={X(0)} y={Y(2)} w={L * 0.667} h={r} label="GENERAL TOLERANCES" value={tolerance} />
      <Cell x={X(L * 0.667)} y={Y(2)} w={L * 0.333} h={r} label="UNITS" value="mm" />

      {/* projection symbol cell */}
      <text x={X(1.2)} y={Y(3) + 2.6} fontSize={LABEL} fill="#64748b" fontFamily={FONT}>
        {layout.projection_method === "first_angle" ? "PROJECTION (ISO E)" : "PROJECTION (ISO A)"}
      </text>
      <g transform={`translate(${X(L * 0.185 - 26 * 0.35)} ${Y(3) + 3.6}) scale(0.7)`}>
        <ProjectionSymbol x={0} y={0} method={layout.projection_method} thin={thin / 0.7} thick={thin / 0.7} />
      </g>

      <Cell x={X(L * 0.37)} y={Y(3)} w={L * 0.315} h={r} label="SCALE" value={layout.scale_label} size={4} />
      <Cell x={X(L * 0.685)} y={Y(3)} w={L * 0.315} h={r} label="SHEET" value={`${layout.page_format} · 1/1`} />

      {/* right block */}
      <text x={X(L + 1.2)} y={Y(0) + 2.6} fontSize={LABEL} fill="#64748b" fontFamily={FONT}>
        TITLE
      </text>
      <text
        x={X(L + (w - L) / 2)}
        y={Y(1) + 2}
        fontSize={fitSize(fields.partName || "UNTITLED", w - L - 4, 5.5)}
        textAnchor="middle"
        fontWeight={700}
        fill={INK}
        fontFamily={FONT}
      >
        {(fields.partName || "UNTITLED").toUpperCase()}
      </text>
      <Cell x={X(L)} y={Y(2)} w={w - L - 20} h={r} label="DRAWING NO." value={fields.drawingNumber} />
      <Cell x={X(w - 20)} y={Y(2)} w={20} h={r} label="REV" value={fields.revision} size={4} />
      <text x={X(L + 1.5)} y={Y(4) - 2.4} fontSize={3} fill={INK} fontFamily={FONT} fontWeight={700}>
        AutoDraw 2D
      </text>
      <text x={X(w - 18.5)} y={Y(4) - 2.4} fontSize={2} fill="#64748b" fontFamily={FONT}>
        {layout.standard}
      </text>
    </g>
  );
}
