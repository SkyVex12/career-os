'use client';

const DEFAULT_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const DEFAULT_TOKEN = process.env.NEXT_PUBLIC_EXTENSION_TOKEN || "";

export function getApiBase() {
  // allow override via localStorage (optional)
  if (typeof window !== "undefined") {
    const v = window.localStorage.getItem("careeros_api_base");
    if (v && v.startsWith("http")) return v.replace(/\/$/, "");
  }
  return DEFAULT_BASE.replace(/\/$/, "");
}

export function getToken() {
  if (typeof window !== "undefined") {
    const t = window.localStorage.getItem("careeros_token");
    if (t) return t;
  }
  return DEFAULT_TOKEN;
}

export async function apiFetch(path, init = {}) {
  const base = getApiBase();
  const token = getToken();
  const headers = {
    "Content-Type": "application/json",
    ...(init.headers || {}),
  };
  // only add token if present (backend will 401 if required)
  if (token) headers["X-Extension-Token"] = token;

  const res = await fetch(`${base}${path}`, { ...init, headers });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) ? (data.detail || data.message) : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}
