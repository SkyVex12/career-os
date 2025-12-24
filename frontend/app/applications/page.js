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

function isoDate(d) {
  if (!d) return "";
  return new Date(d).toISOString().slice(0, 10);
}

export default function ApplicationsPage() {
  const [view, setView] = useState("kanban"); // kanban | list
  const [listItems, setListItems] = useState([]);
  const [listTotal, setListTotal] = useState(0);
  const [listPage, setListPage] = useState(1);
  const [listPageSize, setListPageSize] = useState(50);

  const [q, setQ] = useState("");
  const [filterStage, setFilterStage] = useState(""); // list-only stage filter
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [status, setStatus] = useState("");

  // kanban: per-stage data + paging
  const [kb, setKb] = useState(() => ({
    applied: { items: [], total: 0, page: 1, page_size: 25 },
    interview: { items: [], total: 0, page: 1, page_size: 25 },
    offer: { items: [], total: 0, page: 1, page_size: 25 },
    rejected: { items: [], total: 0, page: 1, page_size: 25 },
  }));
  const [dragOverStage, setDragOverStage] = useState("");

  const userId = useMemo(() => {
    if (typeof window === "undefined") return "u1";
    return localStorage.getItem("careeros_user_id") || "u1";
  }, []);

  function buildCommonParams(extra = {}) {
    const params = new URLSearchParams({
      user_id: userId,
      ...(q.trim() ? { q: q.trim() } : {}),
      ...(dateFrom ? { date_from: dateFrom } : {}),
      ...(dateTo ? { date_to: dateTo } : {}),
      ...extra,
    });
    return params;
  }

  async function loadList() {
    try {
      setStatus("Loading list...");
      const params = buildCommonParams({
        page: String(listPage),
        page_size: String(listPageSize),
        ...(filterStage ? { stage: filterStage } : {}),
      });
      const data = await apiFetch(`/v1/applications/paged?${params.toString()}`);
      setListItems((data.items || []).map((x) => ({ ...x, stage: stageNormalize(x.stage) })));
      setListTotal(data.total || 0);
      setStatus("");
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  }

  async function loadKanbanStage(stage) {
    try {
      const cur = kb[stage];
      const params = buildCommonParams({
        stage,
        page: String(cur.page),
        page_size: String(cur.page_size),
      });
      const data = await apiFetch(`/v1/applications/kanban?${params.toString()}`);
      setKb((prev) => ({
        ...prev,
        [stage]: {
          ...prev[stage],
          items: (data.items || []).map((x) => ({ ...x, stage: stageNormalize(x.stage) })),
          total: data.total || 0,
          page: data.page || prev[stage].page,
          page_size: data.page_size || prev[stage].page_size,
        },
      }));
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  }

  async function loadKanbanAll() {
    setStatus("Loading board...");
    for (const s of STAGES) {
      // eslint-disable-next-line no-await-in-loop
      await loadKanbanStage(s);
    }
    setStatus("");
  }

  useEffect(() => {
    if (view === "list") loadList();
    else loadKanbanAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  // when filters change: reset paging and reload current view
  useEffect(() => {
    const t = setTimeout(() => {
      if (view === "list") {
        setListPage(1);
      } else {
        setKb((prev) => {
          const next = { ...prev };
          for (const s of STAGES) next[s] = { ...next[s], page: 1 };
          return next;
        });
      }
      if (view === "list") loadList();
      else loadKanbanAll();
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, filterStage, dateFrom, dateTo]);

  useEffect(() => {
    if (view === "list") loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listPage, listPageSize]);

  // kanban paging reload per stage
  useEffect(() => {
    if (view !== "kanban") return;
    for (const s of STAGES) loadKanbanStage(s);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kb.applied.page, kb.interview.page, kb.offer.page, kb.rejected.page,
      kb.applied.page_size, kb.interview.page_size, kb.offer.page_size, kb.rejected.page_size]);

  const listPageCount = Math.max(1, Math.ceil(listTotal / listPageSize));

  async function updateStage(id, stage) {
    const next = stageNormalize(stage);

    // optimistic update across list + kanban
    setListItems((prev) => prev.map((x) => (x.id === id ? { ...x, stage: next } : x)));
    setKb((prev) => {
      const nextKb = { ...prev };
      // remove from all columns
      for (const s of STAGES) {
        nextKb[s] = { ...nextKb[s], items: nextKb[s].items.filter((x) => x.id !== id) };
      }
      // add to top of target column
      const moved = listItems.find((x) => x.id === id) || null;
      if (moved) nextKb[next] = { ...nextKb[next], items: [{ ...moved, stage: next }, ...nextKb[next].items] };
      return nextKb;
    });

    try {
      await apiFetch(`/v1/applications/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ stage: next }),
      });
      // refresh the affected columns (and list)
      if (view === "list") loadList();
      else {
        await loadKanbanStage(next);
      }
    } catch (e) {
      alert(e.message);
      if (view === "list") loadList();
      else loadKanbanAll();
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
      <TopbarClient title="Applications" subtitle="Search + filter on backend. Kanban has per-column pagination." />

      <div className="card cardPad" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <button className={`btn ${view==="kanban" ? "btnPrimary" : ""}`} onClick={() => setView("kanban")}>Kanban</button>
          <button className={`btn ${view==="list" ? "btnPrimary" : ""}`} onClick={() => setView("list")}>List</button>

          <div style={{ flex: 1 }} />

          <input className="input" style={{ width: 320 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search (company / role / url)..." />

          {view === "list" ? (
            <select className="select" value={filterStage} onChange={(e) => setFilterStage(e.target.value)}>
              <option value="">All stages</option>
              {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          ) : (
            <span className="chip">Kanban = stages columns</span>
          )}

          <input className="input" style={{ width: 140 }} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} placeholder="date_from (YYYY-MM-DD)" />
          <input className="input" style={{ width: 140 }} value={dateTo} onChange={(e) => setDateTo(e.target.value)} placeholder="date_to (YYYY-MM-DD)" />

          <button className="btn btnGhost" onClick={() => (view==="list" ? loadList() : loadKanbanAll())}>Refresh</button>
        </div>

        {status ? <div className="small" style={{ marginTop: 10 }}>{status}</div> : null}

        {view === "list" ? (
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
            <button className="btn" disabled={listPage <= 1} onClick={() => setListPage((p) => Math.max(1, p - 1))}>Prev</button>
            <div className="small">Page <b>{listPage}</b> / {listPageCount} &nbsp;•&nbsp; Total <b>{listTotal}</b></div>
            <button className="btn" disabled={listPage >= listPageCount} onClick={() => setListPage((p) => Math.min(listPageCount, p + 1))}>Next</button>

            <div style={{ width: 8 }} />
            <span className="small">Page size</span>
            <select className="select" value={listPageSize} onChange={(e) => { setListPage(1); setListPageSize(Number(e.target.value)); }}>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
          </div>
        ) : (
          <div className="small" style={{ marginTop: 10 }}>
            Drag cards to move stages. Each column has its own pagination.
          </div>
        )}
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
              {listItems.map((a) => (
                <tr key={a.id}>
                  <td>{a.company}</td>
                  <td>{a.role}</td>
                  <td>
                    <select className="select" value={stageNormalize(a.stage)} onChange={(e) => updateStage(a.id, e.target.value)}>
                      {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
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
          {STAGES.map((stage) => {
            const col = kb[stage];
            const pageCount = Math.max(1, Math.ceil(col.total / col.page_size));
            return (
              <div key={stage} className="card cardPad">
                <div className="columnHead">
                  <div className="columnTitle" style={{ textTransform: "capitalize" }}>{stage}</div>
                  <div className="columnCount">{col.total}</div>
                </div>

                <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
                  <button className="btn" disabled={col.page <= 1} onClick={() => setKb((p) => ({ ...p, [stage]: { ...p[stage], page: Math.max(1, p[stage].page - 1) } }))}>Prev</button>
                  <div className="small">Page <b>{col.page}</b> / {pageCount}</div>
                  <button className="btn" disabled={col.page >= pageCount} onClick={() => setKb((p) => ({ ...p, [stage]: { ...p[stage], page: Math.min(pageCount, p[stage].page + 1) } }))}>Next</button>
                  <select className="select" value={col.page_size} onChange={(e) => setKb((p) => ({ ...p, [stage]: { ...p[stage], page: 1, page_size: Number(e.target.value) } }))}>
                    <option value={10}>10</option>
                    <option value={25}>25</option>
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                  </select>
                </div>

                <div
                  className={`dropZone ${dragOverStage === stage ? "over" : ""}`}
                  onDragOver={(e) => onDragOver(e, stage)}
                  onDragLeave={() => setDragOverStage("")}
                  onDrop={(e) => onDrop(e, stage)}
                >
                  {col.items.map((a) => (
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
                  {!col.items.length ? <div className="small muted">No items</div> : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
