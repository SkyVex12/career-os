"use client";

import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../lib/api";
import TopbarClient from "../components/TopbarClient";
export default function AssistantPage() {
  const [threadId, setThreadId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("Help me plan my job search week.");

  async function ensureThread() {
    if (threadId) return threadId;
    const res = await fetch(`${API}/assistant/threads`, { method: "POST" });
    const t = await res.json();
    setThreadId(t.id);
    return t.id;
  }

  async function refresh(tid) {
    const res = await fetch(`${API}/assistant/threads/${tid}/messages`);
    setMessages(await res.json());
  }

  useEffect(() => {
    (async () => {
      const tid = await ensureThread();
      await refresh(tid);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function send() {
    const tid = await ensureThread();
    await fetch(`${API}/assistant/threads/${tid}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "user", content: input }),
    });
    setInput("");
    await refresh(tid);
  }

  return (
    <div style={{ maxWidth: 900 }}>
      <h1>Assistant (skeleton)</h1>
      <div
        style={{
          border: "1px solid #eee",
          borderRadius: 8,
          padding: 12,
          minHeight: 220,
        }}
      >
        {messages.map((m) => (
          <div key={m.id} style={{ marginBottom: 10 }}>
            <strong>{m.role}:</strong> {m.content}
          </div>
        ))}
        {messages.length === 0 && (
          <div style={{ color: "#666" }}>No messages yet.</div>
        )}
      </div>

      <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
        <textarea
          rows={3}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask CareerOS..."
        />
        <button onClick={send}>Send</button>
        <small style={{ color: "#666" }}>
          This is a placeholder; next step is OpenAI + retrieval + tool-calling.
        </small>
      </div>
    </div>
  );
}
