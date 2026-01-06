"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "../lib/api";
import { track } from "../lib/analytics";
import TopbarClient from "../components/TopbarClient";
import StageBadge from "../components/StageBadge";

const STAGES = ["applied", "interview", "offer", "rejected"];

function stageNormalize(s) {
  const v = (s || "applied").toLowerCase();
  return STAGES.includes(v) ? v : "applied";
}

export default function ApplicationsPage() {
  const [view, setView] = useState("kanban"); // kanban | list

  // list state
  const [listItems, setListItems] = useState([]);
  const [listTotal, setListTotal] = useState(0);
  const [listPage, setListPage] = useState(1);
  const [listPageSize, setListPageSize] = useState(50);

  // filters
  const [q, setQ] = useState("");
  const [filterStage, setFilterStage] = useState(""); // list-only stage filter
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [status, setStatus] = useState("");

  // kanban state
  const [kb, setKb] = useState(() => ({
    applied: { items: [], total: 0, page: 1, page_size: 25 },
    interview: { items: [], total: 0, page: 1, page_size: 25 },
    offer: { items: [], total: 0, page: 1, page_size: 25 },
    rejected: { items: [], total: 0, page: 1, page_size: 25 },
  }));
  const [dragOverStage, setDragOverStage] = useState("");

  // user scope
  const [userId, setUserId] = useState("u1");

  // debounce + request canceling (prevents out-of-order updates)
  const reqSeq = useRef(0);

  useEffect(() => {
    const read = () => {
      try {
        setUserId(localStorage.getItem("careeros_user_id") || "u1");
      } catch {}
    };
    read();

    const onScope = () => read();
    const onStorage = (e) => {
      if (e.key === "careeros_user_id" || e.key === "careeros_scope") read();
    };

    window.addEventListener("careeros:scope", onScope);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("careeros:scope", onScope);
      window.removeEventListener("storage", onStorage);
    };
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

  async function loadList({ page = listPage, pageSize = listPageSize } = {}) {
    const my = ++reqSeq.current;
    try {
      setStatus("Loading list…");
      const params = buildCommonParams({
        page: String(page),
        page_size: String(pageSize),
        view_mode: "paged",
        ...(filterStage ? { stage: filterStage } : {}),
      });
      const data = await apiFetch(`/v1/applications?${params.toString()}`);
      if (my !== reqSeq.current) return;

      setListItems(
        (data.items || []).map((x) => ({
          ...x,
          stage: stageNormalize(x.stage),
        }))
      );
      setListTotal(data.total || 0);
      setStatus("");
    } catch (e) {
      if (my !== reqSeq.current) return;
      setStatus(`Error: ${e.message}`);
    }
  }

  async function loadKanbanStage(stage, override = {}) {
    try {
      const cur = kb[stage];
      const params = buildCommonParams({
        stage,
        view_mode: "kanban",
        page: String(override.page ?? cur.page),
        page_size: String(override.page_size ?? cur.page_size),
      });
      const data = await apiFetch(`/v1/applications?${params.toString()}`);

      setKb((prev) => ({
        ...prev,
        [stage]: {
          ...prev[stage],
          items: (data.items || []).map((x) => ({
            ...x,
            stage: stageNormalize(x.stage),
          })),
          total: data.total || 0,
          page: data.page || override.page || prev[stage].page,
          page_size:
            data.page_size || override.page_size || prev[stage].page_size,
        },
      }));
      setStatus("");
    } catch (e) {
      if (my !== reqSeq.current) return;
      setStatus(`Error: ${e.message}`);
    }
  }

  async function loadKanbanAll() {
    const my = ++reqSeq.current;
    try {
      setStatus("Loading board…");
      // run sequentially to keep backend calmer (and simpler)
      for (const s of STAGES) {
        // eslint-disable-next-line no-await-in-loop
        await loadKanbanStage(s);
        if (my !== reqSeq.current) return;
      }
      setStatus("");
    } catch (e) {
      if (my !== reqSeq.current) return;
      setStatus(`Error: ${e.message}`);
    }
  }

  // ONE effect to reload when view/user/filters change (debounced)
  useEffect(() => {
    const t = setTimeout(() => {
      if (view === "list") {
        setListPage(1);
        loadList({ page: 1 });
      } else {
        setKb((prev) => {
          const next = { ...prev };
          for (const s of STAGES) next[s] = { ...next[s], page: 1 };
          return next;
        });
        loadKanbanAll();
      }
    }, 250);

    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, userId, q, filterStage, dateFrom, dateTo]);

  // list paging reload only
  useEffect(() => {
    if (view !== "list") return;
    loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listPage, listPageSize]);

  const listPageCount = useMemo(
    () => Math.max(1, Math.ceil(listTotal / listPageSize)),
    [listTotal, listPageSize]
  );

  function findMovedFromBoard(prevKb, id) {
    const sid = String(id);
    for (const s of STAGES) {
      const found = prevKb[s].items.find((x) => String(x.id) === sid);
      if (found) return found;
    }
    return null;
  }

  async function updateStage(idRaw, stage) {
    const id = String(idRaw);
    const nextStage = stageNormalize(stage);

    // optimistic update across list + kanban
    setListItems((prev) =>
      prev.map((x) => (String(x.id) === id ? { ...x, stage: nextStage } : x))
    );

    setKb((prev) => {
      const nextKb = { ...prev };
      const moved = findMovedFromBoard(prev, id);

      // remove from all columns
      for (const s of STAGES) {
        nextKb[s] = {
          ...nextKb[s],
          items: nextKb[s].items.filter((x) => String(x.id) !== id),
        };
      }

      // add to top of target column
      if (moved) {
        nextKb[nextStage] = {
          ...nextKb[nextStage],
          items: [{ ...moved, stage: nextStage }, ...nextKb[nextStage].items],
        };
      }
      return nextKb;
    });

    try {
      await apiFetch(`/v1/applications/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ stage: nextStage }),
      });

      // refresh target column (and list if needed)
      if (view === "list") loadList();
      else loadKanbanStage(nextStage);
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
    const id = e.dataTransfer.getData("text/plain"); // string id
    setDragOverStage("");
    if (!id) return;
    updateStage(id, stage);
  }

  function onDragOver(e, stage) {
    e.preventDefault();
    setDragOverStage(stage);
  }

  // UI helpers
  const viewButton = (label, value) => (
    <button
      className={`btn ${view === value ? "btnPrimary" : "btnGhost"}`}
      onClick={() => setView(value)}
      type="button"
    >
      {label}
    </button>
  );

  return (
    <main className="container">
      <TopbarClient
        title="Applications"
        subtitle="Cleaner UI + fewer requests. Kanban uses per-column pagination."
      />

      {/* Toolbar */}
      <div className="card cardPad" style={{ marginBottom: 12 }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr",
            gap: 10,
          }}
        >
          {/* row 1: view + status */}
          <div
            style={{
              display: "flex",
              gap: 8,
              alignItems: "center",
              flexWrap: "wrap",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {viewButton("Kanban", "kanban")}
              {viewButton("List", "list")}
              <span className="chip">user: {userId}</span>
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {status ? <span className="small">{status}</span> : null}
              <button
                className="btn btnGhost"
                onClick={() => (view === "list" ? loadList() : loadKanbanAll())}
                type="button"
              >
                Refresh
              </button>
            </div>
          </div>

          {/* row 2: filters */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "2fr 1fr 1fr 1fr",
              gap: 10,
              alignItems: "center",
            }}
          >
            <input
              className="input"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search company / role / url…"
            />

            {view === "list" ? (
              <select
                className="select"
                value={filterStage}
                onChange={(e) => setFilterStage(e.target.value)}
              >
                <option value="">All stages</option>
                {STAGES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            ) : (
              <div className="chip" style={{ justifySelf: "start" }}>
                Drag cards between columns
              </div>
            )}

            <input
              className="input"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              placeholder="From (YYYY-MM-DD)"
            />
            <input
              className="input"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              placeholder="To (YYYY-MM-DD)"
            />
          </div>
        </div>
      </div>

      {/* List */}
      {view === "list" ? (
        <>
          <div
            className="card cardPad"
            style={{
              marginBottom: 12,
              display: "flex",
              gap: 10,
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
            }}
          >
            <div className="small">
              Page <b>{listPage}</b> / {listPageCount} • Total{" "}
              <b>{listTotal}</b>
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button
                className="btn"
                disabled={listPage <= 1}
                onClick={() => setListPage((p) => Math.max(1, p - 1))}
                type="button"
              >
                Prev
              </button>
              <button
                className="btn"
                disabled={listPage >= listPageCount}
                onClick={() =>
                  setListPage((p) => Math.min(listPageCount, p + 1))
                }
                type="button"
              >
                Next
              </button>

              <span className="small" style={{ marginLeft: 6 }}>
                Page size
              </span>
              <select
                className="select"
                value={listPageSize}
                onChange={(e) => {
                  setListPage(1);
                  setListPageSize(Number(e.target.value));
                }}
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={200}>200</option>
              </select>
            </div>
          </div>

          <div className="card" style={{ overflow: "hidden" }}>
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: "22%" }}>Company</th>
                  <th style={{ width: "26%" }}>Role</th>
                  <th style={{ width: "14%" }}>Source</th>
                  <th style={{ width: "16%" }}>Stage</th>
                  <th style={{ width: "12%" }}>Date</th>
                  <th style={{ width: "10%" }}>Resume</th>
                  <th style={{ width: "10%" }}>URL</th>
                </tr>
              </thead>
              <tbody>
                {listItems.map((a) => (
                  <tr key={a.id}>
                    <td style={{ fontWeight: 600 }}>{a.company}</td>
                    <td>{a.role}</td>
                    <td className="small">{a.source_site || "-"}</td>
                    <td>
                      <select
                        className="select"
                        value={stageNormalize(a.stage)}
                        onChange={(e) => updateStage(a.id, e.target.value)}
                      >
                        {STAGES.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="small">
                      {a.created_at
                        ? new Date(a.created_at).toLocaleDateString()
                        : "-"}
                    </td>
                    <td>
                      {a.resume_docx_download_url ? (
                        <a
                          href={a.resume_docx_download_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          resume
                        </a>
                      ) : (
                        <span className="small muted">—</span>
                      )}
                    </td>
                    <td>
                      {a.url ? (
                        <a href={a.url} target="_blank" rel="noreferrer">
                          open
                        </a>
                      ) : (
                        <span className="small muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
                {!listItems.length ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="small muted"
                      style={{ padding: 14 }}
                    >
                      No items
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        /* Kanban */
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, minmax(240px, 1fr))",
            gap: 12,
            alignItems: "start",
            overflowX: "auto",
            paddingBottom: 4,
          }}
        >
          {STAGES.map((stage) => {
            const col = kb[stage];
            const pageCount = Math.max(1, Math.ceil(col.total / col.page_size));

            return (
              <div
                key={stage}
                className="card"
                style={{
                  minWidth: 240,
                  display: "flex",
                  flexDirection: "column",
                  maxHeight: "calc(100vh - 260px)",
                }}
              >
                {/* Sticky header */}
                <div
                  className="cardPad"
                  style={{
                    position: "sticky",
                    top: 0,
                    background: "var(--card-bg, rgba(15,23,42,.95))",
                    backdropFilter: "blur(10px)",
                    zIndex: 2,
                    borderBottom: "1px solid rgba(255,255,255,.08)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 10,
                    }}
                  >
                    <div
                      style={{ display: "flex", alignItems: "center", gap: 8 }}
                    >
                      <div
                        style={{ fontWeight: 800, textTransform: "capitalize" }}
                      >
                        {stage}
                      </div>
                      <span className="chip">{col.total}</span>
                    </div>
                    <div className="small muted">
                      {col.page}/{pageCount}
                    </div>
                  </div>

                  {/* Paging (clean + compact) */}
                  <div
                    style={{
                      display: "flex",
                      gap: 8,
                      alignItems: "center",
                      marginTop: 10,
                    }}
                  >
                    <button
                      className="btn"
                      disabled={col.page <= 1}
                      onClick={() => {
                        const nextPage = Math.max(1, col.page - 1);
                        setKb((p) => ({
                          ...p,
                          [stage]: { ...p[stage], page: nextPage },
                        }));
                        loadKanbanStage(stage, { page: nextPage });
                      }}
                      type="button"
                    >
                      Prev
                    </button>

                    <button
                      className="btn"
                      disabled={col.page >= pageCount}
                      onClick={() => {
                        const nextPage = Math.min(pageCount, col.page + 1);
                        setKb((p) => ({
                          ...p,
                          [stage]: { ...p[stage], page: nextPage },
                        }));
                        loadKanbanStage(stage, { page: nextPage });
                      }}
                      type="button"
                    >
                      Next
                    </button>

                    <div style={{ flex: 1 }} />

                    <select
                      className="select"
                      value={col.page_size}
                      onChange={(e) => {
                        const nextSize = Number(e.target.value);
                        setKb((p) => ({
                          ...p,
                          [stage]: {
                            ...p[stage],
                            page: 1,
                            page_size: nextSize,
                          },
                        }));
                        loadKanbanStage(stage, {
                          page: 1,
                          page_size: nextSize,
                        });
                      }}
                    >
                      <option value={10}>10</option>
                      <option value={25}>25</option>
                      <option value={50}>50</option>
                      <option value={100}>100</option>
                    </select>
                  </div>
                </div>

                {/* Drop zone / scroll list */}
                <div
                  onDragOver={(e) => onDragOver(e, stage)}
                  onDragLeave={() => setDragOverStage("")}
                  onDrop={(e) => onDrop(e, stage)}
                  style={{
                    padding: 10,
                    flex: 1,
                    overflowY: "auto",
                    borderTop: "1px solid rgba(255,255,255,.06)",
                    background:
                      dragOverStage === stage
                        ? "rgba(96,165,250,.08)"
                        : "transparent",
                    transition: "background 120ms ease",
                  }}
                >
                  {col.items.map((a) => (
                    <div
                      key={a.id}
                      draggable
                      onDragStart={(e) => onDragStart(e, a.id)}
                      style={{
                        padding: 12,
                        borderRadius: 14,
                        border: "1px solid rgba(255,255,255,.10)",
                        background: "rgba(2,6,23,.35)",
                        marginBottom: 10,
                        cursor: "grab",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          gap: 10,
                          alignItems: "flex-start",
                        }}
                      >
                        <div style={{ minWidth: 0 }}>
                          <div
                            style={{
                              fontWeight: 800,
                              lineHeight: 1.2,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                            title={a.company || ""}
                          >
                            {a.company}
                          </div>
                          <div
                            className="small muted"
                            style={{
                              marginTop: 4,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                            title={a.role || ""}
                          >
                            {a.role}
                          </div>
                        </div>
                        <StageBadge stage={a.stage} />
                      </div>

                      <div
                        className="small"
                        style={{
                          marginTop: 10,
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: 10,
                        }}
                      >
                        <span className="muted">
                          {a.created_at
                            ? new Date(a.created_at).toLocaleDateString()
                            : "—"}
                        </span>
                        {a.resume_pdf_download_url ||
                        a.resume_docx_download_url ? (
                          <a
                            onClick={() =>
                              track("Resume Downloaded", {
                                appId: a.id,
                                type: "docx",
                              })
                            }
                            href={a.resume_docx_download_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            resume
                          </a>
                        ) : (
                          <span className="muted">—</span>
                        )}

                        {a.url ? (
                          <a href={a.url} target="_blank" rel="noreferrer">
                            open
                          </a>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </div>
                    </div>
                  ))}

                  {!col.items.length ? (
                    <div
                      className="small muted"
                      style={{
                        padding: 14,
                        border: "1px dashed rgba(255,255,255,.18)",
                        borderRadius: 14,
                        textAlign: "center",
                      }}
                    >
                      No items
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Mobile-friendly grid fallback */}
      <style jsx>{`
        @media (max-width: 980px) {
          .cardPad :global(.input),
          .cardPad :global(.select) {
            width: 100%;
          }
        }
      `}</style>
    </main>
  );
}
