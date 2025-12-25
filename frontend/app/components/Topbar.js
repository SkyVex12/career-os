
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, setToken, getToken } from "../lib/api";
import { useScope } from "./ClientShell";

export default function Topbar({ title = "CareerOS", subtitle = "Application analytics + document generator" }) {
  const router = useRouter();
  const { mounted, principal, setPrincipal, users, setUsers, scope, setScope } = useScope();
  const [err, setErr] = useState("");

  // Refresh principal/users on mount (ClientShell already does, but this keeps Topbar resilient)
  useEffect(() => {
    if (!mounted) return;
    (async () => {
      try {
        setErr("");
        const tok = getToken();
        if (!tok) return;
        const me = await api("/v1/me");
        setPrincipal(me);
        const u = await api("/v1/users");
        const items = Array.isArray(u) ? u : (u.items || u.users || []);
        setUsers(items);
      } catch (e) {
        setErr(String(e?.message || e));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted]);

  async function onLogout() {
    try {
      await api("/v1/auth/logout", { method: "POST" });
    } catch {}
    setToken("");
    localStorage.removeItem("careeros_scope");
    setPrincipal(null);
    setUsers([]);
    setScope({ mode: "all", userId: null });
    router.push("/login");
  }

  // Hydration-safe: never branch on localStorage during SSR / first render
  if (!mounted) {
    return (
      <div className="topbar">
        <div className="topLeft">
          <div className="topTitle">{title}</div>
          <div className="topSub">{subtitle}</div>
        </div>
        <div className="topRight">
          <div className="pill">Loading…</div>
        </div>
      </div>
    );
  }

  const token = getToken();

  return (
    <div className="topbar">
      <div className="topLeft">
        <div className="topTitle">{title}</div>
        <div className="topSub">{subtitle}</div>
      </div>

      <div className="topRight">
        {err ? <div className="pill pillErr">{err}</div> : null}

        {principal ? (
          <>
            <div className="pill">
              {principal.type === "admin" ? `Admin: ${principal.admin_id}` : `User: ${principal.user_id}`}
            </div>

            {principal.type === "admin" ? (
              <div className="pill">
                <span className="muted" style={{ marginRight: 8 }}>Scope</span>
                <select
                  value={scope.mode === "all" ? "all" : (scope.userId || "all")}
                  onChange={(e) => {
                    const v = e.target.value;
                    setScope(v === "all" ? { mode: "all", userId: null } : { mode: "user", userId: v });
                  }}
                >
                  <option value="all">All my users</option>
                  {users.map(u => (
                    <option key={u.id} value={u.id}>{u.name ? `${u.name} (${u.id})` : u.id}</option>
                  ))}
                </select>
              </div>
            ) : null}

            <button className="pill pillBtn" onClick={onLogout}>Logout</button>
          </>
        ) : (
          token ? <div className="pill">Loading…</div> : <Link className="pill pillBtn" href="/login">Login</Link>
        )}
      </div>
    </div>
  );
}
