import { lazy, Suspense } from "react";
import type { DrawingStandard, Orientation, PageFormat } from "../../api/types";
import { useStore, type DimensionMode, type Tolerance } from "../../state/store";
import { Field, Section, Segmented, Select, TextInput, Toggle } from "../ui/controls";
import { ViewSelector } from "./ViewSelector";

// three.js is ~700 kB: load it only once a part is shown.
const PartPreview3D = lazy(() => import("../preview/PartPreview3D").then((m) => ({ default: m.PartPreview3D })));

const SCALES = ["auto", "5:1", "2:1", "1:1", "1:2", "1:5", "1:10", "1:20"];
const MATERIALS = ["S235JR", "S355J2", "C45", "42CrMo4", "1.4301 (304)", "Al 6061-T6", "Al 7075-T6", "PA6", "POM-C"];
const ROUGHNESS = ["Ra 0.8", "Ra 1.6", "Ra 3.2", "Ra 6.3", "Ra 12.5"];

const fmt = (v: number, d = 1) => v.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });

function PartInfo() {
  const part = useStore((s) => s.part);
  const layout = useStore((s) => s.layout);
  if (!part) {
    return <p className="text-sm text-slate-500">No part loaded. Upload a .step file or pick a sample.</p>;
  }
  const g = part.geometry;
  return (
    <>
      <Suspense fallback={<div className="h-48 animate-pulse rounded-lg border border-slate-800 bg-slate-900" />}>
        <PartPreview3D part={part} />
      </Suspense>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        <dt className="text-slate-500">Size</dt>
        <dd className="tabular-nums text-slate-200">
          {fmt(g.size[0])} × {fmt(g.size[1])} × {fmt(g.size[2])} mm
        </dd>
        <dt className="text-slate-500">Volume</dt>
        <dd className="tabular-nums text-slate-200">{fmt(g.volume / 1000, 2)} cm³</dd>
        <dt className="text-slate-500">Faces</dt>
        <dd className="tabular-nums text-slate-200">
          {g.face_count} · {g.solid_count} solid{g.solid_count === 1 ? "" : "s"}
        </dd>
        {layout && (
          <>
            <dt className="text-slate-500">Scale</dt>
            <dd className="text-slate-200">
              {layout.scale_label} {layout.auto_scale && <span className="text-slate-500">(auto-fit)</span>}
            </dd>
          </>
        )}
      </dl>
      {g.feature_groups.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs text-slate-500">Detected features</div>
          <div className="flex flex-wrap gap-1.5">
            {g.feature_groups.map((f) => (
              <span
                key={f.label + f.feature_ids[0]}
                title={`${f.kind.replace("_", " ")} · ${f.feature_ids.join(", ")}`}
                className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${
                  f.kind === "hole"
                    ? "bg-sky-500/15 text-sky-300"
                    : f.kind === "boss"
                      ? "bg-emerald-500/15 text-emerald-300"
                      : "bg-slate-700/60 text-slate-300"
                }`}
              >
                {f.label}
              </span>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

const SOURCE_LABEL: Record<string, { text: string; cls: string }> = {
  ai: { text: "AI · Gemini", cls: "bg-violet-500/15 text-violet-300" },
  ai_cached: { text: "AI · cached", cls: "bg-violet-500/15 text-violet-300" },
  precomputed: { text: "AI · pre-computed", cls: "bg-violet-500/15 text-violet-300" },
  deterministic: { text: "Rule-based", cls: "bg-emerald-500/15 text-emerald-300" },
};

function AnnotationStatus() {
  const ann = useStore((s) => s.annotations);
  const overrides = useStore((s) => s.overrides);
  const resetOverride = useStore((s) => s.resetOverride);
  const aiPending = useStore((s) => s.aiPending);
  const autoDimensionAI = useStore((s) => s.autoDimensionAI);
  if (aiPending) return <p className="text-xs text-violet-300">Gemini is laying out dimensions…</p>;
  if (!ann) return null;
  const src = SOURCE_LABEL[ann.source];
  const moved = Object.keys(overrides).length;
  return (
    <div className="space-y-2 rounded-md border border-slate-800 bg-slate-900/60 p-2.5 text-xs">
      <div className="flex items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 font-medium ${src.cls}`}>{src.text}</span>
        <span className="text-slate-400">{ann.dimensions.length} dimensions</span>
        {ann.rejected > 0 && (
          <span className="text-slate-500" title="AI primitives that failed geometric validation were dropped">
            · {ann.rejected} rejected
          </span>
        )}
      </div>
      {ann.mode === "full" && ann.source === "deterministic" && (
        <button type="button" onClick={() => autoDimensionAI()} className="text-violet-300 hover:text-violet-200">
          ✦ Run AI layout for these views
        </button>
      )}
      {moved > 0 && (
        <button type="button" onClick={() => resetOverride()} className="block text-sky-300 hover:text-sky-200">
          Reset {moved} moved label{moved === 1 ? "" : "s"}
        </button>
      )}
    </div>
  );
}

export function Sidebar() {
  const sheet = useStore((s) => s.sheet);
  const setSheet = useStore((s) => s.setSheet);
  const display = useStore((s) => s.display);
  const setDisplay = useStore((s) => s.setDisplay);
  const title = useStore((s) => s.title);
  const setTitle = useStore((s) => s.setTitle);
  const dimensionMode = useStore((s) => s.dimensionMode);
  const setDimensionMode = useStore((s) => s.setDimensionMode);
  const tolerance = useStore((s) => s.tolerance);
  const customTolerance = useStore((s) => s.customTolerance);
  const setTolerance = useStore((s) => s.setTolerance);
  const layout = useStore((s) => s.layout);

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col overflow-y-auto border-r border-slate-800 bg-slate-950">
      <Section title="Part">
        <PartInfo />
      </Section>

      <Section title="Sheet Setup">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Page format">
            <Select<PageFormat>
              value={sheet.page_format}
              onChange={(v) => setSheet({ page_format: v })}
              options={[
                { value: "A4", label: "A4 · 210×297" },
                { value: "A3", label: "A3 · 297×420" },
                { value: "A2", label: "A2 · 420×594" },
                { value: "A1", label: "A1 · 594×841" },
              ]}
            />
          </Field>
          <Field label="Scale">
            <Select
              value={sheet.scale}
              onChange={(v) => setSheet({ scale: v })}
              options={SCALES.map((s) => ({
                value: s,
                label: s === "auto" ? `Auto-fit${layout?.auto_scale ? ` (${layout.scale_label})` : ""}` : s,
              }))}
            />
          </Field>
        </div>
        <Field label="Orientation">
          <Segmented<Orientation>
            value={sheet.orientation}
            onChange={(v) => setSheet({ orientation: v })}
            options={[
              { value: "landscape", label: "Landscape" },
              { value: "portrait", label: "Portrait" },
            ]}
          />
        </Field>
        <Field label="Drawing standard">
          <Segmented<DrawingStandard>
            value={sheet.standard}
            onChange={(v) => setSheet({ standard: v })}
            options={[
              { value: "ISO", label: "ISO · 1st angle", title: "First-angle projection, metric" },
              { value: "ANSI", label: "ANSI · 3rd angle", title: "Third-angle projection" },
            ]}
          />
        </Field>
      </Section>

      <Section title="View Selection">
        <ViewSelector />
        <div className="space-y-2.5 pt-1">
          <Toggle
            checked={display.hidden}
            onChange={(v) => setDisplay({ hidden: v })}
            label="Show hidden lines"
            hint="Dashed, ISO 128 type 02.1"
          />
          <Toggle
            checked={display.centerlines}
            onChange={(v) => setDisplay({ centerlines: v })}
            label="Centerlines & center marks"
            hint="Chain lines on holes and shaft axes"
          />
          <Toggle
            checked={display.tangent}
            onChange={(v) => setDisplay({ tangent: v })}
            label="Show tangent edges"
            hint="Thin lines where fillets blend into faces"
          />
        </div>
      </Section>

      <Section title="Annotations">
        <Field label="Dimensioning mode" hint="Drag any dimension text to move it · double-click to reset">
          <Select<DimensionMode>
            value={dimensionMode}
            onChange={setDimensionMode}
            options={[
              { value: "none", label: "None (views only)" },
              { value: "overall", label: "Overall only (L × W × H)" },
              { value: "key", label: "Key features" },
              { value: "full", label: "Full engineering (AI)" },
            ]}
          />
        </Field>
        <AnnotationStatus />
        <Field label="General tolerance">
          <Select<Tolerance>
            value={tolerance}
            onChange={(v) => setTolerance(v)}
            options={[
              { value: "ISO 2768-f", label: "ISO 2768-f (fine)" },
              { value: "ISO 2768-m", label: "ISO 2768-m (medium)" },
              { value: "ISO 2768-c", label: "ISO 2768-c (coarse)" },
              { value: "custom", label: "Custom…" },
            ]}
          />
        </Field>
        {tolerance === "custom" && (
          <TextInput
            value={customTolerance}
            onChange={(v) => setTolerance("custom", v)}
            placeholder="e.g. ±0.1 unless stated"
          />
        )}
      </Section>

      <Section title="Title Block">
        <Field label="Part name">
          <TextInput value={title.partName} onChange={(v) => setTitle({ partName: v })} />
        </Field>
        <div className="grid grid-cols-[1fr_4.5rem] gap-3">
          <Field label="Drawing number">
            <TextInput value={title.drawingNumber} onChange={(v) => setTitle({ drawingNumber: v })} />
          </Field>
          <Field label="Rev">
            <TextInput value={title.revision} onChange={(v) => setTitle({ revision: v })} />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Material">
            <TextInput value={title.material} onChange={(v) => setTitle({ material: v })} list="materials" />
          </Field>
          <Field label="Surface">
            <TextInput value={title.roughness} onChange={(v) => setTitle({ roughness: v })} list="roughness" />
          </Field>
          <Field label="Drawn by">
            <TextInput value={title.drawnBy} onChange={(v) => setTitle({ drawnBy: v })} placeholder="Your name" />
          </Field>
          <Field label="Date">
            <input
              type="date"
              value={title.date}
              onChange={(e) => setTitle({ date: e.target.value })}
              className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100 outline-none [color-scheme:dark] focus:border-sky-500"
            />
          </Field>
        </div>
        <p className="text-[11px] text-slate-500">
          Scale and projection symbol are synced automatically from the sheet setup.
        </p>
        <datalist id="materials">
          {MATERIALS.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        <datalist id="roughness">
          {ROUGHNESS.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
      </Section>
    </aside>
  );
}
