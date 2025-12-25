"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "../lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [accountType, setAccountType] = useState("admin");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [dob, setDob] = useState(""); // YYYY-MM-DD

  const [admins, setAdmins] = useState([]);
  const [adminQuery, setAdminQuery] = useState("");
  const [adminId, setAdminId] = useState(""); // required for user signup (selected)
  const [userId, setUserId] = useState("");   // optional custom id

  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // only needed for user signup, but cheap
    (async () => {
      try {
        const res = await api("/v1/admins/public");
        setAdmins(res.items || []);
      } catch (e) {
        // ignore; user can still type admin id if needed (but we hide that now)
        setAdmins([]);
      }
    })();
  }, []);

  const filteredAdmins = useMemo(() => {
    const q = (adminQuery || "").trim().toLowerCase();
    if (!q) return admins;
    return admins.filter((a) => {
      const name = (a.name || "").toLowerCase();
      const email = (a.email || "").toLowerCase();
      const fn = (a.first_name || "").toLowerCase();
      const ln = (a.last_name || "").toLowerCase();
      return name.includes(q) || email.includes(q) || fn.includes(q) || ln.includes(q);
    });
  }, [admins, adminQuery]);

  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setErr("");
    try {
      const payload = {
        account_type: accountType,
        email,
        password,
        first_name: firstName,
        last_name: lastName,
        dob: dob || null,
        user_id: accountType === "user" ? (userId || null) : null,
        admin_id: accountType === "user" ? (adminId || null) : null,
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
        Admins can manage multiple users. Users must be linked to an admin.
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
          <label>First name</label>
          <input value={firstName} onChange={(e)=>setFirstName(e.target.value)} placeholder="John" />
        </div>

        <div className="authRow">
          <label>Last name</label>
          <input value={lastName} onChange={(e)=>setLastName(e.target.value)} placeholder="Moore" />
        </div>

        <div className="authRow">
          <label>Date of birth (optional)</label>
          <input value={dob} onChange={(e)=>setDob(e.target.value)} placeholder="YYYY-MM-DD" />
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
              <label>Select admin (by name or email)</label>
              <input
                value={adminQuery}
                onChange={(e)=>setAdminQuery(e.target.value)}
                placeholder="Search admin..."
                style={{ marginBottom: 8 }}
              />
              <select value={adminId} onChange={(e)=>setAdminId(e.target.value)}>
                <option value="">-- Select an admin --</option>
                {filteredAdmins.map((a) => {
                  const label = `${a.first_name || ""} ${a.last_name || ""}`.trim() || (a.name || a.id);
                  const emailPart = a.email ? ` • ${a.email}` : "";
                  return (
                    <option key={a.id} value={a.id}>
                      {label}{emailPart}
                    </option>
                  );
                })}
              </select>
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
