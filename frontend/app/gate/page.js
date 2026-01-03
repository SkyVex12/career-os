"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function GatePage() {
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get("next") || "/";

  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e) {
    e?.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const res = await fetch("/api/gate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) {
        const msg =
          (await res.json().catch(() => null))?.detail || "Wrong password";
        setErr(msg);
        return;
      }
      router.replace(next);
      router.refresh();
      console.log("--------------------------", next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: 24,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 420,
          border: "1px solid #e5e7eb",
          borderRadius: 12,
          padding: 20,
        }}
      >
        <h1 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>
          Enter site password
        </h1>
        <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 16 }}>
          This is a simple access gate (not a user login).
        </p>

        <form onSubmit={submit} style={{ display: "grid", gap: 10 }}>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            autoFocus
            style={{
              width: "100%",
              padding: "10px 12px",
              border: "1px solid #d1d5db",
              borderRadius: 10,
              outline: "none",
            }}
          />

          {err ? (
            <div style={{ color: "#b91c1c", fontSize: 13 }}>{err}</div>
          ) : null}

          <button
            type="submit"
            disabled={busy || !password}
            style={{
              padding: "10px 12px",
              borderRadius: 10,
              border: "1px solid #111827",
              background: busy ? "#111827" : "#111827",
              color: "white",
              cursor: busy || !password ? "not-allowed" : "pointer",
              opacity: busy || !password ? 0.7 : 1,
              fontWeight: 600,
            }}
          >
            {busy ? "Checking..." : "Enter"}
          </button>
        </form>
      </div>
    </div>
  );
}
