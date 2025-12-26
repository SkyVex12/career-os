import "./globals.css";
import { Toaster } from "react-hot-toast";
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
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 2200,
            style: {
              background: "rgba(10,10,12,0.9)",
              color: "#fff",
              border: "1px solid rgba(255,255,255,0.12)",
            },
          }}
        />
      </body>
    </html>
  );
}
