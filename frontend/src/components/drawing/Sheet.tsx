import { forwardRef } from "react";
import type { Part, SheetLayout } from "../../api/types";
import { toleranceText, useStore } from "../../state/store";
import { DimensionLayer, NotesBlock } from "./Dimensions";
import { INK, lineWeights } from "./lineStyles";
import { TitleBlock } from "./TitleBlock";
import { SectionLayer } from "./SectionLayer";
import { ViewGroup } from "./ViewGroup";

const FONT = "Arial, Helvetica, sans-serif";
const NO_NOTES: string[] = []; // stable reference: zustand selectors must not allocate

interface Props {
  part: Part;
  layout: SheetLayout;
  widthPx: number;
}

/** The full drawing sheet as one SVG in paper millimetres (viewBox = page size). */
export const Sheet = forwardRef<SVGSVGElement, Props>(function Sheet({ part, layout, widthPx }, ref) {
  const display = useStore((s) => s.display);
  const title = useStore((s) => s.title);
  const tol = useStore((s) => toleranceText(s.tolerance, s.customTolerance));
  const notes = useStore((s) => s.annotations?.notes ?? NO_NOTES);

  const W = layout.page_width;
  const H = layout.page_height;
  const { thick, thin } = lineWeights(layout.page_format);
  const fr = layout.frame;
  const z = layout.zones;
  const right = fr.x + fr.w;
  const bottom = fr.y + fr.h;

  return (
    <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`0 0 ${W} ${H}`}
      width={widthPx}
      height={(widthPx * H) / W}
      style={{ display: "block" }}
      shapeRendering="geometricPrecision"
    >
      <rect width={W} height={H} fill="#fff" />

      {display.grid && (
        <g stroke="#bfdbfe" strokeWidth={0.12} data-screen-only>
          {Array.from({ length: Math.floor(fr.w / 10) + 1 }, (_, i) => (
            <line key={`gx${i}`} x1={fr.x + i * 10} y1={fr.y} x2={fr.x + i * 10} y2={bottom} />
          ))}
          {Array.from({ length: Math.floor(fr.h / 10) + 1 }, (_, i) => (
            <line key={`gy${i}`} x1={fr.x} y1={fr.y + i * 10} x2={right} y2={fr.y + i * 10} />
          ))}
        </g>
      )}

      {/* ISO 5457 frame + zone references */}
      <rect x={fr.x} y={fr.y} width={fr.w} height={fr.h} fill="none" stroke={INK} strokeWidth={thick} />
      <g stroke={INK} strokeWidth={thin}>
        {z.col_edges.slice(1, -1).map((x) => (
          <g key={`cx${x}`}>
            <line x1={x} y1={fr.y} x2={x} y2={fr.y - 5} />
            <line x1={x} y1={bottom} x2={x} y2={bottom + 5} />
          </g>
        ))}
        {z.row_edges.slice(1, -1).map((y) => (
          <g key={`ry${y}`}>
            <line x1={fr.x} y1={y} x2={fr.x - 5} y2={y} />
            <line x1={right} y1={y} x2={right + 5} y2={y} />
          </g>
        ))}
        {/* centring marks */}
        <line x1={W / 2} y1={0} x2={W / 2} y2={fr.y} strokeWidth={thick} />
        <line x1={W / 2} y1={bottom} x2={W / 2} y2={H} strokeWidth={thick} />
        <line x1={0} y1={H / 2} x2={fr.x} y2={H / 2} strokeWidth={thick} />
        <line x1={right} y1={H / 2} x2={W} y2={H / 2} strokeWidth={thick} />
      </g>
      <g fontSize={3} fill={INK} fontFamily={FONT} textAnchor="middle">
        {z.columns.map((c, i) => {
          const cx = (z.col_edges[i] + z.col_edges[i + 1]) / 2;
          return (
            <g key={`c${c}`}>
              <text x={cx} y={fr.y - 2.6}>{c}</text>
              <text x={cx} y={bottom + 6.4}>{c}</text>
            </g>
          );
        })}
        {z.rows.map((r, i) => {
          const cy = (z.row_edges[i] + z.row_edges[i + 1]) / 2 + 1.1;
          return (
            <g key={`r${r}`}>
              <text x={fr.x - 10} y={cy}>{r}</text>
              <text x={right + 5} y={cy}>{r}</text>
            </g>
          );
        })}
      </g>

      {/* views */}
      {layout.placements.map((p) => {
        let v = part.views[p.view];
        if (!v) return null;
        const sec = layout.section;
        if (sec && sec.view === p.view) {
          // full section: cut geometry in the same frame, no hidden lines
          v = {
            ...v,
            visible: { svg_path: sec.visible_svg },
            tangent: { svg_path: sec.tangent_svg },
            hidden: { svg_path: "" },
            tangent_hidden: { svg_path: "" },
            center_marks: sec.center_marks,
            centerlines: sec.centerlines,
          };
        }
        return <ViewGroup key={p.view} view={v} placement={p} display={display} thick={thick} thin={thin} />;
      })}

      {/* per-view scale note when it differs from the sheet scale */}
      {layout.placements
        .filter((p) => p.scale !== layout.scale)
        .map((p) => (
          <text
            key={`lbl-${p.view}`}
            x={p.rect.x + p.rect.w / 2}
            y={p.rect.y + p.rect.h + 7}
            fontSize={3.5}
            textAnchor="middle"
            fill={INK}
            fontFamily={FONT}
          >
            {`${p.view.toUpperCase()} (${p.scale_label})`}
          </text>
        ))}

      {layout.section && <SectionLayer section={layout.section} layout={layout} thick={thick} thin={thin} />}

      <DimensionLayer part={part} layout={layout} thin={thin} />
      <NotesBlock layout={layout} notes={notes} />

      <TitleBlock rect={layout.title_block} layout={layout} fields={title} tolerance={tol} thick={thick} thin={thin} />
    </svg>
  );
});
