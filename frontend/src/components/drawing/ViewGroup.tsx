import type { ViewData, ViewPlacement } from "../../api/types";
import type { DisplayOptions } from "../../state/store";
import { CENTER_DASH, CENTER_OVERSHOOT, HIDDEN_DASH, INK, dash } from "./lineStyles";

interface Props {
  view: ViewData;
  placement: ViewPlacement;
  display: DisplayOptions;
  thick: number;
  thin: number;
}

/** One projected view, placed with translate(offset) scale(s). Geometry is in model mm
 *  (view-local, y-down), so stroke widths / dashes are divided by the view scale. */
export function ViewGroup({ view, placement: p, display, thick, thin }: Props) {
  const s = p.scale;
  const ext = CENTER_OVERSHOOT / s;
  return (
    <g
      transform={`translate(${p.x_offset} ${p.y_offset}) scale(${s})`}
      fill="none"
      stroke={INK}
      strokeLinecap="round"
      strokeLinejoin="round"
      data-view={view.name}
    >
      {display.tangent && view.tangent.svg_path && (
        <path d={view.tangent.svg_path} strokeWidth={thin / s} stroke="#475569" />
      )}
      {display.hidden && view.hidden.svg_path && (
        <path d={view.hidden.svg_path} strokeWidth={thin / s} strokeDasharray={dash(HIDDEN_DASH, s)} />
      )}
      {display.hidden && display.tangent && view.tangent_hidden.svg_path && (
        <path
          d={view.tangent_hidden.svg_path}
          strokeWidth={thin / s}
          strokeDasharray={dash(HIDDEN_DASH, s)}
          stroke="#475569"
        />
      )}
      <path d={view.visible.svg_path} strokeWidth={thick / s} />

      {display.centerlines && !view.is_isometric && (
        <g strokeWidth={thin / s} strokeDasharray={dash(CENTER_DASH, s)} strokeLinecap="butt">
          {view.centerlines.map((c, i) => {
            const [x0, y0] = c.p0;
            const [x1, y1] = c.p1;
            const len = Math.hypot(x1 - x0, y1 - y0) || 1;
            const ux = (x1 - x0) / len;
            const uy = (y1 - y0) / len;
            return (
              <line key={`c${i}`} x1={x0 - ux * ext} y1={y0 - uy * ext} x2={x1 + ux * ext} y2={y1 + uy * ext} />
            );
          })}
          {view.center_marks.map((m, i) => {
            const arm = m.r + ext;
            return (
              <g key={`m${i}`}>
                <line x1={m.cx - arm} y1={m.cy} x2={m.cx + arm} y2={m.cy} />
                <line x1={m.cx} y1={m.cy - arm} x2={m.cx} y2={m.cy + arm} />
              </g>
            );
          })}
        </g>
      )}
    </g>
  );
}
