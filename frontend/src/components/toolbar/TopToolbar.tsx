import { useEffect, useRef, useState } from "react";
import { useStore } from "../../state/store";

const PORTFOLIO_URL = import.meta.env.VITE_PORTFOLIO_URL as string | undefined;

const EXPORTS = [
  { ext: "DXF", title: "CAD Drawing (.DXF)", hint: "Editable in SolidWorks, AutoCAD, Fusion, Inventor" },
  { ext: "PDF", title: "Print / Share (.PDF)", hint: "Vector sheet ready for printing or review" },
  { ext: "SVG", title: "Web / Vector (.SVG)", hint: "Scalable vector for docs & illustrations" },
];

export function TopToolbar() {
  const samples = useStore((s) => s.samples);
  const part = useStore((s) => s.part);
  const loading = useStore((s) => s.loading);
  const loadSample = useStore((s) => s.loadSample);
  const uploadFile = useStore((s) => s.uploadFile);
  const toast = useStore((s) => s.toast);
  const autoDimensionAI = useStore((s) => s.autoDimensionAI);
  const aiPending = useStore((s) => s.aiPending);
  const fileRef = useRef<HTMLInputElement>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const exportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!exportOpen) return;
    const close = (e: MouseEvent) => {
      if (!exportRef.current?.contains(e.target as Node)) setExportOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [exportOpen]);

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 md:gap-4 border-b border-slate-800 bg-slate-950 px-4">
      {/* left: brand */}
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex items-center gap-2">
          <svg viewBox="0 0 32 32" className="h-7 w-7">
            <rect width="32" height="32" rx="7" fill="#0c4a6e" />
            <path d="M8 24V8h10l6 6v10z" fill="none" stroke="#38bdf8" strokeWidth="2.2" strokeLinejoin="round" />
            <path d="M11 19h10M11 15h6" stroke="#7dd3fc" strokeWidth="1.4" />
          </svg>
          <span className="whitespace-nowrap font-semibold tracking-tight text-slate-100">
            AutoDraw <span className="text-sky-400">2D</span>
          </span>
        </div>
        {PORTFOLIO_URL && (
          <a href={PORTFOLIO_URL} className="hidden text-xs text-slate-500 transition hover:text-slate-300 md:inline">
            ← Back to Portfolio
          </a>
        )}
      </div>

      {/* center: file + samples */}
      <div className="flex flex-1 items-center justify-center gap-2">
        <input
          ref={fileRef}
          type="file"
          accept=".step,.stp"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) uploadFile(f);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          disabled={!!loading}
          onClick={() => fileRef.current?.click()}
          className="flex items-center gap-2 rounded-md bg-sky-500 px-3 py-1.5 text-sm font-medium text-slate-950 transition hover:bg-sky-400 disabled:opacity-50"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M10 13V3M6 7l4-4 4 4M3 13v3h14v-3" />
          </svg>
          <span className="whitespace-nowrap">
            Upload<span className="hidden sm:inline"> .STEP</span>
          </span>
        </button>
        <span className="hidden text-xs text-slate-600 lg:inline">or try</span>
        {samples.map((s) => (
          <button
            key={s.id}
            type="button"
            disabled={!!loading}
            title={s.description}
            onClick={() => loadSample(s.id)}
            className={`hidden rounded-md border px-3 py-1.5 text-sm transition disabled:opacity-50 lg:block ${
              part?.sample_id === s.id
                ? "border-sky-500/60 bg-sky-500/10 text-sky-200"
                : "border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white"
            }`}
          >
            {s.name}
          </button>
        ))}
      </div>

      {/* right: AI + export */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={!part || aiPending}
          onClick={() => autoDimensionAI()}
          title="Let Gemini lay out a complete dimension set (geometry is always measured by the CAD kernel)"
          className="flex items-center gap-1.5 rounded-md border border-violet-500/50 bg-violet-500/10 px-3 py-1.5 text-sm text-violet-200 transition hover:bg-violet-500/20 disabled:opacity-40"
        >
          {aiPending ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-violet-300 border-t-transparent" />
          ) : (
            <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
              <path d="M10 1l1.8 4.7L16.5 7.5l-4.7 1.8L10 14l-1.8-4.7L3.5 7.5l4.7-1.8zM15.5 12l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z" />
            </svg>
          )}
          <span className="hidden whitespace-nowrap md:inline">
            {aiPending ? "Dimensioning…" : "Auto-Dimension (AI)"}
          </span>
          <span className="md:hidden">AI</span>
        </button>
        <div ref={exportRef} className="relative">
          <button
            type="button"
            disabled={!part}
            onClick={() => setExportOpen((o) => !o)}
            className="flex items-center gap-1.5 rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 transition hover:border-slate-500 disabled:opacity-40"
          >
            Export
            <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="currentColor">
              <path d="M5 7l5 6 5-6z" />
            </svg>
          </button>
          {exportOpen && (
            <div className="absolute right-0 top-full z-30 mt-1.5 w-72 overflow-hidden rounded-lg border border-slate-700 bg-slate-900 shadow-2xl">
              {EXPORTS.map((x) => (
                <button
                  key={x.ext}
                  type="button"
                  onClick={() => {
                    setExportOpen(false);
                    toast(`${x.ext} export is coming in the next update.`, "info");
                  }}
                  className="flex w-full items-start gap-3 px-3 py-2.5 text-left transition hover:bg-slate-800"
                >
                  <span className="mt-0.5 rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-sky-300">
                    {x.ext}
                  </span>
                  <span>
                    <span className="block text-sm text-slate-100">{x.title}</span>
                    <span className="block text-xs text-slate-500">{x.hint}</span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
