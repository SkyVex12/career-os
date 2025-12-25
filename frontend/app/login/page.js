
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
    setStatus("Logging in...");
    try {
      const res = await api("/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(res.token);
      setStatus("✅ Logged in");
      router.push("/dashboard");
    } catch (err) {
      setStatus(String(err?.message || err));
    }
  }

  return (
    <main className="authShell">
      <div className="authBg" aria-hidden="true" />
      <div className="authCard">
        <div className="authBrand">
          <div className="authMark" />
          <div>
            <div className="authTitle">CareerOS</div>
            <div className="authSub">Sign in to manage applications & generate docs</div>
          </div>
        </div>

        <form onSubmit={onSubmit} className="authForm">
          <label className="authLabel">Email</label>
          <input className="authInput" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@email.com" autoComplete="email" />

          <label className="authLabel">Password</label>
          <input className="authInput" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" />

          <button className="authBtn authBtnPrimary" type="submit">Login</button>

          {status ? <div className={status.startsWith("✅") ? "authOk" : "authErr"}>{status}</div> : null}

          <div className="authFoot">
            <span>New here?</span>
            <Link href="/signup">Create an account</Link>
          </div>
        </form>
      </div>
    </main>
  );
}
