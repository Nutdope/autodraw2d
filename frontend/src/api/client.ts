import type { AnnotateRequest, AnnotationSet, ModelOrientation, Part, Sample, SheetConfig, SheetLayout, UpAxis } from "./types";

export const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, `Cannot reach the backend at ${API_URL}`);
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) msg = body.detail.map((d: { msg: string }) => d.msg).join("; ");
      else if (body.error) msg = body.error;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // per-attempt timeout so a hung request during a cold start doesn't stall the retry loop
  samples: () => request<Sample[]>("/api/samples", { signal: AbortSignal.timeout(60_000) }),
  loadSample: (id: string) => request<Part>(`/api/samples/${id}/load`, { method: "POST" }),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<Part>("/api/parts", { method: "POST", body });
  },
  orient: (partId: string, up: UpAxis | "auto", turn: ModelOrientation["turn"]) =>
    request<Part>(`/api/parts/${partId}/orient`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ up, turn }),
    }),
  layout: (partId: string, cfg: SheetConfig, signal?: AbortSignal) =>
    request<SheetLayout>(`/api/parts/${partId}/layout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
      signal,
    }),
  annotate: (partId: string, req: AnnotateRequest) =>
    request<AnnotationSet>(`/api/parts/${partId}/annotate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  exportSheet: async (partId: string, body: unknown): Promise<{ blob: Blob; filename: string }> => {
    let res: Response;
    try {
      res = await fetch(`${API_URL}/api/parts/${partId}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch {
      throw new ApiError(0, `Cannot reach the backend at ${API_URL}`);
    }
    if (!res.ok) {
      let msg = `Export failed (${res.status})`;
      try {
        const j = await res.json();
        if (typeof j.detail === "string") msg = j.detail;
        else if (j.error) msg = j.error;
      } catch {
        /* binary or empty body */
      }
      throw new ApiError(res.status, msg);
    }
    const cd = res.headers.get("Content-Disposition") ?? "";
    const filename = /filename="([^"]+)"/.exec(cd)?.[1] ?? "drawing";
    return { blob: await res.blob(), filename };
  },
  meshUrl: (part: Part) => `${API_URL}${part.mesh_url}`,
};
