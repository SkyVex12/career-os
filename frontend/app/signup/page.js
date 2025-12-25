
"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, setToken } from "../lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [role, setRole] = useState("user"); // user|admin
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstname, setFirstname] = useState("");
  const [lastname, setLastname] = useState("");
  const [dob, setDob] = useState("");

  const [admins, setAdmins] = useState([]);
  const [adminFilter, setAdminFilter] = useState("");
  const [selectedAdminIds, setSelectedAdminIds] = useState([]);

  const [status, setStatus] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const a = await api("/v1/admins/public");
        setAdmins(a.items || []);
      } catch {
        setAdmins([]);
      }
    })();
  }, []);

  const filteredAdmins = useMemo(() => {
    const f = adminFilter.trim().toLowerCase();
    if (!f) return admins;
    return admins.filter(a => (a.name || "").toLowerCase().includes(f) || (a.id || "").toLowerCase().includes(f));
  }, [admins, adminFilter]);

  async function onSubmit(e) {
    e.preventDefault();
    setStatus("Signing up...");
    try {
      const payload = {
        role,
        email,
        password,
        firstname: firstname || null,
        lastname: lastname || null,
        dob: dob || null,
      };
      if (role === "user") {
        payload.admin_ids = selectedAdminIds;
      }
      const res = await api("/v1/auth/signup", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setToken(res.token);
      setStatus("✅ Signed up");
      router.push("/dashboard");
    } catch (err) {
      setStatus(String(err?.message || err));
    }
  }

  function toggleAdmin(id) {
    setSelectedAdminIds((prev) => (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]));
  }

  return (
    <main className="authShell">
      <div className="authBg" aria-hidden="true" />
      <div className="authCard">
        <div className="authBrand">
          <div className="authMark" aria-hidden="true">C</div>
          <div>
            <div className="authBrandName">CareerOS</div>
            <div className="authBrandTag">Create your account</div>
          </div>
        </div>

        <div className="authTabs" style={{ marginTop: 10 }}>
          <button
            type="button"
            className={`authTab ${role === "user" ? "isActive" : ""}`}
            onClick={() => setRole("user")}
          >
            User
          </button>
          <button
            type="button"
            className={`authTab ${role === "admin" ? "isActive" : ""}`}
            onClick={() => setRole("admin")}
          >
            Admin
          </button>
        </div>

        <form onSubmit={onSubmit} className="authForm" style={{ marginTop: 12 }}>
          <label className="label">Email</label>
          <input className="authInput" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@email.com" />

          <label className="label">Password</label>
          <input className="authInput" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />

          <div className="row">
            <div>
              <label className="label">First name</label>
              <input className="authInput" value={firstname} onChange={(e) => setFirstname(e.target.value)} />
            </div>
            <div>
              <label className="label">Last name</label>
              <input className="authInput" value={lastname} onChange={(e) => setLastname(e.target.value)} />
            </div>
          </div>

          <label className="label">Date of birth</label>
          <input className="authInput" type="date" value={dob} onChange={(e) => setDob(e.target.value)} />

          {role === "user" ? (
            <div style={{ marginTop: 12 }}>
              <label className="label">Select Admins (optional)</label>
              <input className="authInput" value={adminFilter} onChange={(e) => setAdminFilter(e.target.value)} placeholder="Filter admins by name/id..." />
              <div className="checkList" style={{ marginTop: 10 }}>
                {filteredAdmins.length ? filteredAdmins.map((a) => (
                  <label key={a.id} className="checkRow">
                    <input type="checkbox" checked={selectedAdminIds.includes(a.id)} onChange={() => toggleAdmin(a.id)} />
                    <span style={{ marginLeft: 8 }}>{a.name ? `${a.name} (${a.id})` : a.id}</span>
                  </label>
                )) : <div className="muted">No admins found.</div>}
              </div>
              <div className="muted" style={{ marginTop: 6 }}>
                Users can link to multiple admins. You can also add admins later (admin can link you).
              </div>
            </div>
          ) : null}

          <button className="authBtn authBtnPrimary" type="submit">Create account</button>

          {status ? <div className="status">{status}</div> : null}

          <div className="muted" style={{ marginTop: 10 }}>
            Already have an account? <Link href="/login">Login</Link>
          </div>
        </form>
      </div>
    </main>
  );
}
