
"use client";

import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import Sidebar from "./Sidebar";
import { api, getToken, setToken } from "../lib/api";

const ScopeContext = createContext(null);

export function useScope() {
  const ctx = useContext(ScopeContext);
  if (!ctx) throw new Error("useScope must be used within <ClientShell/>");
  return ctx;
}

export default function ClientShell({ children }) {
  const [mounted, setMounted] = useState(false);
  const [principal, setPrincipal] = useState(null); // {type, admin_id/user_id}
  const [users, setUsers] = useState([]);
  const [scope, setScope] = useState({ mode: "all", userId: null }); // admin-only
  const [loading, setLoading] = useState(false);

  // Hydration-safe init
  useEffect(() => {
    setMounted(true);
    const savedScope = localStorage.getItem("careeros_scope");
    if (savedScope) {
      try {
        const s = JSON.parse(savedScope);
        if (s?.mode === "user" && s?.userId) setScope({ mode: "user", userId: s.userId });
        else setScope({ mode: "all", userId: null });
      } catch {}
    }
  }, []);

  // Load principal/users once token exists
  useEffect(() => {
    if (!mounted) return;
    const tok = getToken();
    if (!tok) {
      setPrincipal(null);
      setUsers([]);
      return;
    }
    (async () => {
      setLoading(true);
      try {
        const me = await api("/v1/me");
        setPrincipal(me);
        const u = await api("/v1/users");
        const items = Array.isArray(u) ? u : (u.items || u.users || []);
        setUsers(items);
      } catch (e) {
        // token invalid; reset
        setToken("");
        setPrincipal(null);
        setUsers([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [mounted]);

  useEffect(() => {
    if (!mounted) return;
    localStorage.setItem("careeros_scope", JSON.stringify(scope));
  }, [mounted, scope]);

  const value = useMemo(
    () => ({
      mounted,
      loading,
      principal,
      setPrincipal,
      users,
      setUsers,
      scope,
      setScope,
    }),
    [mounted, loading, principal, users, scope]
  );

  return (
    <ScopeContext.Provider value={value}>
      <div className="shell">
        <Sidebar />
        <main className="main">{children}</main>
      </div>
    </ScopeContext.Provider>
  );
}
