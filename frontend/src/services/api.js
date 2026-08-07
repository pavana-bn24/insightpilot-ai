const BASE = import.meta.env.VITE_API_BASE || "";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.message || detail;
    } catch (_) {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  health: () => request("/api/health"),

  listDatasets: () => request("/api/datasets"),

  uploadDataset: async (file) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/datasets/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail || detail;
      } catch (_) {}
      throw new Error(detail);
    }
    return res.json();
  },

  getDataset: (id) => request(`/api/datasets/${id}`),

  analyze: (dataset_id, question, hints) =>
    request("/api/analyze", {
      method: "POST",
      body: JSON.stringify({ dataset_id, question, hints: hints || {} }),
    }),

  history: () => request("/api/history"),

  conversation: () => request("/api/conversation"),

  deleteHistory: (id) => request(`/api/history/${id}`, { method: "DELETE" }),

  suggestions: (dataset_id) => request(`/api/suggestions/${dataset_id}`),

  createSamples: () => request("/api/samples/create", { method: "GET" }),
};

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
