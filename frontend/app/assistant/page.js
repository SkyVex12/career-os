"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import TopbarClient from "../components/TopbarClient";
import { api } from "../lib/api";

function cx(...xs) {
  return xs.filter(Boolean).join(" ");
}

export default function AssistantPage() {
  const [threads, setThreads] = useState([]);
  const [activeId, setActiveId] = useState(null);

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  const scrollerRef = useRef(null);
  const stickToBottomRef = useRef(true);

  // Track scroll position (so we don't yank user down while reading)
  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const onScroll = () => {
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      stickToBottomRef.current = nearBottom;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    if (stickToBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  async function loadThreads() {
    const t = await api("/assistant/threads");
    setThreads(Array.isArray(t) ? t : []);
    if (!activeId && t?.length) setActiveId(t[0].id);
  }

  async function loadMessages(threadId) {
    const m = await api(`/assistant/threads/${threadId}/messages`);
    setMessages(Array.isArray(m) ? m : []);
  }

  useEffect(() => {
    loadThreads().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!activeId) return;
    loadMessages(activeId).catch(() => {});
  }, [activeId]);

  async function newChat() {
    const t = await api("/assistant/threads", { method: "POST" });
    setThreads((prev) => [t, ...prev]);
    setActiveId(t.id);
    setMessages([]);
    setInput("");
    // optional: focus input
    setTimeout(() => document.getElementById("chatInput")?.focus(), 50);
  }

  async function deleteChat(threadId) {
    const ok = confirm("Delete this chat? This cannot be undone.");
    if (!ok) return;

    try {
      await api(`/assistant/threads/${threadId}`, { method: "DELETE" });

      setThreads((prev) => prev.filter((t) => t.id !== threadId));

      // If deleting the active chat, switch to next available
      if (activeId === threadId) {
        const remaining = threads.filter((t) => t.id !== threadId);
        const next = remaining[0]?.id ?? null;
        setActiveId(next);
        setMessages([]);
        if (next) loadMessages(next).catch(() => {});
      }
    } catch (e) {
      alert(e?.message || "Failed to delete chat.");
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || sending) return;

    let tid = activeId;
    if (!tid) {
      const t = await api("/assistant/threads", { method: "POST" });
      setThreads((prev) => [t, ...prev]);
      tid = t.id;
      setActiveId(t.id);
      setMessages([]);
    }

    setInput("");

    // optimistic user message
    const localUser = {
      id: `local-u-${crypto.randomUUID()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, localUser]);

    setSending(true);

    try {
      // backend will append assistant placeholder reply too
      await api(`/assistant/threads/${tid}/messages`, {
        method: "POST",
        body: JSON.stringify({ role: "user", content: text }),
      });

      await loadMessages(tid);
      await loadThreads();
    } catch (e) {
      // show error as assistant bubble
      setMessages((prev) => [
        ...prev,
        {
          id: `local-a-${crypto.randomUUID()}`,
          role: "assistant",
          content: `⚠️ ${e?.message || "Failed to send."}`,
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setSending(false);
      setTimeout(() => document.getElementById("chatInput")?.focus(), 10);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  const activeTitle = useMemo(() => {
    const t = threads.find((x) => x.id === activeId);
    return t?.title || "New chat";
  }, [threads, activeId]);

  return (
    <div className="container">
      <TopbarClient
        title="Assistant"
        subtitle="ChatGPT-style UI • next step: streaming + tool-calling"
      />

      <div className="chatLayout">
        {/* LEFT: Threads */}
        <aside className="chatSide">
          <div className="chatSideTop">
            <div className="chatSideTitle">Chats</div>
            <button className="btn btnPrimary" onClick={newChat}>
              New
            </button>
          </div>

          <div className="chatThreadList">
            {threads.length === 0 ? (
              <div className="mutedSmall">No chats yet.</div>
            ) : (
              threads.map((t) => (
                <div
                  key={t.id}
                  className={cx(
                    "chatThreadWrap",
                    activeId === t.id && "chatThreadWrapActive"
                  )}
                >
                  <button
                    className={cx(
                      "chatThread",
                      activeId === t.id && "chatThreadActive"
                    )}
                    onClick={() => setActiveId(t.id)}
                    title={t.title}
                  >
                    <div className="chatThreadTitle">
                      {t.title || "New chat"}
                    </div>
                    <div className="chatThreadMeta">
                      {t.updated_at
                        ? new Date(t.updated_at).toLocaleString()
                        : ""}
                    </div>
                  </button>

                  <button
                    className="chatThreadDelete"
                    title="Delete chat"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteChat(t.id);
                    }}
                  >
                    🗑
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* RIGHT: Chat */}
        <section className="chatMain">
          <div className="chatHeader">
            <div className="chatHeaderTitle">{activeTitle}</div>
            <div className="chatHeaderSub">
              Enter to send • Shift+Enter for newline
            </div>
          </div>

          <div ref={scrollerRef} className="chatScroll">
            <div className="chatInner">
              {messages.length === 0 ? (
                <div className="chatEmpty">
                  <div className="chatEmptyTitle">Your CareerOS Assistant</div>
                  <div className="chatEmptySub">
                    Ask to tailor a resume, draft a cover letter, or triage
                    recruiter emails.
                  </div>
                  <div className="chatSuggestions">
                    {[
                      "Tailor my resume to this job description",
                      "Draft a confident cover letter (200 words)",
                      "Summarize recruiter emails from this week",
                      "What should I follow up on next?",
                    ].map((s) => (
                      <button
                        key={s}
                        className="chatChip"
                        onClick={() => setInput(s)}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((m) => <MessageRow key={m.id} m={m} />)
              )}

              {sending ? (
                <div className="msgRow">
                  <div className="avatar avatarAI">AI</div>
                  <div className="bubble bubbleAI">
                    <div className="typing">
                      <span />
                      <span />
                      <span />
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          <div className="chatComposer">
            <textarea
              id="chatInput"
              className="chatInput"
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Message CareerOS…"
            />
            <button
              className={cx(
                "btn btnSend",
                (!input.trim() || sending) && "btnDisabled"
              )}
              onClick={send}
              disabled={!input.trim() || sending}
            >
              Send
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}

function MessageRow({ m }) {
  const isUser = m.role === "user";
  return (
    <div className={cx("msgRow", isUser && "msgRowUser")}>
      <div className={cx("avatar", isUser ? "avatarUser" : "avatarAI")}>
        {isUser ? "You" : "AI"}
      </div>
      <div className={cx("bubble", isUser ? "bubbleUser" : "bubbleAI")}>
        <div className="bubbleText">{m.content}</div>
        <div className="bubbleActions">
          <button
            className="miniBtn"
            onClick={() => navigator.clipboard.writeText(m.content || "")}
          >
            Copy
          </button>
        </div>
      </div>
    </div>
  );
}
