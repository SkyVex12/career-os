"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function GateClient() {
  const router = useRouter();
  const sp = useSearchParams();

  const next = useMemo(() => sp.get("next") || "/", [sp]);

  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    setErr("");

    const res = await fetch("/api/gate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ password, next }),
    });

    if (!res.ok) {
      setErr("Wrong password");
      return;
    }

    // IMPORTANT: middleware may immediately redirect if cookie not set correctly,
    // so use a hard navigation (most reliable).
    window.location.assign(next);
  }

  return (
    <main style={{ maxWidth: 420, margin: "48px auto", padding: 16 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>Password required</h1>

      <form
        onSubmit={onSubmit}
        style={{ marginTop: 12, display: "grid", gap: 10 }}
      >
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Enter password"
          type="password"
          autoFocus
          style={{ padding: 10, border: "1px solid #ddd", borderRadius: 8 }}
        />
        <button type="submit" style={{ padding: 10, borderRadius: 8 }}>
          Enter
        </button>
        {err ? <div style={{ color: "crimson" }}>{err}</div> : null}
      </form>
    </main>
  );
}
