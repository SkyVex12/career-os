"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const Icon = ({ name }) => {
  // Minimal inline icons to avoid extra deps
  const common = {
    className: "navIcon",
    viewBox: "0 0 24 24",
    fill: "none",
    xmlns: "http://www.w3.org/2000/svg",
  };
  switch (name) {
    case "dashboard":
      return (
        <svg {...common}>
          <path d="M3 13h8V3H3v10Z" stroke="currentColor" strokeWidth="2" />
          <path d="M13 21h8V11h-8v10Z" stroke="currentColor" strokeWidth="2" />
          <path d="M13 3h8v6h-8V3Z" stroke="currentColor" strokeWidth="2" />
          <path d="M3 17h8v4H3v-4Z" stroke="currentColor" strokeWidth="2" />
        </svg>
      );
    case "apps":
      return (
        <svg {...common}>
          <path d="M7 3h4v4H7V3Z" stroke="currentColor" strokeWidth="2" />
          <path d="M13 3h4v4h-4V3Z" stroke="currentColor" strokeWidth="2" />
          <path d="M7 9h4v4H7V9Z" stroke="currentColor" strokeWidth="2" />
          <path d="M13 9h4v4h-4V9Z" stroke="currentColor" strokeWidth="2" />
          <path d="M7 15h4v6H7v-6Z" stroke="currentColor" strokeWidth="2" />
          <path d="M13 15h4v6h-4v-6Z" stroke="currentColor" strokeWidth="2" />
        </svg>
      );
    case "users":
      return (
        <svg {...common}>
          <path
            d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"
            stroke="currentColor"
            strokeWidth="2"
          />
          <path
            d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"
            stroke="currentColor"
            strokeWidth="2"
          />
          <path
            d="M22 21v-2a4 4 0 0 0-3-3.87"
            stroke="currentColor"
            strokeWidth="2"
          />
          <path
            d="M16 3.13a4 4 0 0 1 0 7.75"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <path
            d="M4 6h16M4 12h16M4 18h16"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      );
  }
};

export default function Sidebar() {
  const pathname = usePathname();

  const nav = [
    { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
    { href: "/applications", label: "Applications", icon: "apps" },
    { href: "/manage-users", label: "Manage users", icon: "users" },
  ];

  return (
    <aside className="sidebar">
      <Link href="/dashboard" className="brand" aria-label="CareerOS Home">
        <div className="brandMark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
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
          <div className="brandTitle">CareerOS</div>
          <div className="brandSub">Applications + documents</div>
        </div>
      </Link>

      <nav className="nav" aria-label="Primary">
        {nav.map((i) => (
          <Link
            key={i.href}
            href={i.href}
            className={pathname === i.href ? "active" : ""}
          >
            <Icon name={i.icon} />
            <span>{i.label}</span>
          </Link>
        ))}
      </nav>

      <div style={{ marginTop: 14 }} className="card">
        <div className="cardTitle">Tip</div>
        <div className="cardSub">
          Use the extension on a job post to auto-save the application and
          generate a tailored resume.
        </div>
      </div>
    </aside>
  );
}
