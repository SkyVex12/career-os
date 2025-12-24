'use client';

import { useEffect, useState } from "react";

const API = "http://localhost:8000/v1";

export default function ApplicationsPage() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ company: "", role: "", url: "", location: "" });

  async function refresh() {
    const res = await fetch(`${API}/applications`);
    setItems(await res.json());
  }

  useEffect(() => { refresh(); }, []);

  async function create(e) {
    e.preventDefault();
    const res = await fetch(`${API}/applications`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        company: form.company,
        role: form.role,
        url: form.url || null,
        location: form.location || null
      })
    });
    if (!res.ok) return alert("Failed to create");
    setForm({ company: "", role: "", url: "", location: "" });
    await refresh();
  }

  return (
    <div style={{ maxWidth: 900 }}>
      <h1>Applications</h1>

      <form onSubmit={create} style={{ display: "grid", gap: 8, marginBottom: 16 }}>
        <input placeholder="Company" value={form.company} onChange={e=>setForm({...form, company:e.target.value})} />
        <input placeholder="Role" value={form.role} onChange={e=>setForm({...form, role:e.target.value})} />
        <input placeholder="Job URL (optional)" value={form.url} onChange={e=>setForm({...form, url:e.target.value})} />
        <input placeholder="Location (optional)" value={form.location} onChange={e=>setForm({...form, location:e.target.value})} />
        <button type="submit">Create</button>
      </form>

      <div style={{ border: "1px solid #eee", borderRadius: 8 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: 8 }}>Company</th>
              <th style={{ textAlign: "left", padding: 8 }}>Role</th>
              <th style={{ textAlign: "left", padding: 8 }}>Stage</th>
              <th style={{ textAlign: "left", padding: 8 }}>Updated</th>
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id} style={{ borderTop: "1px solid #eee" }}>
                <td style={{ padding: 8 }}>{a.company}</td>
                <td style={{ padding: 8 }}>{a.role}</td>
                <td style={{ padding: 8 }}>{a.stage}</td>
                <td style={{ padding: 8 }}>{new Date(a.updated_at).toLocaleString()}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan="4" style={{ padding: 12, color: "#666" }}>No applications yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
