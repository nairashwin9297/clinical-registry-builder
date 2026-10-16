// Small fetch wrapper. Paths are relative, so the same build works behind Vite's dev proxy and
// when Django serves the app.

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

export const api = {
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
};

export const exportUrls = {
  registry: "/api/export/registry.csv",
  redcap: "/api/export/redcap.csv",
  redcapDictionary: "/api/export/redcap-dictionary.csv",
};
