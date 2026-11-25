import type { SectionOverlay, SheetLayout } from "../../api/types";
import { useStore } from "../../state/store";
import { CENTER_DASH, INK } from "./lineStyles";

const FONT = "Arial, Helvetica, sans-serif";
const LABEL_GAP = 8; // keep in sync with backend/app/layout/section_overlay.py

interface Props {
  section: SectionOverlay;
  layout: SheetLayout;
  thick: number;
  thin: number;
}

/** Hatching, cutting-plane line, arrows and "SECTION A-A" — all in paper mm, computed by
 *  the backend so the screen and the DXF / PDF / SVG exports draw exactly the same thing. */
export function SectionLayer({ section: s, layout, thick, thin }: Props) {
  const dims = useStore((st) => st.annotations?.dimensions);
  const overrides = useStore((st) => st.overrides);
  const place = layout.placements.find((p) => p.view === s.view);

  // Drop the label below any dimensions placed under the sectioned view (mirrors label_y()).
  let labelY = s.label.y;
  if (place && dims) {
    let lowest = 0;
    for (const d of dims) {
      if (d.view !== s.view || d.type !== "linear" || d.orientation !== "horizontal" || d.offset_from !== "edge") continue;
      const off = overrides[d.id]?.offset_mm ?? d.offset_mm;
      if (off < 0) lowest = Math.max(lowest, -off);
    }
    if (lowest) labelY = Math.max(labelY, place.rect.y + place.rect.h + lowest + LABEL_GAP);
  }

  const hatch = s.hatch.map(([x1, y1, x2, y2]) => `M${x1} ${y1}L${x2} ${y2}`).join("");
  return (
    <g data-layer="section" stroke={INK} fill="none" strokeLinecap="butt">
      {hatch && <path d={hatch} strokeWidth={thin} />}
      {s.lines.map((l, i) => (
        <line
          key={i}
          x1={l.x1}
          y1={l.y1}
          x2={l.x2}
          y2={l.y2}
          strokeWidth={l.style === "thick" ? thick : thin}
          strokeDasharray={l.style === "chain" ? CENTER_DASH.join(" ") : undefined}
        />
      ))}
      {s.arrows.map((pts, i) => (
        <polygon key={i} points={pts.map((p) => p.join(",")).join(" ")} fill={INK} stroke="none" />
      ))}
      <g fill={INK} stroke="none" fontFamily={FONT} fontWeight="bold">
        {s.texts.map((t, i) => (
          <text key={i} x={t.x} y={t.y} fontSize={t.size} textAnchor={t.anchor}>
            {t.text}
          </text>
        ))}
        <text x={s.label.x} y={labelY} fontSize={s.label.size} textAnchor={s.label.anchor}>
          {s.label.text}
        </text>
      </g>
    </g>
  );
}
