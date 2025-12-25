
const DEFAULT_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export function getToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("careeros_token") || "";
}

export function setToken(token) {
  if (typeof window === "undefined") return;
  if (!token) localStorage.removeItem("careeros_token");
  else localStorage.setItem("careeros_token", token);
}

export async function api(path, options = {}) {
  const base = DEFAULT_BASE;
  const url = path.startsWith("http") ? path : base + path;

  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body) headers.set("Content-Type", "application/json");

  const tok = getToken();
  if (tok) headers.set("X-Auth-Token", tok);

  const res = await fetch(url, { ...options, headers, cache: "no-store" });
  const ct = res.headers.get("content-type") || "";
  let data = null;
  if (ct.includes("application/json")) {
    data = await res.json().catch(() => null);
  } else {
    data = await res.text().catch(() => "");
  }
  if (!res.ok) {
    const msg = typeof data === "string" ? data : (data?.detail || data?.message || JSON.stringify(data));
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return data;
}

export const apiFetch = api;
