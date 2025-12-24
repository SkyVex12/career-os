'use client';

import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import TopbarClient from "../components/TopbarClient";
export default function DocumentsPage() {
  const [docs, setDocs] = useState([]);
  const [prompt, setPrompt] = useState("Write a short cover letter draft for a senior software engineer role.");
  const [generated, setGenerated] = useState(null);

  async function refresh() {
    const res = await apiFetch(`/v1/documents`);
    setDocs(await res.json());
  }

  useEffect(() => { refresh(); }, []);

  async function generate() {
    const res = await fetch(`${API}/documents/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_type: "cover_letter", prompt, context: null, application_id: null })
    });
    const data = await res.json();
    setGenerated(data);
    await refresh();
  }

  return (
    <div style={{ maxWidth: 900 }}>
      <h1>Documents</h1>

      <div style={{ display: "grid", gap: 8, marginBottom: 16 }}>
        <textarea rows={6} value={prompt} onChange={e=>setPrompt(e.target.value)} />
        <button onClick={generate}>Generate (stub)</button>
      </div>

      {generated && (
        <div style={{ whiteSpace: "pre-wrap", padding: 12, border: "1px solid #eee", borderRadius: 8, marginBottom: 16 }}>
          <strong>Generated version</strong>
          <div style={{ marginTop: 8 }}>{generated.content}</div>
        </div>
      )}

      <h3>Documents list</h3>
      <ul>
        {docs.map(d => (
          <li key={d.id}>{d.title} — <em>{d.doc_type}</em></li>
        ))}
        {docs.length === 0 && <li style={{ color: "#666" }}>No documents yet.</li>}
      </ul>
    </div>
  );
}
