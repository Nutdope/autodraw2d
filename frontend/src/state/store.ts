import { create } from "zustand";
import { api, ApiError } from "../api/client";
import { resolveDimensions } from "../components/drawing/dimensionGeometry";
import type {
  AnnotationSet,
  DimensionMode,
  ModelOrientation,
  UpAxis,
  DimOverride,
  OrthoView,
  Part,
  Sample,
  SheetConfig,
  SheetLayout,
} from "../api/types";

export const MAX_ORTHO_VIEWS = 3;

export type { DimensionMode };
export type ExportFormat = "dxf" | "pdf" | "svg";
export type Tolerance = "ISO 2768-f" | "ISO 2768-m" | "ISO 2768-c" | "custom";

export interface TitleBlockFields {
  partName: string;
  drawingNumber: string;
  revision: string;
  material: string;
  roughness: string;
  drawnBy: string;
  date: string;
}

export interface DisplayOptions {
  hidden: boolean;
  centerlines: boolean;
  tangent: boolean;
  grid: boolean;
}

export interface Toast {
  id: number;
  kind: "info" | "error" | "success";
  text: string;
}

interface State {
  samples: Sample[];
  /** connecting: first contact / free-tier host waking up · offline: gave up, user can retry */
  backend: "connecting" | "ready" | "offline";
  part: Part | null;
  loading: string | null; // human-readable status while a part loads
  layout: SheetLayout | null;
  layoutError: string | null;
  sheet: SheetConfig;
  display: DisplayOptions;
  dimensionMode: DimensionMode;
  tolerance: Tolerance;
  customTolerance: string;
  title: TitleBlockFields;
  toasts: Toast[];
  annotations: AnnotationSet | null;
  aiPending: boolean;
  overrides: Record<string, DimOverride>;
  /** Phone layout: settings drawer visibility (always shown on desktop). */
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;

  init: (force?: boolean) => Promise<void>;
  loadSample: (id: string) => Promise<void>;
  uploadFile: (file: File) => Promise<void>;
  reorient: (up: UpAxis | "auto", turn: ModelOrientation["turn"]) => Promise<void>;
  setSheet: (patch: Partial<SheetConfig>) => void;
  toggleOrtho: (view: OrthoView) => void;
  setDisplay: (patch: Partial<DisplayOptions>) => void;
  setTitle: (patch: Partial<TitleBlockFields>) => void;
  setDimensionMode: (m: DimensionMode) => void;
  setTolerance: (t: Tolerance, custom?: string) => void;
  setLayout: (l: SheetLayout | null, err?: string | null) => void;
  runAnnotate: (useAi: boolean) => Promise<void>;
  autoDimensionAI: () => Promise<void>;
  setOverride: (id: string, patch: DimOverride) => void;
  exporting: ExportFormat | null;
  exportDrawing: (format: ExportFormat) => Promise<void>;
  resetOverride: (id?: string) => void;
  toast: (text: string, kind?: Toast["kind"]) => void;
  dismissToast: (id: number) => void;
}

let toastSeq = 0;
let annotateSeq = 0;

const sameViews = (a: string[], b: string[]) => [...a].sort().join() === [...b].sort().join();

const FALLBACK_MSG: Record<string, string> = {
  rate_limited: "AI limit reached for now — used the built-in auto-dimensioner instead.",
  daily_cap: "Today's shared AI budget is used up — used the built-in auto-dimensioner instead.",
  ai_not_configured: "AI isn't configured on this server — used the built-in auto-dimensioner.",
  ai_quota: "Gemini free-tier quota is exhausted — used the built-in auto-dimensioner.",
  ai_error: "AI service unavailable right now — used the built-in auto-dimensioner.",
  sample_not_precomputed:
    "No pre-computed AI layout for this sample + view combination — showing rule-based dimensions (upload your own part for live AI).",
};
let initStarted = false;
const WAKE_TIMEOUT_MS = 180_000;
const today = () => new Date().toISOString().slice(0, 10);

function drawingNumberFor(name: string) {
  const slug = name.toUpperCase().replace(/[^A-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 14);
  return `AD-${slug || "PART"}-001`;
}

export const useStore = create<State>((set, get) => {
  const applyPart = (part: Part) =>
    set((s) => ({
      part,
      loading: null,
      layout: null,
      annotations: null,
      overrides: {},
      title: {
        ...s.title,
        partName: part.name,
        drawingNumber: drawingNumberFor(part.name),
        material: part.default_material ?? s.title.material,
      },
    }));

  const fail = (e: unknown) => {
    set({ loading: null });
    get().toast(e instanceof ApiError ? e.message : String(e), "error");
  };

  return {
    samples: [],
    backend: "connecting",
    part: null,
    loading: null,
    layout: null,
    layoutError: null,
    sheet: {
      page_format: "A3",
      orientation: "landscape",
      standard: "ISO",
      ortho_views: ["front", "top", "left"],
      show_isometric: true,
      scale: "auto",
    },
    display: { hidden: true, centerlines: true, tangent: false, grid: false },
    dimensionMode: "key",
    tolerance: "ISO 2768-m",
    customTolerance: "",
    title: {
      partName: "",
      drawingNumber: "",
      revision: "A",
      material: "S235JR",
      roughness: "Ra 3.2",
      drawnBy: "",
      date: today(),
    },
    toasts: [],
    annotations: null,
    aiPending: false,
    overrides: {},
    exporting: null,
    sidebarOpen: false,
    setSidebarOpen: (open) => set({ sidebarOpen: open }),

    exportDrawing: async (format) => {
      const { part, layout, sheet, display, title, tolerance, customTolerance, annotations, overrides } = get();
      if (!part || !layout) return;
      set({ exporting: format });
      try {
        const { blob, filename } = await api.exportSheet(part.part_id, {
          format,
          sheet,
          display: { hidden: display.hidden, centerlines: display.centerlines, tangent: display.tangent },
          title,
          tolerance: toleranceText(tolerance, customTolerance),
          dimensions: annotations ? resolveDimensions(annotations, overrides, part, layout) : [],
          notes: annotations?.notes ?? [],
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
        get().toast(`Exported ${filename}`, "success");
      } catch (e) {
        get().toast(e instanceof ApiError ? e.message : String(e), "error");
      } finally {
        set({ exporting: null });
      }
    },

    init: async (force = false) => {
      if (initStarted && !force) return; // StrictMode double-invokes effects in dev
      initStarted = true;
      set({ backend: "connecting" });
      // A free-tier backend (Render) sleeps after 15 min idle; waking it and loading the
      // CAD kernel can take a minute or more. Keep retrying quietly for up to ~3 minutes.
      const deadline = Date.now() + WAKE_TIMEOUT_MS;
      for (let attempt = 0; Date.now() < deadline; attempt++) {
        try {
          set({ samples: await api.samples(), backend: "ready" });
          return;
        } catch {
          await new Promise((r) => setTimeout(r, Math.min(1500 * 1.4 ** attempt, 8000)));
        }
      }
      set({ backend: "offline" });
      get().toast("The drawing server didn't respond. Please retry in a moment.", "error");
    },

    loadSample: async (id) => {
      const name = get().samples.find((s) => s.id === id)?.name ?? id;
      set({ loading: `Loading ${name}…` });
      try {
        applyPart(await api.loadSample(id));
      } catch (e) {
        fail(e);
      }
    },

    uploadFile: async (file) => {
      if (!/\.(step|stp)$/i.test(file.name)) {
        get().toast("Please choose a .step or .stp file", "error");
        return;
      }
      set({ loading: `Analysing ${file.name}… (hidden-line projection can take a few seconds)` });
      try {
        applyPart(await api.upload(file));
        get().toast(`${file.name} loaded`, "success");
      } catch (e) {
        fail(e);
      }
    },

    reorient: async (up, turn) => {
      const part = get().part;
      if (!part) return;
      set({ loading: "Re-orienting the part… (new hidden-line views)" });
      try {
        applyPart(await api.orient(part.part_id, up, turn));
      } catch (e) {
        fail(e);
      }
    },

    setSheet: (patch) => set((s) => ({ sheet: { ...s.sheet, ...patch } })),

    toggleOrtho: (view) => {
      if (view === "front") return; // base view, always on
      const cur = get().sheet.ortho_views;
      if (cur.includes(view)) {
        get().setSheet({ ortho_views: cur.filter((v) => v !== view) });
      } else if (cur.length >= MAX_ORTHO_VIEWS) {
        get().toast(`Maximum ${MAX_ORTHO_VIEWS} orthographic views — untick one first`, "info");
      } else {
        get().setSheet({ ortho_views: [...cur, view] });
      }
    },

    setDisplay: (patch) => set((s) => ({ display: { ...s.display, ...patch } })),
    setTitle: (patch) => set((s) => ({ title: { ...s.title, ...patch } })),
    setDimensionMode: (dimensionMode) => set({ dimensionMode }),
    setTolerance: (tolerance, custom) =>
      set((s) => ({ tolerance, customTolerance: custom ?? s.customTolerance })),
    setLayout: (layout, err = null) => set({ layout, layoutError: err }),

    runAnnotate: async (useAi) => {
      const { part, dimensionMode, sheet, tolerance, customTolerance } = get();
      if (!part) return;
      if (!useAi && get().aiPending) return; // never clobber an in-flight AI run
      if (dimensionMode === "none" && !useAi) {
        set({ annotations: null, overrides: {} });
        return;
      }
      const seq = ++annotateSeq;
      if (useAi) set({ aiPending: true });
      try {
        const res = await api.annotate(part.part_id, {
          mode: useAi ? "full" : dimensionMode,
          ortho_views: sheet.ortho_views,
          use_ai: useAi,
          tolerance: toleranceText(tolerance, customTolerance),
        });
        const now = get();
        if (useAi) set({ aiPending: false });
        if (now.part?.part_id !== part.part_id) return;
        if (!useAi && seq !== annotateSeq) return; // a newer request superseded this one
        if (!sameViews(res.views, now.sheet.ortho_views)) {
          get().runAnnotate(false); // views changed while the AI was thinking
          return;
        }
        set({ annotations: res, overrides: {} });
        if (useAi) {
          if (res.source === "ai")
            get().toast(`AI placed ${res.dimensions.length} dimensions (${res.model})`, "success");
          else if (res.source !== "deterministic")
            get().toast(`Loaded cached AI dimensions (${res.dimensions.length})`, "success");
          else get().toast(FALLBACK_MSG[res.fallback_reason ?? ""] ?? "Used the built-in auto-dimensioner.", "info");
        }
      } catch (e) {
        if (useAi) set({ aiPending: false });
        get().toast(e instanceof ApiError ? e.message : String(e), "error");
      }
    },

    autoDimensionAI: async () => {
      set({ dimensionMode: "full" });
      await get().runAnnotate(true);
    },

    setOverride: (id, patch) =>
      set((s) => ({ overrides: { ...s.overrides, [id]: { ...s.overrides[id], ...patch } } })),
    resetOverride: (id) =>
      set((s) => {
        if (!id) return { overrides: {} };
        const next = { ...s.overrides };
        delete next[id];
        return { overrides: next };
      }),

    toast: (text, kind = "info") => {
      const id = ++toastSeq;
      set((s) => ({ toasts: [...s.toasts, { id, kind, text }] }));
      setTimeout(() => get().dismissToast(id), kind === "error" ? 7000 : 4000);
    },
    dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  };
});

export function toleranceText(t: Tolerance, custom: string) {
  return t === "custom" ? custom || "—" : t;
}
