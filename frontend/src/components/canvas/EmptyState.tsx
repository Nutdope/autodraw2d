import { useStore } from "../../state/store";

export function EmptyState() {
  const samples = useStore((s) => s.samples);
  const loadSample = useStore((s) => s.loadSample);
  return (
    <div className="absolute inset-0 grid place-items-center p-6" onPointerDown={(e) => e.stopPropagation()}>
      <div className="max-w-md rounded-2xl border border-slate-800 bg-slate-900/80 p-8 text-center shadow-2xl">
        <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-xl bg-sky-500/15 text-sky-300">
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M12 3 3 7.5v9L12 21l9-4.5v-9z" />
            <path d="M3 7.5 12 12l9-4.5M12 12v9" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-slate-100">Drop a STEP file to start</h2>
        <p className="mt-2 text-sm text-slate-400">
          AutoDraw computes exact hidden-line views, hole callouts and an ISO/ANSI sheet layout from your 3D
          model. No file handy? Try a sample part:
        </p>
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
