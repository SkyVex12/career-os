"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import toast from "react-hot-toast";
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
  const [selectedAdminIds, setSelectedAdminIds] = useState([]);
  const [adminQuery, setAdminQuery] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const res = await api("/v1/admins/public");
        const items = Array.isArray(res) ? res : res.items || res.admins || [];
        setAdmins(items);
      } catch (e) {
        setAdmins([]);
      }
    })();
  }, []);

  const filteredAdmins = useMemo(() => {
    const q = adminQuery.trim().toLowerCase();
    if (!q) return admins;
    return admins.filter(
      (a) =>
        String(a.email || "")
          .toLowerCase()
          .includes(q) ||
        String(a.name || "")
          .toLowerCase()
          .includes(q) ||
        String(a.id || a.admin_id || "")
          .toLowerCase()
          .includes(q)
    );
  }, [admins, adminQuery]);

  function toggleAdmin(id) {
    setSelectedAdminIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function onSubmit(e) {
    e.preventDefault();
    setStatus("");
    try {
      const payload = {
        role,
        email,
        password,
        firstname,
        lastname,
        dob,
      };

      // If a user signs up, they can link to multiple admins
      if (role === "user") payload.admin_ids = selectedAdminIds;

      const res = await api("/v1/auth/signup", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setToken(res.token || "");
      toast.success("Account created successfully");
      router.push("/dashboard");
    } catch (err) {
      setStatus(String(err?.message || err));
    }
  }

  return (
    <div className="authShell">
      <div className="authCard">
        <div className="authHeader">
          <div className="authLogo">
            <div className="authLogoMark" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M5 12c2.4-4.2 5.2-6 7-6s4.6 1.8 7 6c-2.4 4.2-5.2 6-7 6s-4.6-1.8-7-6Z"
                  stroke="rgba(10,15,28,.95)"
                  strokeWidth="2"
                />
                <path
                  d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"
                  fill="rgba(10,15,28,.95)"
                />
              </svg>
            </div>
            <div>
              <div className="authTitle">Create your account</div>
              <div className="authDesc">
                Users can link to multiple admins. Admins can manage linked
                users.
              </div>
            </div>
          </div>
          <Link className="pill pillBtn" href="/login">
            Login
          </Link>
        </div>

        {status ? <div className="authErr">{status}</div> : null}

        <form onSubmit={onSubmit} style={{ marginTop: 12 }}>
          <div className="authField">
            <div className="authLabel">Account type</div>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              style={{ width: "100%" }}
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          <div className="authGrid2">
            <div className="authField">
              <div className="authLabel">First name</div>
              <input
                className="authInput"
                type="text"
                value={firstname}
                onChange={(e) => setFirstname(e.target.value)}
                placeholder="Goran"
                required
              />
            </div>
            <div className="authField">
              <div className="authLabel">Last name</div>
              <input
                className="authInput"
                type="text"
                value={lastname}
                onChange={(e) => setLastname(e.target.value)}
                placeholder="M."
                required
              />
            </div>
          </div>

          <div className="authField">
            <div className="authLabel">Date of birth</div>
            <input
              className="authInput"
              type="date"
              value={dob}
              onChange={(e) => setDob(e.target.value)}
              required
            />
          </div>

          <div className="authField">
            <div className="authLabel">Email</div>
            <input
              className="authInput"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@domain.com"
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
              placeholder="Create a strong password"
              required
            />
          </div>

          {role === "user" ? (
            <div className="authField">
              <div className="authLabel">Link to admins (optional)</div>
              <input
                className="authInput"
                type="text"
                value={adminQuery}
                onChange={(e) => setAdminQuery(e.target.value)}
                placeholder="Search by admin email or name…"
              />
              <div
                style={{
                  marginTop: 10,
                  display: "flex",
                  gap: 8,
                  flexWrap: "wrap",
                }}
              >
                {selectedAdminIds.length ? (
                  selectedAdminIds.map((id) => {
                    const a =
                      admins.find((x) => (x.id || x.admin_id) === id) || {};
                    const label = a.name
                      ? `${a.name} (${a.email || id})`
                      : a.email || id;
                    return (
                      <button
                        key={id}
                        type="button"
                        className="badge warn"
                        onClick={() => toggleAdmin(id)}
                        title="Click to remove"
                      >
                        {label} ✕
                      </button>
                    );
                  })
                ) : (
                  <div className="muted" style={{ fontSize: 12 }}>
                    No admins selected.
                  </div>
                )}
              </div>

              <div className="hr" />

              <div
                style={{
                  display: "grid",
                  gap: 8,
                  maxHeight: 180,
                  overflow: "auto",
                  paddingRight: 4,
                }}
              >
                {filteredAdmins.map((a) => {
                  const id = a.id || a.admin_id;
                  const active = selectedAdminIds.includes(id);
                  return (
                    <button
                      key={id}
                      type="button"
                      className={"pill " + (active ? "pillBtn" : "")}
                      onClick={() => toggleAdmin(id)}
                      style={{ justifyContent: "space-between", width: "100%" }}
                    >
                      <span>
                        <strong>{a.name || "Admin"}</strong>{" "}
                        <span className="muted">{a.email || id}</span>
                      </span>
                      <span>{active ? "Selected" : "Select"}</span>
                    </button>
                  );
                })}
                {!filteredAdmins.length ? (
                  <div className="authHint">
                    No admins found for that search.
                  </div>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="authHint">
              Creating an <strong>Admin</strong> lets you manage multiple linked
              users and generate docs for them (batch mode in extension).
            </div>
          )}

          <button className="authBtn" type="submit">
            Create account
          </button>

          <div className="authAlt">
            <span>Already have an account?</span>
            <Link href="/login">Log in</Link>
          </div>
        </form>
      </div>
    </div>
  );
}
