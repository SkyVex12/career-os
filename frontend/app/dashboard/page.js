'use client';

import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../lib/api";
import TopbarClient from "../components/TopbarClient";

function pct(n) {
  if (!isFinite(n)) return "0%";
  return `${Math.round(n * 100)}%`;
}

export default function DashboardPage() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("Loading...");
  const [rangeDays, setRangeDays] = useState(90);

  async function refresh() {
    try {
      setStatus("Loading...");
      // NOTE: this expects your backend to provide GET /v1/applications
      const userId = (typeof window !== 'undefined' ? (localStorage.getItem('careeros_user_id') || 'u1') : 'u1');
      const data = await apiFetch(`/v1/applications?user_id=${encodeURIComponent(userId)}`);
      setItems(Array.isArray(data) ? data : []);
      setStatus("");
    } catch (e) {
      setStatus(`Error: ${e.message}\n\nIf you haven't added /v1/applications in the backend yet, we'll add it next.`);
    }
  }

  useEffect(() => { refresh(); }, []);

  const filtered = useMemo(() => {
    const now = Date.now();
    const cutoff = now - rangeDays * 24 * 60 * 60 * 1000;
    return items.filter((x) => {
      const d = x.created_at ? Date.parse(x.created_at) : null;
      return !d || d >= cutoff;
    });
  }, [items, rangeDays]);

  const stats = useMemo(() => {
    const byStage = {};
    for (const a of filtered) {
      const stage = (a.stage || "applied").toLowerCase();
      byStage[stage] = (byStage[stage] || 0) + 1;
    }
    const total = filtered.length;
    const applied = (byStage.applied || 0) + (byStage.submitted || 0);
    const interview = (byStage.interview || 0) + (byStage.interviewing || 0) + (byStage.phone || 0);
    const rejected = (byStage.rejected || 0) + (byStage.declined || 0);
    const offer = (byStage.offer || 0) + (byStage.offered || 0);

    const interviewRate = total ? interview / total : 0;
    const offerRate = total ? offer / total : 0;
    const rejectRate = total ? rejected / total : 0;

    return { total, applied, interview, rejected, offer, byStage, interviewRate, offerRate, rejectRate };
  }, [filtered]);

  const topStages = useMemo(() => {
    const entries = Object.entries(stats.byStage).sort((a,b)=>b[1]-a[1]);
    return entries.slice(0, 8);
  }, [stats.byStage]);

  return (
    <main className="container">
      <TopbarClient title="Dashboard" subtitle="Your funnel, success rate, and recent activity." />
      <p style={{ marginTop: 6, color: "#444" }}>
        Overview of your applications — counts, rates, and funnel health.
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "center", margin: "12px 0" }}>
        <label style={{ fontSize: 12, color: "#222" }}>Time range</label>
        <select value={rangeDays} onChange={(e) => setRangeDays(Number(e.target.value))}>
          <option value={30}>Last 30 days</option>
          <option value={60}>Last 60 days</option>
          <option value={90}>Last 90 days</option>
          <option value={365}>Last 12 months</option>
        </select>
        <button onClick={refresh} style={{ padding: "6px 10px", cursor: "pointer" }}>Refresh</button>
      </div>

      {status ? (
        <pre style={{ background: "#fff7ed", border: "1px solid #fed7aa", padding: 12, borderRadius: 10 }}>{status}</pre>
      ) : null}

      <div className="grid5">
        <Card title="Total" value={stats.total} />
        <Card title="Applied" value={stats.applied} />
        <Card title="Interview" value={stats.interview} sub={pct(stats.interviewRate)} />
        <Card title="Offers" value={stats.offer} sub={pct(stats.offerRate)} />
        <Card title="Rejected" value={stats.rejected} sub={pct(stats.rejectRate)} />
      </div>

      <div className="grid2">
        <div className="card cardPad">
          <h3 style={{ margin: "0 0 8px 0" }}>Funnel</h3>
          <FunnelRow label="Applied" n={stats.applied} total={stats.total} />
          <FunnelRow label="Interview" n={stats.interview} total={stats.total} />
          <FunnelRow label="Offer" n={stats.offer} total={stats.total} />
          <FunnelRow label="Rejected" n={stats.rejected} total={stats.total} />
          <div style={{ marginTop: 10, fontSize: 12, color: "#555" }}>
            “Success rate” (offer/total): <b>{pct(stats.offerRate)}</b>
          </div>
        </div>

        <div className="card cardPad">
          <h3 style={{ margin: "0 0 8px 0" }}>By stage</h3>
          {topStages.length === 0 ? (
            <div style={{ fontSize: 12, color: "#666" }}>No data yet.</div>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {topStages.map(([k,v]) => (
                <li key={k} style={{ fontSize: 13, marginBottom: 6 }}>
                  <b>{k}</b>: {v}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div style={{ marginTop: 14, border: "1px solid #eee", borderRadius: 14, padding: 12, background: "#fff" }}>
        <h3 style={{ margin: "0 0 8px 0" }}>Recent applications</h3>
        <table className="table">
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #eee" }}>
              <th style={{ padding: 8 }}>Company</th>
              <th style={{ padding: 8 }}>Role</th>
              <th style={{ padding: 8 }}>Stage</th>
              <th style={{ padding: 8 }}>Date</th>
              <th style={{ padding: 8 }}>URL</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice().sort((a,b)=> {
              const da = a.created_at ? Date.parse(a.created_at) : 0;
              const db = b.created_at ? Date.parse(b.created_at) : 0;
              return db - da;
            }).slice(0, 20).map((a) => (
              <tr key={a.id} style={{ borderBottom: "1px solid #f2f2f2" }}>
                <td style={{ padding: 8 }}>{a.company}</td>
                <td style={{ padding: 8 }}>{a.role}</td>
                <td style={{ padding: 8 }}>{a.stage || "applied"}</td>
                <td style={{ padding: 8 }}>{a.created_at ? new Date(a.created_at).toLocaleDateString() : "-"}</td>
                <td style={{ padding: 8 }}>
                  {a.url ? <a href={a.url} target="_blank" rel="noreferrer">open</a> : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}

function Card({ title, value, sub }) {
  return (
    <div className="card cardPad">
      <div className="kpiTitle">{title}</div>
      <div className="kpiValue">{value}</div>
      {sub ? <div className="small" style={{ marginTop: 2 }}>{sub}</div> : null}
    </div>
  );
}

function FunnelRow({ label, n, total }) {
  const ratio = total ? n / total : 0;
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#333" }}>
        <span>{label}</span>
        <span><b>{n}</b> ({pct(ratio)})</span>
      </div>
      <div style={{ height: 10, background: "#f3f4f6", borderRadius: 999, overflow: "hidden", marginTop: 6 }}>
        <div style={{ height: "100%", width: `${Math.max(2, ratio*100)}%`, background: "#111827" }} />
      </div>
    </div>
  );
}
