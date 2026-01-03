import { NextResponse } from "next/server";

const COOKIE_NAME = "site_gate";

export async function POST(req) {
  const body = await req.json().catch(() => ({}));
  const password = String(body?.password || "");

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
  const url = `${API_BASE}/v1/gate/check`;

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
    // no-cache so you don't get weird caching in some environments
    cache: "no-store",
  });

  if (!res.ok) {
    const data = await res.json().catch(() => null);
    return NextResponse.json(
      { detail: data?.detail || "Invalid password" },
      { status: 401 }
    );
  }

  const data = await res.json();
  const token = data?.token;

  const resp = NextResponse.json({ ok: true });
  resp.cookies.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7, // 7 days
  });

  return resp;
}

export async function DELETE() {
  const resp = NextResponse.json({ ok: true });
  resp.cookies.set(COOKIE_NAME, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  return resp;
}
