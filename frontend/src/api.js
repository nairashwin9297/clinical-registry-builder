// The app talks to one of two backends with the same interface:
// - httpApi: the Django REST API (local dev, Docker). Paths are relative, so the same build works behind
//   Vite's dev proxy and when Django serves the app.
// - staticApi: exported JSON + localStorage, for the GitHub Pages demo (built with VITE_STATIC=true).
import { staticApi } from "./staticApi.js";

async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, options);
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await res.json() : await res.text();
  if (!res.ok) {
    const err = new Error(body?.detail || `Request failed (${res.status})`);
    err.details = body?.errors || [];
    throw err;
  }
  return body;
}

const EXPORT_URLS = {
  registry: "/api/export/registry.csv",
  redcap: "/api/export/redcap.csv",
  redcapDictionary: "/api/export/redcap-dictionary.csv",
};

const httpApi = {
  config: () => request("/config/"),
  notes: () => request("/notes/"),
  note: (id) => request(`/notes/${id}/`),
  reviewQueue: (includeReviewed) => request(`/review-queue/${includeReviewed ? "?include_reviewed=true" : ""}`),
  metrics: () => request("/metrics/"),
  submitReview: (extractionId, correctedValue) =>
    request(`/extractions/${extractionId}/review/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ corrected_value: correctedValue }),
    }),
  liveStatus: () => request("/live/status/"),
  uploadNotes: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/notes/upload/", { method: "POST", body: form });
  },
  runExtraction: (noteId) => request(`/notes/${noteId}/extract/`, { method: "POST" }),
  // The server builds the CSV (with corrections applied) and the browser downloads it.
  download: async (kind) => { window.location.href = EXPORT_URLS[kind]; },
};

export const api = import.meta.env.VITE_STATIC === "true" ? staticApi : httpApi;
