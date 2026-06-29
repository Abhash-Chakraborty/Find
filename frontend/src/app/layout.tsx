import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import "./globals.css";
import CursorGlow from "@/components/CursorGlow";
import NavBar from "@/components/NavBar";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Find - Local AI Image Intelligence",
  description:
    "AI-powered image search and organization that runs entirely on your device",
  manifest: "/manifest.json",
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
          <CursorGlow />
          <nav className="sticky top-0 z-50 h-[var(--nav-height)] w-full max-w-full overflow-x-hidden border-b border-[var(--frost)] bg-[color:var(--void)]/78 backdrop-blur-xl">
            <div className="container-shell px-0 py-4">
              <div className="flex items-center justify-between gap-4">
                <Link
                  href="/"
                  className="group flex shrink-0 items-center gap-3 text-2xl font-semibold text-[color:var(--near-white)] transition-colors hover:opacity-90"
                >
                  <span className="relative grid h-8 w-8 place-items-center rounded-md border border-[var(--frost)] bg-[color:var(--near-white)] p-1 shadow-sm transition-transform group-hover:scale-105 dark:bg-[color:var(--frost-soft)]">
                    <Image
                      src="/Find-Logo.svg"
                      alt=""
                      width={50}
                      height={50}
                      priority
                    />
                  </span>
                  FIND.
                </Link>

                <NavBar />
              </div>
            </div>
          </nav>

          {children}

          <div className="pointer-events-none fixed bottom-3 left-1/2 z-40 -translate-x-1/2 rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] px-3 py-1 text-[11px] font-medium text-[color:var(--muted)] backdrop-blur-md">
            © 2026 Find. AGPL-3.0 License.
          </div>
        </Providers>
      </body>
    </html>
  );
}
