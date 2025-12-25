
"use client";

import Link from "next/link";
import { useScope } from "./ClientShell";

export default function Sidebar() {
  const { mounted, principal } = useScope();

  const isAdmin = mounted && principal?.type === "admin";

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brandTitle">CareerOS</div>
        <div className="brandSub">Apps + Docs</div>
      </div>

      <nav className="nav">
        <Link className="navItem" href="/dashboard">Dashboard</Link>
        <Link className="navItem" href="/applications">Applications</Link>
        {isAdmin ? <Link className="navItem" href="/manage-users">Manage Users</Link> : null}
      </nav>
    </aside>
  );
}
