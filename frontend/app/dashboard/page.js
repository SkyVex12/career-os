"use client";

import { useEffect, useMemo, useState } from "react";
import TopbarClient from "../components/TopbarClient";
import { apiFetch } from "../lib/api";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
  Legend,
  BarChart,
  Bar,
} from "recharts";
import { useScope } from "../components/ClientShell";

const COLORS = [
  "#60a5fa",
  "#34d399",
  "#a78bfa",
  "#f87171",
  "#fbbf24",
  "#22c55e",
];

function kpiSub(label, value) {
  return (
    <div className="small" style={{ marginTop: 2 }}>
      {label}: <b>{value}</b>
    </div>
  );
}

function todayLocalISODate() {
  // YYYY-MM-DD in the user's local timezone
  const d = new Date();
  const localMidnight = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  return localMidnight.toISOString().slice(0, 10);
}

function pct1(x) {
  return `${Math.round((x || 0) * 1000) / 10}%`;
}

export default function DashboardPage() {
  // NOTE: don't read localStorage during the initial render ...
  // can cause hydration mismatches. Read it after mount instead.
  const [userId, setUserId] = useState("u1");
  const { scope, principal } = useScope();

  const effectivelyUserId =
    principal?.type === "user"
      ? principal.user_id
      : scope?.mode === "user"
        ? scope.userId
        : null;

  const [days, setDays] = useState(1);

  // ✅ NEW: day selector used when days === 1
  // Passed to backend as ?days=1&day=YYYY-MM-DD
  const [selectedDay, setSelectedDay] = useState(todayLocalISODate());

  const [data, setData] = useState(null);
  const [status, setStatus] = useState("");

  // ✅ NEW: source site controls
  const [sourceMetric, setSourceMetric] = useState("interview_rate"); // or "success_rate"
  const [minN, setMinN] = useState(5);

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
      const params = new URLSearchParams({
        ...(effectivelyUserId ? { user_id: effectivelyUserId } : {}),
        days: String(days),
        ...(days === 1 && selectedDay ? { day: selectedDay } : {}),
      });
      const d = await apiFetch(`/v1/applications/stats?${params.toString()}`);
      setData(d);
      setStatus("");
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  }

  useEffect(() => {
    load(); /* eslint-disable-next-line */
  }, [days, effectivelyUserId, selectedDay]);

  const stagePie = useMemo(() => {
    if (!data?.stage_counts) return [];
    const map = data.stage_counts;
    return Object.keys(map)
      .map((k) => ({ name: k, value: map[k] }))
      .sort((a, b) => b.value - a.value);
  }, [data]);

  const series = data?.series || data?.series_daily || [];
  const unit = data?.series_unit || "day"; // fallback for old API
  const xKey = unit === "hour" ? "time" : "day";

  // ✅ NEW: Source site computed rows
  const sourceRows = useMemo(() => {
    const rows = data?.source_site_stats || [];
    const filtered = rows.filter((r) => (r.total || 0) >= minN);

    filtered.sort(
      (a, b) =>
        (b[sourceMetric] || 0) - (a[sourceMetric] || 0) ||
        (b.total || 0) - (a.total || 0),
    );

    return filtered;
  }, [data, sourceMetric, minN]);

  const sourceBars = useMemo(() => {
    return (sourceRows || []).slice(0, 8).map((r) => ({
      source_site: r.source_site,
      rate: Math.round((r[sourceMetric] || 0) * 1000) / 10, // percent with 1 decimal
      total: r.total,
    }));
  }, [sourceRows, sourceMetric]);

  return (
    <main className="container">
      <TopbarClient
        title="Dashboard"
        subtitle="Fast view of your pipeline health + trends."
      />

      <div className="card cardPad" style={{ marginBottom: 12 }}>
        <div
          style={{
            display: "flex",
            gap: 10,
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <span className="chip">user: {effectivelyUserId}</span>
          <span className="chip">window: last {days} days</span>

          <select
            className="select"
            value={days}
            onChange={(e) => {
              const next = Number(e.target.value);
              setDays(next);

              // ✅ when switching to 1 day, ensure we have a selectedDay
              if (next === 1 && !selectedDay) {
                setSelectedDay(todayLocalISODate());
              }
            }}
          >
            <option value={1}>1 day</option>
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={180}>180 days</option>
            <option value={365}>365 days</option>
          </select>

          {/* ✅ NEW: day picker shown only when days === 1 */}
          {days === 1 ? (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span className="small">Day:</span>
              <input
                className="select"
                type="date"
                value={selectedDay || ""}
                onChange={(e) => setSelectedDay(e.target.value || "")}
                style={{ minWidth: 160 }}
              />
            </div>
          ) : null}

          <button className="btn btnGhost" onClick={load}>
            Refresh
          </button>

          {status ? <span className="small">{status}</span> : null}
        </div>

        {/* Optional: show which day is pinned when in 1-day mode */}
        {days === 1 && selectedDay ? (
          <div className="small" style={{ marginTop: 8, opacity: 0.8 }}>
            Showing hourly counts for: <b>{selectedDay}</b>
          </div>
        ) : null}
      </div>

      <div className="grid5" style={{ marginBottom: 12 }}>
        <div className="card cardPad">
          <div className="kpiTitle">Total applications</div>
          <div className="kpiValue">{data?.total ?? "—"}</div>
          {kpiSub(
            "Success rate",
            data ? `${Math.round((data.success_rate || 0) * 100)}%` : "—",
          )}
        </div>
        <div className="card cardPad">
          <div className="kpiTitle">Applied</div>
          <div className="kpiValue">{data?.applied_count ?? "—"}</div>
          {kpiSub(
            "Interview rate",
            data ? `${Math.round((data.interview_rate || 0) * 100)}%` : "—",
          )}
        </div>
        <div className="card cardPad">
          <div className="kpiTitle">Interview</div>
          <div className="kpiValue">{data?.interview_count ?? "—"}</div>
          <div className="small" style={{ marginTop: 2 }}>
            Keep pushing.
          </div>
        </div>
        <div className="card cardPad">
          <div className="kpiTitle">Offer</div>
          <div className="kpiValue">{data?.offer_count ?? "—"}</div>
          <div className="small" style={{ marginTop: 2 }}>
            🎯
          </div>
        </div>
        <div className="card cardPad">
          <div className="kpiTitle">Rejected</div>
          <div className="kpiValue">{data?.rejected_count ?? "—"}</div>
          {kpiSub(
            "Rejection rate",
            data ? `${Math.round((data.rejection_rate || 0) * 100)}%` : "—",
          )}
        </div>
      </div>

      <div className="grid2">
        <div className="card cardPad">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              marginBottom: 10,
            }}
          >
            <div>
              <div className="kpiTitle">Applications by date</div>
              <div className="small">
                Counts per {unit === "hour" ? "hour" : "day"} (last {days} day
                {days > 1 ? "s" : ""})
              </div>

              {unit !== "hour" ? (
                <div className="small" style={{ opacity: 0.75, marginTop: 2 }}>
                  Tip: click a day on the chart to drill into hourly view.
                </div>
              ) : null}
            </div>
          </div>

          <div style={{ width: "100%", height: 320 }}>
            <ResponsiveContainer>
              <LineChart
                data={series}
                // ✅ NEW: click-to-drill when chart is daily
                onClick={(e) => {
                  if (unit === "hour") return;
                  const label = e?.activeLabel; // should be "YYYY-MM-DD"
                  if (!label) return;
                  setSelectedDay(label);
                  setDays(1);
                }}
              >
                <CartesianGrid stroke="rgba(255,255,255,.10)" />
                <XAxis
                  dataKey={xKey}
                  tick={{ fill: "rgba(255,255,255,.55)", fontSize: 11 }}
                  tickFormatter={(v) => {
                    if (unit !== "hour") return v;
                    // v like "2025-12-29 13:00" -> "13:00"
                    const parts = String(v).split(" ");
                    return parts[1] || v;
                  }}
                />

                <YAxis
                  tick={{ fill: "rgba(255,255,255,.55)", fontSize: 11 }}
                  allowDecimals={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "rgba(15,23,42,.9)",
                    border: "1px solid rgba(255,255,255,.12)",
                    borderRadius: 12,
                    color: "white",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke="#60a5fa"
                  strokeWidth={2}
                  dot={false}
                />
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
                <Pie
                  data={stagePie}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={65}
                  outerRadius={110}
                  paddingAngle={3}
                >
                  {stagePie.map((_, idx) => (
                    <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                  ))}
                </Pie>
                <Legend />
                <Tooltip
                  contentStyle={{
                    background: "rgba(15,23,42,.9)",
                    border: "1px solid rgba(255,255,255,.12)",
                    borderRadius: 12,
                    color: "white",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="small" style={{ marginTop: 10 }}>
            Tip: if the pie is mostly <b>applied</b>, focus on improving
            conversion to <b>interview</b>.
          </div>
        </div>
      </div>

      {/* ✅ NEW: Source site performance */}
      <div className="card cardPad" style={{ marginTop: 12 }}>
        <div
          style={{
            display: "flex",
            gap: 10,
            alignItems: "center",
            flexWrap: "wrap",
            marginBottom: 10,
          }}
        >
          <div style={{ marginRight: "auto" }}>
            <div className="kpiTitle">Best source sites</div>
            <div className="small">
              Conversion by <code>source_site</code> (same window)
            </div>
          </div>

          <select
            className="select"
            value={sourceMetric}
            onChange={(e) => setSourceMetric(e.target.value)}
          >
            <option value="interview_rate">Interview rate</option>
            <option value="success_rate">Offer rate</option>
          </select>

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="small">Min n:</span>
            <input
              className="select"
              type="number"
              min={0}
              value={minN}
              onChange={(e) => setMinN(Number(e.target.value))}
              style={{ width: 90 }}
            />
          </div>
        </div>

        {!sourceRows || sourceRows.length === 0 ? (
          <div className="small" style={{ opacity: 0.8 }}>
            No source-site data yet (or all sources are below min n).
          </div>
        ) : (
          <div className="grid2">
            {/* Chart */}
            <div style={{ width: "100%", height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={sourceBars}>
                  <CartesianGrid stroke="rgba(255,255,255,.10)" />
                  <XAxis
                    dataKey="source_site"
                    tick={{ fill: "rgba(255,255,255,.55)", fontSize: 11 }}
                  />
                  <YAxis
                    tick={{ fill: "rgba(255,255,255,.55)", fontSize: 11 }}
                    allowDecimals={false}
                    unit="%"
                  />
                  <Tooltip
                    contentStyle={{
                      background: "rgba(15,23,42,.9)",
                      border: "1px solid rgba(255,255,255,.12)",
                      borderRadius: 12,
                      color: "white",
                    }}
                    formatter={(value) => [
                      `${value}%`,
                      sourceMetric === "interview_rate"
                        ? "Interview rate"
                        : "Offer rate",
                    ]}
                    labelFormatter={(label) => `Source: ${label}`}
                  />
                  <Bar dataKey="rate" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Table */}
            <div style={{ overflowX: "auto" }}>
              <table className="table" style={{ width: "100%" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Source</th>
                    <th style={{ textAlign: "right" }}>Total</th>
                    <th style={{ textAlign: "right" }}>Interview</th>
                    <th style={{ textAlign: "right" }}>Offer</th>
                    <th style={{ textAlign: "right" }}>
                      {sourceMetric === "interview_rate"
                        ? "Interview rate"
                        : "Offer rate"}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sourceRows.slice(0, 20).map((r) => (
                    <tr key={r.source_site}>
                      <td style={{ textAlign: "left" }}>{r.source_site}</td>
                      <td style={{ textAlign: "right" }}>{r.total}</td>
                      <td style={{ textAlign: "right" }}>
                        {r.interview_count}
                      </td>
                      <td style={{ textAlign: "right" }}>{r.offer_count}</td>
                      <td style={{ textAlign: "right" }}>
                        {pct1(r[sourceMetric])}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="small" style={{ marginTop: 8, opacity: 0.8 }}>
                Showing top 20 by{" "}
                {sourceMetric === "interview_rate" ? "interview" : "offer"} rate
                (min n {minN})
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
