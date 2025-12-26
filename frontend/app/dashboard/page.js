'use client';

import { useEffect, useMemo, useState } from "react";
import TopbarClient from "../components/TopbarClient";
import { apiFetch } from "../lib/api";
import {
  ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  PieChart, Pie, Cell, Legend
} from "recharts";

const COLORS = ["#60a5fa", "#34d399", "#a78bfa", "#f87171", "#fbbf24", "#22c55e"];

function kpiSub(label, value) {
  return (
    <div className="small" style={{ marginTop: 2 }}>
      {label}: <b>{value}</b>
    </div>
  );
}

export default function DashboardPage() {
  // NOTE: don't read localStorage during the initial render ...
  // can cause hydration mismatches. Read it after mount instead.
  const [userId, setUserId] = useState("u1");

  const [days, setDays] = useState(60);
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    const sync = () => {
      try {
        const v = localStorage.getItem("careeros_user_id") || "u1";
        setUserId(v);
      } catch {}
    };
    sync();
    const onStorage = (e) => {
      if (e.key === "careeros_user_id") sync();
    };
    window.addEventListener("storage", onStorage);
    window.addEventListener("careeros:user-changed", sync);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("careeros:user-changed", sync);
    };
  }, []);

  async function load() {
    try {
      setStatus("Loading...");
      const params = new URLSearchParams({ user_id: userId, days: String(days) });
      const d = await apiFetch(`/v1/applications/stats?${params.toString()}`);
      setData(d);
      setStatus("");
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [days, userId]);

  const stagePie = useMemo(() => {
    if (!data?.stage_counts) return [];
    const map = data.stage_counts;
    return Object.keys(map).map((k) => ({ name: k, value: map[k] })).sort((a,b)=>b.value-a.value);
  }, [data]);

  return (
    <main className="container">
      <TopbarClient title="Dashboard" subtitle="Fast view of your pipeline health + trends." />

      <div className="card cardPad" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span className="chip">user: {userId}</span>
          <span className="chip">window: last {days} days</span>
          <select className="select" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={1}>1 day</option>
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={180}>180 days</option>
            <option value={365}>365 days</option>
          </select>
          <button className="btn btnGhost" onClick={load}>Refresh</button>
          {status ? <span className="small">{status}</span> : null}
        </div>
      </div>

      <div className="grid5" style={{ marginBottom: 12 }}>
        <div className="card cardPad">
          <div className="kpiTitle">Total applications</div>
          <div className="kpiValue">{data?.total ?? "—"}</div>
          {kpiSub("Success rate", data ? `${Math.round((data.success_rate||0) * 100)}%` : "—")}
        </div>
        <div className="card cardPad">
          <div className="kpiTitle">Applied</div>
          <div className="kpiValue">{data?.applied_count ?? "—"}</div>
          {kpiSub("Interview rate", data ? `${Math.round((data.interview_rate||0) * 100)}%` : "—")}
        </div>
        <div className="card cardPad">
          <div className="kpiTitle">Interview</div>
          <div className="kpiValue">{data?.interview_count ?? "—"}</div>
          <div className="small" style={{ marginTop: 2 }}>Keep pushing.</div>
        </div>
        <div className="card cardPad">
          <div className="kpiTitle">Offer</div>
          <div className="kpiValue">{data?.offer_count ?? "—"}</div>
          <div className="small" style={{ marginTop: 2 }}>🎯</div>
        </div>
        <div className="card cardPad">
          <div className="kpiTitle">Rejected</div>
          <div className="kpiValue">{data?.rejected_count ?? "—"}</div>
          {kpiSub("Rejection rate", data ? `${Math.round((data.rejection_rate||0) * 100)}%` : "—")}
        </div>
      </div>

      <div className="grid2">
        <div className="card cardPad">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
            <div>
              <div className="kpiTitle">Applications by date</div>
              <div className="small">Counts per day (last {days} days)</div>
            </div>
          </div>

          <div style={{ width: "100%", height: 320 }}>
            <ResponsiveContainer>
              <LineChart data={data?.series_daily || []}>
                <CartesianGrid stroke="rgba(255,255,255,.10)" />
                <XAxis dataKey="day" tick={{ fill: "rgba(255,255,255,.55)", fontSize: 11 }} />
                <YAxis tick={{ fill: "rgba(255,255,255,.55)", fontSize: 11 }} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "rgba(15,23,42,.9)", border: "1px solid rgba(255,255,255,.12)", borderRadius: 12, color: "white" }} />
                <Line type="monotone" dataKey="count" stroke="#60a5fa" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card cardPad">
          <div className="kpiTitle">Stage distribution</div>
          <div className="small">Where your pipeline is concentrated</div>

          <div style={{ width: "100%", height: 320, marginTop: 10 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie data={stagePie} dataKey="value" nameKey="name" innerRadius={65} outerRadius={110} paddingAngle={3}>
                  {stagePie.map((_, idx) => (
                    <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                  ))}
                </Pie>
                <Legend />
                <Tooltip contentStyle={{ background: "rgba(15,23,42,.9)", border: "1px solid rgba(255,255,255,.12)", borderRadius: 12, color: "white" }} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="small" style={{ marginTop: 10 }}>
            Tip: if the pie is mostly <b>applied</b>, focus on improving conversion to <b>interview</b>.
          </div>
        </div>
      </div>
    </main>
  );
}
