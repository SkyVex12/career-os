export const DescriptionModal = ({
  jdOpen,
  jdData,
  jdLoading,
  jdError,
  onClose,
}) => {
  if (!jdOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      onMouseDown={(e) => {
        // click outside closes
        if (e.target === e.currentTarget) setJdOpen(false);
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.95)",
        display: "grid",
        placeItems: "center",
        zIndex: 9999,
        padding: 16,
      }}
    >
      <div
        onMouseDown={(e) => e.stopPropagation()}
        className="card"
        style={{
          width: "min(1500px, 100%)",
          maxHeight: "85vh",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Header */}
        <div
          className="cardPad"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
            borderBottom: "1px solid rgba(255,255,255,.08)",
          }}
        >
          <div style={{ fontWeight: 800 }}>
            {jdData?.title || "Job Description"}
          </div>

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {jdData?.jd_text ? (
              <button
                className="btn btnGhost btnXS"
                type="button"
                onClick={() => navigator.clipboard.writeText(jdData.jd_text)}
              >
                Copy
              </button>
            ) : null}

            <button className="btn btnGhost" type="button" onClick={onClose}>
              Close
            </button>
          </div>
        </div>

        {/* Body */}
        <div
          style={{
            padding: 14,
            overflowY: "auto",
            flex: 1,
          }}
        >
          {jdLoading ? (
            <div className="small">Loading…</div>
          ) : jdError ? (
            <div className="small" style={{ color: "tomato" }}>
              {jdError}
            </div>
          ) : jdData?.jd_text ? (
            <pre
              style={{
                margin: 0,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontSize: 22,
                lineHeight: 1.45,
              }}
            >
              {jdData.jd_text}
            </pre>
          ) : (
            <div className="small muted">No description found.</div>
          )}
        </div>
      </div>
    </div>
  );
};
