import "./globals.css";

export const metadata = {
  title: "CareerOS",
  description: "Job application tracker + generator",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <aside className="sidebar">
            <div className="brand">
              <div className="logo" />
              <div>
                <h1>CareerOS</h1>
                <p>Track → Analyze → Win</p>
              </div>
            </div>

            <div className="nav">
              <a href="/dashboard">Dashboard</a>
              <a href="/applications">Applications</a>
              <a href="/assistant">Assistant</a>
              <a href="/documents">Documents</a>
            </div>

            <div style={{ marginTop: 16 }} className="card cardPad">
              <div className="kpiTitle">Tip</div>
              <div className="small" style={{ marginTop: 6 }}>
                Use <b>Applications → Kanban</b> to drag cards between stages.
              </div>
            </div>
          </aside>

          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
