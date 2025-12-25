"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@local");
  const [password, setPassword] = useState("admin123");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setErr("");
    try {
      const res = await api("/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(res.token);
      router.push("/dashboard");
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="authCard">
      <div className="authTitle">Login</div>
      <div className="authSubtitle">Use your account to manage applications and generate documents.</div>

      <form onSubmit={onSubmit}>
        <div className="authRow">
          <label>Email</label>
          <input value={email} onChange={(e)=>setEmail(e.target.value)} placeholder="you@domain.com" />
        </div>

        <div className="authRow">
          <label>Password</label>
          <input type="password" value={password} onChange={(e)=>setPassword(e.target.value)} />
        </div>

        {err ? <div className="authErr">{err}</div> : null}

        <button className="authBtn" type="submit" disabled={loading}>
          {loading ? "Signing in…" : "Login"}
        </button>

        <div className="authLink">
          No account? <a href="/signup">Create one</a>
        </div>
      </form>
    </div>
  );
}
