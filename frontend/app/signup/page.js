"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "../lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [accountType, setAccountType] = useState("admin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [adminId, setAdminId] = useState(""); // for user signup
  const [userId, setUserId] = useState("");   // optional
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setErr("");
    try {
      const payload = {
        account_type: accountType,
        email,
        password,
        admin_id: adminId || null,
        user_id: userId || null,
      };
      const res = await api("/v1/auth/signup", { method: "POST", body: JSON.stringify(payload) });
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
      <div className="authTitle">Create account</div>
      <div className="authSubtitle">
        Admins can manage multiple users. Users can be linked to an admin (optional).
      </div>

      <form onSubmit={onSubmit}>
        <div className="authRow">
          <label>Account type</label>
          <select value={accountType} onChange={(e)=>setAccountType(e.target.value)}>
            <option value="admin">Admin</option>
            <option value="user">User</option>
          </select>
        </div>

        <div className="authRow">
          <label>Email</label>
          <input value={email} onChange={(e)=>setEmail(e.target.value)} placeholder="you@domain.com" />
        </div>

        <div className="authRow">
          <label>Password (min 6 chars)</label>
          <input type="password" value={password} onChange={(e)=>setPassword(e.target.value)} />
        </div>

        {accountType === "user" ? (
          <>
            <div className="authRow">
              <label>Admin ID (optional)</label>
              <input value={adminId} onChange={(e)=>setAdminId(e.target.value)} placeholder="a_1234abcd" />
            </div>
            <div className="authRow">
              <label>User ID (optional)</label>
              <input value={userId} onChange={(e)=>setUserId(e.target.value)} placeholder="u_james" />
            </div>
          </>
        ) : null}

        {err ? <div className="authErr">{err}</div> : null}

        <button className="authBtn" type="submit" disabled={loading}>
          {loading ? "Creating…" : "Sign up"}
        </button>

        <div className="authLink">
          Already have an account? <a href="/login">Login</a>
        </div>
      </form>
    </div>
  );
}
