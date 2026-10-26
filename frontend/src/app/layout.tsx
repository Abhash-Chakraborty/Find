import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AppShell } from "@/components/app-shell";
import { ServiceWorkerRegistrar } from "@/components/service-worker-registrar";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Find - Local AI Image Intelligence",
  description:
    "AI-powered image search and organization that runs entirely on your device",
  manifest: "/manifest.json",
  // Installed on iOS the app runs standalone without Safari chrome; without
  // this it opens in a browser tab instead (#259).
  appleWebApp: {
    capable: true,
    title: "Find",
    statusBarStyle: "black-translucent",
  },
};

// themeColor lives on the viewport export in the Next.js App Router, not on
// metadata. It must match manifest.json or the installed splash and title bar
// disagree with the running app.
export const viewport: Viewport = {
  themeColor: "#000000",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <Providers>
          <ServiceWorkerRegistrar />
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
