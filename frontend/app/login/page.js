"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, setToken } from "../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    setStatus("");
    try {
      const res = await api("/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(res.token || "");
      router.push("/dashboard");
    } catch (e) {
      setStatus(String(e?.message || e));
    }
  }

  return (
    <div className="authShell">
      <div className="authCard">
        <div className="authHeader">
          <div className="authLogo">
            <div className="authLogoMark" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M5 12c2.4-4.2 5.2-6 7-6s4.6 1.8 7 6c-2.4 4.2-5.2 6-7 6s-4.6-1.8-7-6Z" stroke="rgba(10,15,28,.95)" strokeWidth="2"/>
                <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" fill="rgba(10,15,28,.95)"/>
              </svg>
            </div>
            <div>
              <div className="authTitle">Welcome back</div>
              <div className="authDesc">Log in to manage your applications and generate docs.</div>
            </div>
          </div>

          <div className="pill" style={{ fontWeight: 900 }}>
            Demo-ready
          </div>
        </div>

        {status ? <div className="authErr">{status}</div> : null}

        <form onSubmit={onSubmit} style={{ marginTop: 12 }}>
          <div className="authField">
            <div className="authLabel">Email</div>
            <input
              className="authInput"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@domain.com"
              autoComplete="email"
              required
            />
          </div>

          <div className="authField">
            <div className="authLabel">Password</div>
            <input
              className="authInput"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
          </div>

          <button className="authBtn" type="submit">
            Log in
          </button>

          <div className="authAlt">
            <span>New here?</span>
            <Link href="/signup">Create an account</Link>
          </div>

          <div className="authHint">
            Tip: Admin accounts can manage multiple users. Use the scope selector in the top bar after login.
          </div>
        </form>
      </div>
    </div>
  );
}
