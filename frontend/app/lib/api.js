'use client';

const DEFAULT_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export function getApiBase() {
  if (typeof window !== "undefined") {
    const v = window.localStorage.getItem("careeros_api_base");
    if (v && v.startsWith("http")) return v.replace(/\/$/, "");
  }
  return DEFAULT_BASE.replace(/\/$/, "");
}

export function getScopeUserId() {
  if (typeof window === "undefined") return null;
  const v = localStorage.getItem("careeros_scope") || "all";
  return v === "all" ? null : v;
}

export function getToken() {
  if (typeof window !== "undefined") {
    const t = window.localStorage.getItem("careeros_token");
    if (t) return t;
  }
  // no token by default; use login/signup
  return "";
}

export function setToken(token) {
  if (typeof window === "undefined") return;
  if (!token) {
    window.localStorage.removeItem("careeros_token");
  } else {
    window.localStorage.setItem("careeros_token", token);
  }
}

export async function apiFetch(path, init = {}) {
  const base = getApiBase();
  const token = getToken();
  const headers = {
    ...(init.headers || {}),
  };

  // If body is not FormData and Content-Type not set, default to JSON
  const isForm = (typeof FormData !== "undefined") && (init.body instanceof FormData);
  if (!isForm && !headers["Content-Type"]) headers["Content-Type"] = "application/json";

  if (token) headers["X-Auth-Token"] = token;

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

// simple alias
export const api = apiFetch;
