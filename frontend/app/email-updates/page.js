"use client";

import { useEffect, useMemo, useState } from "react";
import TopbarClient from "../components/TopbarClient";
import toast from "react-hot-toast";
import { api } from "../lib/api";
import { useScope } from "../components/ClientShell";

function fmtDt(x) {
  try {
    const d = new Date(x);
    if (Number.isFinite(d.getTime())) return d.toLocaleString();
  } catch {}
  return x || "";
}

function StagePill({ stage }) {
  const s = (stage || "").toLowerCase();
  let cls = "pill";
  if (s === "offer") cls = "pillOk";
  else if (s === "rejected") cls = "pillDanger";
  else if (s === "interview") cls = "pillWarn";
  return <span className={cls}>{stage || "unknown"}</span>;
}

export default function EmailUpdatesPage() {
  const { scope } = useScope();
  const userId = scope?.mode === "user" ? scope.userId : null;

  const [lookback, setLookback] = useState(60);
  const [maxMessages, setMaxMessages] = useState(25);

  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const [suggestions, setSuggestions] = useState([]);

  // MVP manual token connect (until OAuth UI is added)
  const [accountEmail, setAccountEmail] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [refreshToken, setRefreshToken] = useState("");
  const [expiresIn, setExpiresIn] = useState(3600);
  const [autoUpdate, setAutoUpdate] = useState(false);

  const disabled = !userId;

  async function loadSuggestions() {
    if (!userId) return;
    setLoading(true);
    try {
      const data = await api(
        `/v1/email/suggestions?user_id=${encodeURIComponent(
          userId
        )}&status=pending&limit=50`
      );
      setSuggestions(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error(e?.message || "Failed to load suggestions");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSuggestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  async function connectOutlook() {
    if (!userId) return;
    setLoading(true);
    try {
      await api("/v1/integrations/outlook/connect", {
        method: "POST",
        body: JSON.stringify({
          user_id: userId,
          account_email: accountEmail || null,
          access_token: accessToken || null,
          refresh_token: refreshToken || null,
          expires_in: Number(expiresIn) || 3600,
          auto_update: !!autoUpdate,
        }),
      });
      toast.success("Outlook connected (tokens saved).");
    } catch (e) {
      toast.error(e?.message || "Connect failed");
    } finally {
      setLoading(false);
    }
  }

  async function syncNow() {
    if (!userId) return;
    setSyncing(true);
    try {
      const res = await api(
        `/v1/integrations/outlook/sync?user_id=${encodeURIComponent(
          userId
        )}&lookback_minutes=${encodeURIComponent(
          lookback
        )}&max_messages=${encodeURIComponent(maxMessages)}`,
        { method: "POST" }
      );
      toast.success(
        `Synced. Fetched ${res?.fetched || 0}, new suggestions ${
          res?.new_suggestions || 0
        }.`
      );
      await loadSuggestions();
    } catch (e) {
      toast.error(e?.message || "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  async function approveSuggestion(id) {
    if (!userId) return;
    try {
      await api(`/v1/email/suggestions/${id}/approve`, { method: "POST" });
      toast.success("Applied update.");
      setSuggestions((prev) => prev.filter((x) => x.id !== id));
    } catch (e) {
      toast.error(e?.message || "Approve failed");
    }
  }

  async function rejectSuggestion(id) {
    if (!userId) return;
    try {
      await api(`/v1/email/suggestions/${id}/reject`, { method: "POST" });
      toast.success("Rejected.");
      setSuggestions((prev) => prev.filter((x) => x.id !== id));
    } catch (e) {
      toast.error(e?.message || "Reject failed");
    }
  }

  return (
    <div className="page">
      <TopbarClient
        title="Email → Application Updates"
        subtitle="Sync Outlook emails, review suggestions, and update application stages."
      />

      {!userId ? (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="cardTitle">Select a user scope</div>
          <div className="cardSub">
            Email updates are per-user. Use the Scope selector in the top bar to
            choose a specific user (not &quot;All my users&quot;).
          </div>
        </div>
      ) : null}

      <div
        className="grid2"
        style={{ marginTop: 16, opacity: disabled ? 0.5 : 1 }}
      >
        <div className="card">
          <div className="cardTitle">Connect Outlook (MVP)</div>
          <div className="cardSub">
            For now, paste tokens here. Later this becomes a one-click OAuth
            connect.
          </div>

          <div style={{ marginTop: 10 }} className="formGrid">
            <div>
              <label className="label">Account email (optional)</label>
              <input
                className="input"
                value={accountEmail}
                onChange={(e) => setAccountEmail(e.target.value)}
                placeholder="you@domain.com"
                disabled={disabled}
              />
            </div>

            <div>
              <label className="label">Expires in (seconds)</label>
              <input
                className="input"
                type="number"
                value={expiresIn}
                onChange={(e) => setExpiresIn(e.target.value)}
                disabled={disabled}
              />
            </div>

            <div className="full">
              <label className="label">Access token</label>
              <textarea
                className="textarea"
                value={accessToken}
                onChange={(e) => setAccessToken(e.target.value)}
                placeholder="Paste access token"
                disabled={disabled}
                rows={3}
              />
            </div>

            <div className="full">
              <label className="label">Refresh token (optional)</label>
              <textarea
                className="textarea"
                value={refreshToken}
                onChange={(e) => setRefreshToken(e.target.value)}
                placeholder="Paste refresh token"
                disabled={disabled}
                rows={3}
              />
            </div>

            <div className="full" style={{ display: "flex", gap: 10 }}>
              <label
                className="label"
                style={{ display: "flex", gap: 10, alignItems: "center" }}
              >
                <input
                  type="checkbox"
                  checked={autoUpdate}
                  onChange={(e) => setAutoUpdate(e.target.checked)}
                  disabled={disabled}
                />
                Enable auto-update (not recommended for MVP)
              </label>
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <button
              className="btn"
              onClick={connectOutlook}
              disabled={disabled || loading}
            >
              Save tokens
            </button>
          </div>
        </div>

        <div className="card">
          <div className="cardTitle">Sync Inbox</div>
          <div className="cardSub">
            Pull recent emails and create stage update suggestions.
          </div>

          <div style={{ marginTop: 10 }} className="formGrid">
            <div>
              <label className="label">Lookback minutes</label>
              <input
                className="input"
                type="number"
                value={lookback}
                onChange={(e) => setLookback(e.target.value)}
                disabled={disabled}
              />
            </div>
            <div>
              <label className="label">Max messages</label>
              <input
                className="input"
                type="number"
                value={maxMessages}
                onChange={(e) => setMaxMessages(e.target.value)}
                disabled={disabled}
              />
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <button
              className="btn"
              onClick={syncNow}
              disabled={disabled || syncing}
            >
              {syncing ? "Syncing..." : "Sync now"}
            </button>
            <button
              className="btn btnSecondary"
              onClick={loadSuggestions}
              disabled={disabled || loading}
            >
              Refresh list
            </button>
          </div>

          <div className="hint" style={{ marginTop: 10 }}>
            Tip: start with approve-first mode; enable auto-update only after
            accuracy is proven.
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="cardTitle">Pending Suggestions</div>
        <div className="cardSub">
          Review and approve/reject stage updates inferred from email.
        </div>

        <div style={{ marginTop: 10 }}>
          {loading ? (
            <div className="hint">Loading...</div>
          ) : suggestions.length === 0 ? (
            <div className="hint">No pending suggestions.</div>
          ) : (
            <div className="stack">
              {suggestions.map((s) => (
                <div key={s.id} className="card" style={{ marginTop: 10 }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 12,
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div className="cardTitle" style={{ fontSize: 14 }}>
                        {s.email?.subject || "(no subject)"}
                      </div>
                      <div className="cardSub">
                        From: {s.email?.from_email || "unknown"} •{" "}
                        {fmtDt(s.email?.received_at)} • Confidence:{" "}
                        {s.confidence}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                      <StagePill stage={s.suggested_stage} />
                      <span className="pill">
                        {s.application_id ? "Matched" : "Needs review"}
                      </span>
                    </div>
                  </div>

                  {s.email?.body_preview ? (
                    <div className="hint" style={{ marginTop: 10 }}>
                      {s.email.body_preview}
                    </div>
                  ) : null}

                  {s.reason ? (
                    <div className="hint" style={{ marginTop: 8 }}>
                      Reason: {s.reason}
                    </div>
                  ) : null}

                  <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
                    <button
                      className="btn"
                      onClick={() => approveSuggestion(s.id)}
                    >
                      Approve & Update
                    </button>
                    <button
                      className="btn btnSecondary"
                      onClick={() => rejectSuggestion(s.id)}
                    >
                      Reject
                    </button>
                  </div>

                  {s.application_id ? (
                    <div className="hint" style={{ marginTop: 10 }}>
                      Application: <span className="mono">{s.application_id}</span>
                    </div>
                  ) : (
                    <div className="hint" style={{ marginTop: 10 }}>
                      No application match found. (Next: add UI to select the correct
                      application on approve.)
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
