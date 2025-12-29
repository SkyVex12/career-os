"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "../lib/api";
import { useScope } from "./ClientShell";
import toast from "react-hot-toast";

export default function Topbar({
  title = "CareerOS",
  subtitle = "Application analytics + document generator",
}) {
  const router = useRouter();
  const { principal, setPrincipal, users, setUsers, scope, setScope } =
    useScope();
  const [err, setErr] = useState("");
  const [mounted, setMounted] = useState(false);

  const changeScope = (e) => {
    const v = e.target.value;
    setScope(
      v === "all" ? { mode: "all", userId: null } : { mode: "user", userId: v }
    );

    try {
      if (v === "all") {
        localStorage.removeItem("careeros_user_id");
      } else {
        localStorage.setItem("careeros_user_id", v);
      }
      window.dispatchEvent(new Event("careeros:user-changed"));
    } catch {}
  };

  useEffect(() => {
    setMounted(true);
    (async () => {
      try {
        setErr("");
        const me = await api("/v1/me");
        setPrincipal(me);

        // For admin: show users under this admin (via /v1/users)
        // For user: backend may still return a list (safe to show), but scope selector won't appear.
        const u = await api("/v1/users");
        const items = Array.isArray(u) ? u : u.items || u.users || [];
        setUsers(items);
      } catch (e) {
        // If not logged in, keep principal null and avoid noisy errors on public pages.
        setPrincipal(null);
        setUsers([]);
        setErr("");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onLogout() {
    try {
      await api("/v1/auth/logout", { method: "POST" });
    } catch (e) {}
    setToken("");
    localStorage.removeItem("careeros_scope");
    setPrincipal(null);
    setUsers([]);
    setScope({ mode: "all", userId: null });
    toast.success("Logged out successfully");
    router.push("/login");
  }

  if (!mounted) {
    // Avoid hydration mismatch by rendering stable placeholder on the server
    return (
      <div className="topbar">
        <div className="topLeft">
          <div className="topTitle">
            <span className="dot" />
            {title}
          </div>
          <div className="topSub">{subtitle}</div>
        </div>
        <div className="topRight">
          <div className="pill">Loading…</div>
        </div>
      </div>
    );
  }

  return (
    <div className="topbar">
      <div className="topLeft">
        <div className="topTitle">
          <span className="dot" />
          {title}
        </div>
        <div className="topSub">{subtitle}</div>
      </div>

      <div className="topRight">
        {err ? <div className="pill pillErr">{err}</div> : null}

        {principal ? (
          <>
            <div className="pill">
              <strong>{principal.type === "admin" ? "Admin" : "User"}</strong>
              <span className="muted">
                {principal.name ? ` - ${principal.name}` : ""} (
                {principal.type === "admin"
                  ? principal.admin_id
                  : principal.user_id}
                )
              </span>
            </div>

            {principal.type === "admin" ? (
              <div className="pill">
                <span className="muted" style={{ marginRight: 8 }}>
                  Scope
                </span>
                <select
                  value={scope.mode === "all" ? "all" : scope.userId || "all"}
                  onChange={(e) => changeScope(e)}
                  aria-label="Scope selector"
                >
                  <option value="all">All my users</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name ? `${u.name} (${u.id})` : u.id}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}

            <button className="pill pillBtn" onClick={onLogout}>
              Logout
            </button>
          </>
        ) : (
          <a className="pill pillBtn" href="/login">
            Login
          </a>
        )}
      </div>
    </div>
  );
}
