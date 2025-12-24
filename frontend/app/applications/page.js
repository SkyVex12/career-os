'use client';

import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../lib/api";
import TopbarClient from "../components/TopbarClient";
import StageBadge from "../components/StageBadge";

const STAGES = ["applied", "interview", "offer", "rejected"];

function stageNormalize(s) {
  const v = (s || "applied").toLowerCase();
  return STAGES.includes(v) ? v : "applied";
}

export default function ApplicationsPage() {
  const [view, setView] = useState("kanban"); // kanban | list
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [q, setQ] = useState("");
  const [dragOverStage, setDragOverStage] = useState("");

  const userId = useMemo(() => {
    if (typeof window === "undefined") return "u1";
    return localStorage.getItem("careeros_user_id") || "u1";
  }, []);

  async function loadList() {
    try {
      setStatus("Loading list...");
      const params = new URLSearchParams({
        user_id: userId,
        page: String(page),
        page_size: String(pageSize),
      });
      const data = await apiFetch(`/v1/applications/paged?${params.toString()}`);
      setItems((data.items || []).map(x => ({ ...x, stage: stageNormalize(x.stage) })));
      setTotal(data.total || 0);
      setStatus("");
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  }

  async function loadKanban() {
    try {
      setStatus("Loading board...");
      const params = new URLSearchParams({ user_id: userId, limit: "2000" });
      const data = await apiFetch(`/v1/applications?${params.toString()}`);
      setItems((data || []).map(x => ({ ...x, stage: stageNormalize(x.stage) })));
      setTotal((data || []).length);
      setStatus("");
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  }

  useEffect(() => {
    if (view === "list") loadList();
    else loadKanban();
  }, [view, page, pageSize]);

  const filtered = useMemo(() => {
    if (!q.trim()) return items;
    const s = q.trim().toLowerCase();
    return items.filter(a =>
      (a.company || "").toLowerCase().includes(s) ||
      (a.role || "").toLowerCase().includes(s) ||
      (a.url || "").toLowerCase().includes(s)
    );
  }, [items, q]);

  const byStage = useMemo(() => {
    const map = { applied: [], interview: [], offer: [], rejected: [] };
    for (const a of filtered) map[stageNormalize(a.stage)].push(a);
    for (const k of STAGES) {
      map[k].sort((a,b) => (Date.parse(b.created_at||"")||0) - (Date.parse(a.created_at||"")||0));
    }
    return map;
  }, [filtered]);

  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  async function updateStage(id, stage) {
    const next = stageNormalize(stage);
    const prev = items;
    setItems(items.map(x => x.id === id ? { ...x, stage: next } : x));
    try {
      await apiFetch(`/v1/applications/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ stage: next }),
      });
    } catch (e) {
      setItems(prev);
      alert(e.message);
    }
  }

  function onDragStart(e, appId) {
    e.dataTransfer.setData("text/plain", String(appId));
    e.dataTransfer.effectAllowed = "move";
  }

  function onDrop(e, stage) {
    e.preventDefault();
    const id = Number(e.dataTransfer.getData("text/plain"));
    setDragOverStage("");
    if (!id) return;
    updateStage(id, stage);
  }

  function onDragOver(e, stage) {
    e.preventDefault();
    setDragOverStage(stage);
  }

  return (
    <main className="container">
      <TopbarClient
        title="Applications"
        subtitle="Manage with Kanban or a paginated list. Drag cards to change stage."
      />

      <div className="card cardPad" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <button className={`btn ${view==="kanban" ? "btnPrimary" : ""}`} onClick={() => { setView("kanban"); setPage(1); }}>
            Kanban
          </button>
          <button className={`btn ${view==="list" ? "btnPrimary" : ""}`} onClick={() => { setView("list"); setPage(1); }}>
            List
          </button>

          <div style={{ flex: 1 }} />

          <input className="input" style={{ width: 320 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search company, role, url..." />

          <span className="chip">{filtered.length} shown</span>
          <span className="chip">{total} loaded</span>
        </div>

        {view === "list" ? (
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
            <button className="btn" disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>Prev</button>
            <div className="small">Page <b>{page}</b> / {pageCount}</div>
            <button className="btn" disabled={page >= pageCount} onClick={() => setPage(p => Math.min(pageCount, p + 1))}>Next</button>

            <div style={{ width: 8 }} />
            <span className="small">Page size</span>
            <select className="select" value={pageSize} onChange={(e) => { setPage(1); setPageSize(Number(e.target.value)); }}>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>

            <button className="btn btnGhost" onClick={loadList}>Refresh</button>
          </div>
        ) : (
          <div className="small" style={{ marginTop: 10 }}>
            Tip: Drag a card into another column to update stage instantly.
          </div>
        )}

        {status ? <div className="small" style={{ marginTop: 10 }}>{status}</div> : null}
      </div>

      {view === "list" ? (
        <div className="card" style={{ overflow: "hidden" }}>
          <table className="table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Role</th>
                <th>Stage</th>
                <th>Applied</th>
                <th>URL</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((a) => (
                <tr key={a.id}>
                  <td>{a.company}</td>
                  <td>{a.role}</td>
                  <td>
                    <select className="select" value={stageNormalize(a.stage)} onChange={(e) => updateStage(a.id, e.target.value)}>
                      {STAGES.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="small">{a.created_at ? new Date(a.created_at).toLocaleDateString() : "-"}</td>
                  <td>{a.url ? <a href={a.url} target="_blank" rel="noreferrer">open</a> : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="kanban">
          {STAGES.map((stage) => (
            <div key={stage} className="card cardPad">
              <div className="columnHead">
                <div className="columnTitle" style={{ textTransform: "capitalize" }}>{stage}</div>
                <div className="columnCount">{(byStage[stage] || []).length}</div>
              </div>

              <div
                className={`dropZone ${dragOverStage === stage ? "over" : ""}`}
                onDragOver={(e) => onDragOver(e, stage)}
                onDragLeave={() => setDragOverStage("")}
                onDrop={(e) => onDrop(e, stage)}
              >
                {(byStage[stage] || []).slice(0, 250).map((a) => (
                  <div key={a.id} className="cardItem" draggable onDragStart={(e) => onDragStart(e, a.id)}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                      <h4>{a.company}</h4>
                      <StageBadge stage={a.stage} />
                    </div>
                    <p>{a.role}</p>
                    <div className="small" style={{ marginTop: 8, display: "flex", justifyContent: "space-between" }}>
                      <span>{a.created_at ? new Date(a.created_at).toLocaleDateString() : "-"}</span>
                      {a.url ? <a href={a.url} target="_blank" rel="noreferrer">open</a> : null}
                    </div>
                  </div>
                ))}
                {(byStage[stage] || []).length > 250 ? (
                  <div className="small muted">Showing first 250 in this column (search to narrow)</div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
