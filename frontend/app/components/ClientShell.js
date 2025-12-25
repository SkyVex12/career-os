"use client";

import { useEffect, useMemo, useState, createContext, useContext } from "react";
import { usePathname, useRouter } from "next/navigation";
import Topbar from "./Topbar";
import { api, getToken } from "../lib/api";

const ScopeCtx = createContext(null);
export function useScope() { return useContext(ScopeCtx); }

function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="logo" />
        <div>
          <h1>CareerOS</h1>
          <p>Track → Analyze → Win</p>
        </div>
      </div>

      <div className="nav">
        <a href="/dashboard">Dashboard</a>
        <a href="/applications">Applications</a>
        <a href="/assistant">Assistant</a>
        <a href="/documents">Documents</a>
      </div>

      <div style={{ marginTop: 16 }} className="card cardPad">
        <div style={{ fontWeight: 700, marginBottom: 6 }}>Tip</div>
        <div className="muted">
          Use the header selector to view <strong>All users</strong> or one user.
        </div>
      </div>
    </aside>
  );
}

export default function ClientShell({ children }) {
  const router = useRouter();
  const pathname = usePathname();

  const [principal, setPrincipal] = useState(null);
  const [users, setUsers] = useState([]);
  const [scope, setScope] = useState(() => {
    if (typeof window === "undefined") return { mode: "all", userId: null };
    const v = localStorage.getItem("careeros_scope") || "all";
    return v === "all" ? { mode: "all", userId: null } : { mode: "user", userId: v };
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    localStorage.setItem("careeros_scope", scope.mode === "all" ? "all" : (scope.userId || "all"));
  }, [scope]);

  const isAuthPage = pathname === "/login" || pathname === "/signup";

  useEffect(() => {
    const token = getToken();
    if (!token && !isAuthPage) {
      router.push("/login");
      return;
    }
    if (token && isAuthPage) {
      router.push("/dashboard");
      return;
    }
  }, [isAuthPage, router]);

  useEffect(() => {
    (async () => {
      const token = getToken();
      if (!token) return;
      try {
        const me = await api("/v1/me");
        setPrincipal(me);

        const u = await api("/v1/users");
        const items = Array.isArray(u) ? u : (u.items || u.users || []);
        setUsers(items);

        if (me.type === "user") {
          setScope({ mode: "user", userId: me.user_id });
          localStorage.setItem("careeros_scope", me.user_id);
        } else {
          if (scope.mode === "user") {
            const ok = items.some(x => String(x.id) === String(scope.userId));
            if (!ok) setScope({ mode: "all", userId: null });
          }
        }
      } catch (e) {
        router.push("/login");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo(() => ({ principal, setPrincipal, users, setUsers, scope, setScope }), [principal, users, scope]);

  if (isAuthPage) {
    return (
      <ScopeCtx.Provider value={value}>
        <div className="authShell">{children}</div>
      </ScopeCtx.Provider>
    );
  }

  return (
    <ScopeCtx.Provider value={value}>
      <div className="shell">
        <Sidebar />
        <main className="main">
          <Topbar />
          {children}
        </main>
      </div>
    </ScopeCtx.Provider>
  );
}
