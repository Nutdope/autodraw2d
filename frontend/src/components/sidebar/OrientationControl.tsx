import type { ModelOrientation, UpAxis } from "../../api/types";
import { useStore } from "../../state/store";

const AXES: UpAxis[] = ["+Z", "+Y", "+X", "-Z", "-Y", "-X"];

/** Up axis + 90° turn for parts exported from Y-up CAD systems (SolidWorks, Inventor, Creo…). */
export function OrientationControl({ orientation }: { orientation: ModelOrientation }) {
  const reorient = useStore((s) => s.reorient);
  const busy = useStore((s) => !!s.loading);
  const { up, turn, auto, source_system } = orientation;
  const nextTurn = ((turn + 90) % 360) as ModelOrientation["turn"];

  return (
    <div className="space-y-1.5 rounded-md border border-slate-800 bg-slate-900/60 p-2.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">Orientation</span>
        <span className="text-slate-500" title={source_system ?? undefined}>
          {auto ? `auto-detected ${up} up` : `${up} up (manual)`}
          {turn ? ` · turned ${turn}°` : ""}
        </span>
      </div>
      <div className="flex gap-1.5">
        <select
          aria-label="Model up axis"
          disabled={busy}
          value={auto ? "auto" : up}
          onChange={(e) => reorient(e.target.value as UpAxis | "auto", turn)}
          className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 outline-none focus:border-sky-500 disabled:opacity-50"
        >
          <option value="auto">Auto ({source_system ? source_system.split(" / ").pop() : "header"})</option>
          {AXES.map((a) => (
            <option key={a} value={a}>
              {a} is up
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={busy}
          onClick={() => reorient(auto ? "auto" : up, nextTurn)}
          title="Turn the part 90° about its up axis (changes which side is the front view)"
          className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-200 transition hover:border-slate-500 disabled:opacity-50"
        >
          ⟳ Turn 90°
        </button>
      </div>
      <p className="text-[11px] leading-snug text-slate-500">
        Lying on its side? Pick the axis that should point up (SolidWorks / Inventor / Creo export Y-up).
      </p>
    </div>
  );
}
