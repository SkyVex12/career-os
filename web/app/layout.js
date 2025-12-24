export const metadata = {
  title: "CareerOS",
  description: "CareerOS — your AI-powered career operating system."
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, Arial", margin: 0 }}>
        <div style={{ borderBottom: "1px solid #eee", padding: "12px 16px" }}>
          <strong>CareerOS</strong>
          <nav style={{ display: "inline-block", marginLeft: 16 }}>
            <a href="/" style={{ marginRight: 12 }}>Home</a>
            <a href="/applications" style={{ marginRight: 12 }}>Applications</a>
            <a href="/documents" style={{ marginRight: 12 }}>Documents</a>
            <a href="/assistant">Assistant</a>
          </nav>
        </div>
        <main style={{ padding: "16px" }}>{children}</main>
      </body>
    </html>
  );
}
