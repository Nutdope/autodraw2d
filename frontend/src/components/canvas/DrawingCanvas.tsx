import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useStore } from "../../state/store";
import { Sheet } from "../drawing/Sheet";
import { EmptyState } from "./EmptyState";

interface Viewport {
  x: number; // px offset of the sheet's top-left inside the canvas
  y: number;
  k: number; // px per paper-mm
}

const MIN_K = 0.3;
const MAX_K = 40;

export function DrawingCanvas() {
  const part = useStore((s) => s.part);
  const layout = useStore((s) => s.layout);
  const layoutError = useStore((s) => s.layoutError);
  const loading = useStore((s) => s.loading);
  const display = useStore((s) => s.display);
  const setDisplay = useStore((s) => s.setDisplay);
  const uploadFile = useStore((s) => s.uploadFile);

  const boxRef = useRef<HTMLDivElement>(null);
  const [vp, setVp] = useState<Viewport>({ x: 0, y: 0, k: 1 });
  const [dragOver, setDragOver] = useState(false);
  const drag = useRef<{ px: number; py: number; x: number; y: number } | null>(null);

  const pageW = layout?.page_width ?? 0;
  const pageH = layout?.page_height ?? 0;

  const fit = useCallback(() => {
    const el = boxRef.current;
    if (!el || !pageW) return;
    const { width, height } = el.getBoundingClientRect();
    const k = Math.min((width - 64) / pageW, (height - 64) / pageH);
    setVp({ k, x: (width - pageW * k) / 2, y: (height - pageH * k) / 2 });
  }, [pageW, pageH]);

  // Refit whenever the paper size / orientation changes (not on every layout update).
  useLayoutEffect(() => {
    fit();
  }, [fit, part?.part_id]);

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => fit());
    ro.observe(el);
    return () => ro.disconnect();
  }, [fit]);

  // Wheel zoom around the cursor (non-passive so we can preventDefault page scroll).
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const mx = e.clientX - r.left;
      const my = e.clientY - r.top;
      setVp((v) => {
        const k = Math.min(MAX_K, Math.max(MIN_K, v.k * Math.exp(-e.deltaY * 0.0015)));
        const f = k / v.k;
        return { k, x: mx - (mx - v.x) * f, y: my - (my - v.y) * f };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const zoomBy = (factor: number) => {
    const el = boxRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    setVp((v) => {
      const k = Math.min(MAX_K, Math.max(MIN_K, v.k * factor));
      const f = k / v.k;
      return { k, x: width / 2 - (width / 2 - v.x) * f, y: height / 2 - (height / 2 - v.y) * f };
    });
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0 && e.button !== 1) return;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    drag.current = { px: e.clientX, py: e.clientY, x: vp.x, y: vp.y };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    setVp((v) => ({ ...v, x: d.x + e.clientX - d.px, y: d.y + e.clientY - d.py }));
  };
  const onPointerUp = () => {
    drag.current = null;
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) uploadFile(f);
  };

  return (
    <div
      ref={boxRef}
      className={`relative h-full w-full overflow-hidden select-none bg-[radial-gradient(circle,#1e293b_1px,transparent_1px)] [background-size:18px_18px] cursor-grab active:cursor-grabbing`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={fit}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
    >
      {part && layout ? (
        <div
          className="absolute shadow-[0_10px_40px_rgba(0,0,0,0.55),0_2px_6px_rgba(0,0,0,0.4)]"
          style={{ left: vp.x, top: vp.y }}
        >
          <Sheet part={part} layout={layout} widthPx={pageW * vp.k} />
        </div>
      ) : (
        !loading && <EmptyState />
      )}

      {/* status banners */}
      <div className="pointer-events-none absolute left-1/2 top-3 flex -translate-x-1/2 flex-col items-center gap-2">
        {layout && !layout.fits && (
          <Banner tone="warn">{layout.warnings[0] ?? "Views do not fit this sheet."}</Banner>
        )}
        {layout?.fits &&
          layout.warnings.map((w) => (
            <Banner key={w} tone="info">
              {w}
            </Banner>
          ))}
        {layoutError && <Banner tone="warn">{layoutError}</Banner>}
      </div>

      {loading && (
        <div className="absolute inset-0 grid place-items-center bg-slate-950/60 backdrop-blur-[2px]">
          <div className="flex items-center gap-3 rounded-lg border border-slate-700 bg-slate-900 px-5 py-3 text-sm">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
            {loading}
          </div>
        </div>
      )}

      {dragOver && (
        <div className="pointer-events-none absolute inset-3 grid place-items-center rounded-xl border-2 border-dashed border-sky-400 bg-sky-400/10 text-sky-200">
          Drop .step file to load
        </div>
      )}

      {/* zoom controls */}
      {layout && (
        <div
          className="absolute bottom-4 right-4 flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-900/90 p-1 text-xs shadow-lg"
          onPointerDown={(e) => e.stopPropagation()}
          onDoubleClick={(e) => e.stopPropagation()}
        >
          <CtlButton onClick={() => zoomBy(1 / 1.25)} title="Zoom out">−</CtlButton>
          <span className="w-12 text-center tabular-nums text-slate-400">
            {Math.round((vp.k / 3.7795) * 100)}%
          </span>
          <CtlButton onClick={() => zoomBy(1.25)} title="Zoom in">+</CtlButton>
          <CtlButton onClick={fit} title="Fit sheet (double-click canvas)">Fit</CtlButton>
          <div className="mx-1 h-5 w-px bg-slate-700" />
          <CtlButton
            onClick={() => setDisplay({ grid: !display.grid })}
            title="Toggle 10 mm grid (snap for draggable dimensions arrives with auto-dimensioning)"
            active={display.grid}
          >
            Grid
          </CtlButton>
        </div>
      )}
    </div>
  );
}

function CtlButton({
  children,
  onClick,
  title,
  active,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`h-7 min-w-7 rounded px-2 font-medium transition ${
        active ? "bg-sky-500/20 text-sky-300" : "text-slate-300 hover:bg-slate-800"
      }`}
    >
      {children}
    </button>
  );
}

function Banner({ tone, children }: { tone: "warn" | "info"; children: React.ReactNode }) {
  return (
    <div
      className={`max-w-xl rounded-md border px-3 py-1.5 text-xs shadow ${
        tone === "warn"
          ? "border-amber-500/40 bg-amber-950/90 text-amber-200"
          : "border-slate-600 bg-slate-900/90 text-slate-300"
      }`}
    >
      {children}
    </div>
  );
}
