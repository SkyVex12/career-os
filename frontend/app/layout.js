import "./globals.css";
import ClientShell from "./components/ClientShell";

export const metadata = {
  title: "CareerOS",
  description: "Job application tracker + generator",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <ClientShell>{children}</ClientShell>
      </body>
    </html>
  );
}
