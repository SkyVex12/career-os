export default function Page() {
  return (
    <div style={{ maxWidth: 900 }}>
      <h1>CareerOS</h1>
      <p>
        Initial skeleton: Next.js UI + FastAPI API. This is the base for:
        Applications pipeline, Documents generation/versioning, and an AI Assistant.
      </p>

      <div style={{ padding: 12, border: "1px solid #eee", borderRadius: 8 }}>
        <h3>Quick links</h3>
        <ul>
          <li><a href="/applications">Applications</a></li>
          <li><a href="/documents">Documents</a></li>
          <li><a href="/assistant">Assistant</a></li>
        </ul>
      </div>

      <p style={{ marginTop: 16 }}>
        API health: <a href="http://localhost:8000/health" target="_blank">http://localhost:8000/health</a>
      </p>
    </div>
  );
}
