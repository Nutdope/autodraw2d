import { useEffect } from "react";
import { useStore } from "./store";

/** Re-dimension when the part, dimensioning mode, active views or tolerance change.
 *  Never spends AI quota: "full" mode returns cached/pre-computed AI results when they
 *  exist, otherwise the deterministic set (the AI only runs from the toolbar button). */
export function useAnnotationSync() {
  const part = useStore((s) => s.part);
  const mode = useStore((s) => s.dimensionMode);
  const views = useStore((s) => s.sheet.ortho_views);
  const tolerance = useStore((s) => s.tolerance);
  const custom = useStore((s) => s.customTolerance);
  const runAnnotate = useStore((s) => s.runAnnotate);

  useEffect(() => {
    if (!part) return;
    const t = setTimeout(() => runAnnotate(false), 120);
    return () => clearTimeout(t);
  }, [part, mode, views, tolerance, custom, runAnnotate]);
}
