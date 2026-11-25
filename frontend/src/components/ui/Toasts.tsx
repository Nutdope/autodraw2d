import { useStore } from "../../state/store";

export function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const dismiss = useStore((s) => s.dismissToast);
  return (
    <div className="pointer-events-none fixed bottom-16 left-1/2 z-50 flex w-[calc(100%-1.5rem)] -translate-x-1/2 sm:bottom-4 sm:w-auto flex-col items-center gap-2">
      {toasts.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => dismiss(t.id)}
          className={`pointer-events-auto max-w-md rounded-lg border px-4 py-2 text-sm shadow-xl backdrop-blur ${
            t.kind === "error"
              ? "border-red-500/40 bg-red-950/90 text-red-200"
              : t.kind === "success"
                ? "border-emerald-500/40 bg-emerald-950/90 text-emerald-200"
                : "border-slate-600 bg-slate-900/90 text-slate-200"
          }`}
        >
          {t.text}
        </button>
      ))}
    </div>
  );
}
