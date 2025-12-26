"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";
import Topbar from "../components/Topbar";
import { useScope } from "../components/ClientShell";

export default function ManageUsersPage() {
  const { mounted, principal } = useScope();
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstname, setFirstname] = useState("");
  const [lastname, setLastname] = useState("");
  const [dob, setDob] = useState("");

  async function refresh() {
    const res = await api("/v1/users");
    const list = Array.isArray(res) ? res : res.items || [];
    setItems(list);
  }

  useEffect(() => {
    if (!mounted) return;
    refresh().catch((e) => setStatus(String(e?.message || e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted]);

  async function onCreate(e) {
    e.preventDefault();
    setStatus("Creating user...");
    try {
      await api("/v1/admin/users", {
        method: "POST",
        body: JSON.stringify({ email, password, firstname, lastname, dob }),
      });
      setEmail("");
      setPassword("");
      setFirstname("");
      setLastname("");
      setDob("");
      setStatus("✅ User created & linked");
      await refresh();
    } catch (e) {
      setStatus(String(e?.message || e));
    }
  }

  if (!mounted) return null;

  if (!principal) {
    return (
      <main className="container">
        <Topbar title="Manage Users" subtitle="Admin only" />
        <div className="card">Please login.</div>
      </main>
    );
  }

  if (principal.type !== "admin") {
    return (
      <main className="container">
        <Topbar title="Manage Users" subtitle="Admin only" />
        <div className="card" style={{ gap: 12, marginTop: 12 }}>
          Forbidden (admin only).
        </div>
      </main>
    );
  }

  return (
    <main className="container">
      <Topbar title="Manage Users" subtitle="Create & link users" />

      <div className="grid2" style={{ gap: 12, marginTop: 12 }}>
        <div className="card">
          <div className="cardTitle">Create new user</div>
          <form onSubmit={onCreate}>
            <label className="label">Email</label>
            <input
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />

            <label className="label">Password</label>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />

            <div className="row">
              <div>
                <label className="label">First name</label>
                <input
                  className="input"
                  value={firstname}
                  onChange={(e) => setFirstname(e.target.value)}
                />
              </div>
              <div>
                <label className="label">Last name</label>
                <input
                  className="input"
                  value={lastname}
                  onChange={(e) => setLastname(e.target.value)}
                />
              </div>
            </div>
            <div className="row">
              <label className="label">Date of birth</label>
              <input
                className="input"
                type="date"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
              />

              <label className="label">Date of birth</label>
              <input
                className="input"
                type="date"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
              />

              <button className="btnPrimary" type="submit">
                Create & Link
              </button>
            </div>
            {status ? <div className="status">{status}</div> : null}
          </form>
        </div>

        <div className="card">
          <div className="cardTitle">My linked users</div>
          <div className="muted" style={{ marginBottom: 10 }}>
            Total: {items.length}
          </div>
          <div className="list">
            {items.map((u) => (
              <div key={u.id} className="listRow">
                <div>
                  <div style={{ fontWeight: 700 }}>
                    {u.name ||
                      `${u.firstname || ""} ${u.lastname || ""}`.trim() ||
                      u.id}
                  </div>
                  <div className="muted">
                    {u.id}
                    {u.email ? ` • ${u.email}` : ""}
                  </div>
                </div>
              </div>
            ))}
            {!items.length ? (
              <div className="muted">No users linked yet.</div>
            ) : null}
          </div>
        </div>
      </div>
    </main>
  );
}
