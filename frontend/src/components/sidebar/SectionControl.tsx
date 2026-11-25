import { useEffect, useState } from "react";
import type { OrthoView } from "../../api/types";
import { useStore } from "../../state/store";
import { Field, Select } from "../ui/controls";

const LABEL: Record<OrthoView, string> = {
  front: "Front",
  top: "Top",
  bottom: "Bottom",
  left: "Left",
  right: "Right",
  rear: "Rear",
};

/** Full section (ISO 128-44): pick the view to draw cut, and where the plane sits. */
export function SectionControl() {
  const sheet = useStore((s) => s.sheet);
  const setSheet = useStore((s) => s.setSheet);
  const section = useStore((s) => s.layout?.section ?? null);
  const active = sheet.section_view;

  // Slider moves locally; the (server-side) cut is requested once dragging pauses.
  const [depth, setDepth] = useState<number | null>(null);
  useEffect(() => setDepth(null), [section?.depth, active]);
  useEffect(() => {
    if (depth === null) return;
    const t = setTimeout(() => setSheet({ section_depth: depth }), 250);
    return () => clearTimeout(t);
  }, [depth, setSheet]);

  const max = section?.depth_max ?? 0;
  const shown = depth ?? section?.depth ?? 0;
  const step = max > 200 ? 1 : 0.5;

  return (
    <div className="space-y-2.5">
      <Field label="Section view" hint="Draws the view cut by a plane, with hatching and an A–A cutting line">
        <Select<string>
          value={active ?? "off"}
          onChange={(v) =>
            setSheet({ section_view: v === "off" ? null : (v as OrthoView), section_depth: null })
          }
          options={[
            { value: "off", label: "Off" },
            ...sheet.ortho_views.map((v) => ({ value: v, label: `${LABEL[v]} view in section A–A` })),
          ]}
        />
      </Field>
      {active && section && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400">Cutting plane depth</span>
            <span className="tabular-nums text-slate-200">
              {shown.toFixed(1)} mm
              {section.auto && depth === null && <span className="ml-1 text-slate-500">(auto)</span>}
            </span>
          </div>
          <input
            type="range"
            min={step}
            max={Math.max(step, max - step)}
            step={step}
            value={shown}
            onChange={(e) => setDepth(Number(e.target.value))}
            className="w-full accent-sky-500"
            aria-label="Cutting plane depth"
          />
          <div className="flex items-center justify-between text-[11px] text-slate-500">
            <span>measured from the {LABEL[active].toLowerCase()} face</span>
            {!section.auto && (
              <button
                type="button"
                onClick={() => setSheet({ section_depth: null })}
                className="text-sky-300 hover:text-sky-200"
              >
                Auto (through holes)
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
