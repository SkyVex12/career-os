"use client";

import { useEffect, useMemo, useState } from "react";
import { apiFetch, getToken } from "../lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export default function DocumentsPage() {
  const [items, setItems] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [templatePreviewUrl, setTemplatePreviewUrl] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [uploadingTemplate, setUploadingTemplate] = useState(false);
  const [error, setError] = useState(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch("/v1/base-resumes");
      const next = data?.items || [];
      setItems(next);
      if (!selectedUserId && next.length > 0) {
        setSelectedUserId(next[0].user_id);
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

  const selectedItem = useMemo(
    () => items.find((x) => x.user_id === selectedUserId) || null,
    [items, selectedUserId]
  );

  useEffect(() => {
    async function loadPreview() {
      if (!selectedUserId) {
        setTemplatePreviewUrl("");
        return;
      }
      const item = items.find((x) => x.user_id === selectedUserId);
      if (!item?.resume_template_uploaded) {
        setTemplatePreviewUrl("");
        return;
      }
      setPreviewLoading(true);
      try {
        const token = getToken();
        const res = await fetch(
          `${API_BASE}/v1/users/${selectedUserId}/resume-template-preview.pdf`,
          {
            headers: token ? { "X-Auth-Token": token } : {},
            cache: "no-store",
          }
        );
        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(text || `HTTP ${res.status}`);
        }
        const blob = await res.blob();
        setTemplatePreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return URL.createObjectURL(blob);
        });
      } catch (e) {
        setTemplatePreviewUrl("");
        setError(e?.message || String(e));
      } finally {
        setPreviewLoading(false);
      }
    }

    loadPreview();
  }, [selectedUserId, items]);

  useEffect(() => {
    return () => {
      if (templatePreviewUrl) {
        URL.revokeObjectURL(templatePreviewUrl);
      }
    };
  }, [templatePreviewUrl]);

  async function uploadTemplate(file) {
    if (!selectedUserId || !file) return;
    setUploadingTemplate(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      await apiFetch(`/v1/users/${selectedUserId}/resume-template-docx`, {
        method: "PUT",
        body: form,
      });
      await refresh();
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setUploadingTemplate(false);
    }
  }

  return (
    <div style={{ maxWidth: 980 }}>
      <h1>Resume Templates</h1>

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
          gridTemplateColumns: "340px 1fr",
          gap: 16,
          alignItems: "start",
        }}
      >
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
            <strong>Users</strong>
            <button className="btn btnGhost" onClick={refresh} disabled={loading}>
              {loading ? "Loading..." : "Refresh"}
            </button>
          </div>

          {items.length === 0 && !loading && (
            <div style={{ color: "#8aa" }}>No users available yet.</div>
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
                  <div style={{ fontSize: 12, opacity: 0.74, marginTop: 4 }}>
                    Template:{" "}
                    {x.resume_template_uploaded
                      ? x.resume_template_filename || "Uploaded"
                      : "Not uploaded"}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div
          style={{
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 12,
            padding: 16,
          }}
        >
          <div style={{ marginBottom: 12 }}>
            <strong>Assigned DOCX template</strong>
            {selectedUserId && (
              <span style={{ marginLeft: 8, opacity: 0.7, fontSize: 12 }}>
                ({selectedUserId})
              </span>
            )}
          </div>

          <div
            style={{
              padding: 14,
              borderRadius: 10,
              border: "1px solid rgba(255,255,255,0.08)",
              background: "rgba(255,255,255,0.03)",
            }}
          >
            <div style={{ fontSize: 13, opacity: 0.82, marginBottom: 12 }}>
              {selectedItem?.resume_template_uploaded
                ? `Current file: ${selectedItem.resume_template_filename || "Uploaded DOCX"}`
                : "No template uploaded yet. Apply-and-generate will use the default renderer until you assign a DOCX template."}
            </div>

            <input
              type="file"
              accept=".docx"
              disabled={!selectedUserId || uploadingTemplate}
              onChange={(e) => uploadTemplate(e.target.files?.[0])}
            />

            {uploadingTemplate && (
              <div style={{ fontSize: 12, opacity: 0.72, marginTop: 8 }}>
                Uploading template...
              </div>
            )}

            <div style={{ marginTop: 14, fontSize: 12, opacity: 0.82 }}>
              Template preview
            </div>
            <div
              style={{
                marginTop: 8,
                borderRadius: 8,
                border: "1px solid rgba(255,255,255,0.08)",
                background: "rgba(0,0,0,0.14)",
                minHeight: 480,
                overflow: "hidden",
              }}
            >
              {previewLoading
                ? "Loading preview..."
                : templatePreviewUrl
                  ? (
                    <iframe
                      title="Template preview"
                      src={templatePreviewUrl}
                      style={{ width: "100%", height: 480, border: 0 }}
                    />
                  )
                  : "Upload one DOCX per user to preview it here."}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
