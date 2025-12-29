"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
export default function DocumentsPage() {
  // This page is the Base Resume editor (backed by the base_resumes table).
  const [items, setItems] = useState([]); // { user_id, title, content_text, updated_at }
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch(`/v1/base-resumes`);
      const next = data?.items || [];
      setItems(next);
      // Auto-select first user in list
      if (!selectedUserId && next.length > 0) {
        setSelectedUserId(next[0].user_id);
        setContent(next[0].content_text || "");
      }
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    // When switching user (or list refreshes), update editor content from the list.
    const row = items.find((x) => x.user_id === selectedUserId);
    if (row) setContent(row.content_text || "");
  }, [selectedUserId, items]);

  function preview(text, n = 180) {
    const t = (text || "").trim().replace(/\s+/g, " ");
    return t.length <= n ? t : t.slice(0, n) + "…";
  }

  async function save() {
    if (!selectedUserId) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch(`/v1/users/${selectedUserId}/base-resume`, {
        method: "PUT",
        body: JSON.stringify({ content_text: content }),
      });
      await refresh();
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ maxWidth: 1100 }}>
      <h1>Base Resumes</h1>

      {error && (
        <div
          style={{
            margin: "10px 0 16px",
            padding: 12,
            borderRadius: 10,
            border: "1px solid rgba(255,0,0,0.25)",
            background: "rgba(255,0,0,0.08)",
            whiteSpace: "pre-wrap",
          }}
        >
          {error}
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "360px 1fr",
          gap: 16,
          alignItems: "start",
        }}
      >
        {/* List */}
        <div
          style={{
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 12,
            padding: 12,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 10,
            }}
          >
            <strong>Resumes list</strong>
            <button
              className="btn btnGhost"
              onClick={refresh}
              disabled={loading}
            >
              {loading ? "Loading…" : "Refresh"}
            </button>
          </div>

          {items.length === 0 && !loading && (
            <div style={{ color: "#8aa" }}>No users / base resumes yet.</div>
          )}

          <div style={{ display: "grid", gap: 10 }}>
            {items.map((x) => {
              const active = x.user_id === selectedUserId;
              return (
                <button
                  key={x.user_id}
                  onClick={() => setSelectedUserId(x.user_id)}
                  style={{
                    textAlign: "left",
                    padding: 10,
                    borderRadius: 10,
                    border: active
                      ? "1px solid rgba(255,255,255,0.25)"
                      : "1px solid rgba(255,255,255,0.08)",
                    background: active
                      ? "rgba(255,255,255,0.08)"
                      : "rgba(0,0,0,0.10)",
                    cursor: "pointer",
                    color: active ? "white" : "#ccc",
                  }}
                >
                  <div style={{ fontWeight: 600 }}>{x.title || x.user_id}</div>
                  <div style={{ fontSize: 12, opacity: 0.8, marginTop: 6 }}>
                    {preview(x.content_text)}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Editor */}
        <div
          style={{
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 12,
            padding: 12,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 10,
              marginBottom: 10,
            }}
          >
            <div>
              <strong>Base resume</strong>
              {selectedUserId && (
                <span style={{ marginLeft: 8, opacity: 0.7, fontSize: 12 }}>
                  ({selectedUserId})
                </span>
              )}
            </div>
            <button
              className="btn btnGhost"
              onClick={save}
              disabled={saving || !selectedUserId}
            >
              {saving ? "Saving…" : "Save / Update"}
            </button>
          </div>

          <textarea
            rows={18}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Paste the base resume here…"
            style={{ width: "100%" }}
          />

          <div style={{ marginTop: 8, fontSize: 12, opacity: 0.75 }}>
            This updates the base_resumes table via
            <code style={{ marginLeft: 6 }}>
              /v1/users/&lt;user_id&gt;/base-resume
            </code>
          </div>
        </div>
      </div>
    </div>
  );
}
