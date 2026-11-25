import type { Part, Sample, SheetConfig, SheetLayout } from "./types";

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
  samples: () => request<Sample[]>("/api/samples"),
  loadSample: (id: string) => request<Part>(`/api/samples/${id}/load`, { method: "POST" }),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<Part>("/api/parts", { method: "POST", body });
  },
  layout: (partId: string, cfg: SheetConfig, signal?: AbortSignal) =>
    request<SheetLayout>(`/api/parts/${partId}/layout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
      signal,
    }),
  meshUrl: (part: Part) => `${API_URL}${part.mesh_url}`,
};
