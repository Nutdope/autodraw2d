import { useStore } from "../../state/store";

export function EmptyState() {
  const samples = useStore((s) => s.samples);
  const loadSample = useStore((s) => s.loadSample);
  const backend = useStore((s) => s.backend);
  const retry = useStore((s) => s.init);
  return (
    <div className="absolute inset-0 grid place-items-center overflow-y-auto p-3 sm:p-6" onPointerDown={(e) => e.stopPropagation()}>
      <div className="max-w-md rounded-2xl border border-slate-800 bg-slate-900/80 p-5 text-center sm:p-8 shadow-2xl">
        <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-xl bg-sky-500/15 text-sky-300">
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M12 3 3 7.5v9L12 21l9-4.5v-9z" />
            <path d="M3 7.5 12 12l9-4.5M12 12v9" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-slate-100">
          <span className="hidden md:inline">Drop a STEP file to start</span>
          <span className="md:hidden">Upload a STEP file to start</span>
        </h2>
        <p className="mt-2 text-sm text-slate-400">
          AutoDraw computes exact hidden-line views, hole callouts and an ISO/ANSI sheet layout from your 3D
          model. No file handy? Try a sample part:
        </p>
        {backend === "connecting" && samples.length === 0 && (
          <div className="mt-5 flex items-center justify-center gap-3 rounded-lg border border-slate-800 bg-slate-950/60 px-4 py-3 text-sm text-slate-300">
            <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
            <span className="text-left">
              Waking up the drawing server…
              <span className="block text-xs text-slate-500">
                The free host sleeps when idle — this can take up to a minute.
              </span>
            </span>
          </div>
        )}
        {backend === "offline" && samples.length === 0 && (
          <div className="mt-5 space-y-3 text-sm text-slate-400">
            <p>The drawing server isn't responding right now.</p>
            <button
              type="button"
              onClick={() => retry(true)}
              className="rounded-lg bg-sky-500 px-4 py-2 font-medium text-slate-950 transition hover:bg-sky-400"
            >
              Retry
            </button>
          </div>
        )}
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          {samples.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => loadSample(s.id)}
              title={s.description}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 transition hover:border-sky-500 hover:text-white"
            >
              {s.name}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
