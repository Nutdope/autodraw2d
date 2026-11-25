import { useEffect } from "react";
import { api, ApiError } from "../api/client";
import { useStore } from "./store";

/** Re-computes the sheet layout on the backend whenever the part or sheet config changes.
 *  The layout endpoint is pure Python (~1 ms), so this feels instant; stale requests are aborted. */
export function useLayoutSync() {
  const part = useStore((s) => s.part);
  const sheet = useStore((s) => s.sheet);
  const setLayout = useStore((s) => s.setLayout);

  useEffect(() => {
    if (!part) return;
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      api
        .layout(part.part_id, sheet, ctrl.signal)
        .then((l) => setLayout(l))
        .catch((e) => {
          if (ctrl.signal.aborted) return;
          setLayout(null, e instanceof ApiError ? e.message : String(e));
        });
    }, 60);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [part, sheet, setLayout]);
}
