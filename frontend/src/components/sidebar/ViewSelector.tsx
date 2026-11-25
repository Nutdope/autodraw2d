import type { OrthoView } from "../../api/types";
import { MAX_ORTHO_VIEWS, useStore } from "../../state/store";

type Cell = OrthoView | "iso" | null;

// Where each view lands on the sheet, so the selector doubles as a layout preview.
const THIRD_ANGLE: Cell[][] = [
  [null, "top", null, "iso"],
  ["left", "front", "right", "rear"],
  [null, "bottom", null, null],
];
const FIRST_ANGLE: Cell[][] = [
  [null, "bottom", null, "iso"],
  ["right", "front", "left", "rear"],
  [null, "top", null, null],
];

const LABEL: Record<Exclude<Cell, null>, string> = {
  front: "Front",
  top: "Top",
  bottom: "Bottom",
  left: "Left",
  right: "Right",
  rear: "Rear",
  iso: "Iso",
};

export function ViewSelector() {
  const sheet = useStore((s) => s.sheet);
  const toggleOrtho = useStore((s) => s.toggleOrtho);
  const setSheet = useStore((s) => s.setSheet);
  const grid = sheet.standard === "ANSI" ? THIRD_ANGLE : FIRST_ANGLE;
  const full = sheet.ortho_views.length >= MAX_ORTHO_VIEWS;

  return (
    <div>
      <div className="grid grid-cols-4 gap-1.5">
        {grid.flat().map((cell, i) => {
          if (!cell) return <div key={i} />;
          const isIso = cell === "iso";
          const active = isIso ? sheet.show_isometric : sheet.ortho_views.includes(cell);
          const locked = cell === "front";
          const blocked = !isIso && !active && full;
          return (
            <button
              key={i}
              type="button"
              disabled={locked}
              onClick={() => (isIso ? setSheet({ show_isometric: !sheet.show_isometric }) : toggleOrtho(cell))}
              title={
                locked
                  ? "Front is the base view"
                  : blocked
                    ? `Max ${MAX_ORTHO_VIEWS} orthographic views`
                    : isIso
                      ? "Isometric view (max 1)"
                      : `${LABEL[cell]} view`
              }
              className={`relative h-10 rounded-md border text-xs font-medium transition ${
                active
                  ? "border-sky-500/70 bg-sky-500/15 text-sky-200"
                  : blocked
                    ? "border-slate-800 bg-slate-900/40 text-slate-600"
                    : "border-slate-700 bg-slate-900 text-slate-400 hover:border-slate-500 hover:text-slate-200"
              } ${isIso ? "border-dashed" : ""} ${locked ? "cursor-default" : ""}`}
            >
              {LABEL[cell]}
              {locked && <span className="absolute right-1 top-0.5 text-[8px] text-sky-400">BASE</span>}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-slate-500">
        {sheet.ortho_views.length}/{MAX_ORTHO_VIEWS} orthographic · {sheet.show_isometric ? 1 : 0}/1 isometric ·{" "}
        {sheet.standard === "ANSI" ? "third-angle" : "first-angle"} arrangement
      </p>
    </div>
  );
}
