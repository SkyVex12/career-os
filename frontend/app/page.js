export default function Home() {
  return (
    <main className="container">
      <div className="card cardPad">
        <h2 style={{ marginTop: 0 }}>Welcome to CareerOS</h2>
        <p className="muted" style={{ marginTop: 6 }}>
          Track applications, analyze funnel performance, and manage documents.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
          <a className="btn btnPrimary" href="/dashboard">Open Dashboard</a>
          <a className="btn" href="/applications">Manage Applications</a>
          <a className="btn" href="/assistant">Generate</a>
          <a className="btn" href="/documents">Base Resume</a>
        </div>
      </div>
    </main>
  );
}
