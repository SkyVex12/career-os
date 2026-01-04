import "./globals.css";
import Script from "next/script";
import { Toaster } from "react-hot-toast";
import ClientShell from "./components/ClientShell";

export const metadata = {
  title: "CareerOS",
  description: "Job application tracker + generator",
};

export default function RootLayout({ children }) {
  return (
    <html>
      <head>
        {/* Privacy-friendly analytics by Plausible */}
        <Script
          async
          src="https://plausible.io/js/pa-fY4X0tp2YCaL1J0nNJCdF.js"
          strategy="afterInteractive"
        />
        <Script
          id="plausible-init"
          strategy="afterInteractive"
        >{`window.plausible=window.plausible||function(){(plausible.q=plausible.q||[]).push(arguments)},plausible.init=plausible.init||function(i){plausible.o=i||{}};plausible.init()`}</Script>
      </head>
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
