const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const TOKEN = process.env.NEXT_PUBLIC_EXTENSION_TOKEN || "";

async function request(path, init = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(TOKEN ? { "X-Extension-Token": TOKEN } : {}),
      ...(init.headers || {}),
    },
  });

  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }

  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) ? (data.detail || data.message) : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

export async function putBaseResume(userId, contentText) {
  return request(`/v1/users/${encodeURIComponent(userId)}/base-resume`, {
    method: "PUT",
    body: JSON.stringify({ content_text: contentText }),
  });
}

export async function getBaseResume(userId) {
  return request(`/v1/users/${encodeURIComponent(userId)}/base-resume`, { method: "GET" });
}

export async function generateResume(payload) {
  return request(`/v1/ingest/apply-and-generate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function buildFileUrl(fileId) {
  return `${API_BASE}/v1/files/${fileId}`;
}
