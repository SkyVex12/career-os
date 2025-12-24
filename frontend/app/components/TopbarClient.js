"use client";
import { useEffect, useState } from "react";
import { getApiBase, getToken } from "../lib/api";

export default function TopbarClient({ title, subtitle }) {
  const [userId, setUserId] = useState(() =>
    typeof window !== "undefined" ? localStorage.getItem("careeros_user_id") || "u1" : "u1"
  );
  const [apiBase, setApiBase] = useState(() =>
    typeof window !== "undefined" ? localStorage.getItem("careeros_api_base") || "" : ""
  );
  const [token, setToken] = useState(() =>
    typeof window !== "undefined" ? localStorage.getItem("careeros_token") || "" : ""
  );

  useEffect(() => {
    try {
      localStorage.setItem("careeros_user_id", userId || "u1");
      if (apiBase) localStorage.setItem("careeros_api_base", apiBase);
      if (token) localStorage.setItem("careeros_token", token);
    } catch {}
  }, [userId, apiBase, token]);

  const hintBase = getApiBase();
  const hintTok = getToken();

  return (
    <div className="topbar">
      <div>
        <h2>{title}</h2>
        {subtitle ? <div className="small">{subtitle}</div> : null}
      </div>

      <div className="chips">
        <span className="chip">API: {apiBase || hintBase}</span>
        <span className="chip">user: {userId}</span>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
        <input className="input" style={{ width: 90 }} value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="user_id" />
        <input className="input" style={{ width: 230 }} value={apiBase} onChange={(e) => setApiBase(e.target.value)} placeholder="API base (optional)" />
        <input className="input" style={{ width: 170 }} value={token} onChange={(e) => setToken(e.target.value)} placeholder={hintTok ? "Token (override)" : "Token"} />
      </div>
    </div>
  );
}
