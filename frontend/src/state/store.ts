import { create } from "zustand";
import { api, ApiError } from "../api/client";
import type {
  AnnotationSet,
  DimensionMode,
  DimOverride,
  OrthoView,
  Part,
  Sample,
  SheetConfig,
  SheetLayout,
} from "../api/types";

export const MAX_ORTHO_VIEWS = 3;

export type { DimensionMode };
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

  init: () => Promise<void>;
  loadSample: (id: string) => Promise<void>;
  uploadFile: (file: File) => Promise<void>;
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

    init: async () => {
      if (initStarted) return; // StrictMode double-invokes effects in dev
      initStarted = true;
      // Free-tier hosts cold-start (and the CAD kernel import takes a few seconds),
      // so retry quietly before surfacing an error.
      for (let attempt = 0; attempt < 8; attempt++) {
        try {
          set({ samples: await api.samples() });
          return;
        } catch (e) {
          if (attempt === 7) get().toast(e instanceof ApiError ? e.message : String(e), "error");
          await new Promise((r) => setTimeout(r, 1500 + attempt * 1000));
        }
      }
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
