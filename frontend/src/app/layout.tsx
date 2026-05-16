import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import "./globals.css";
import NavBar from "@/components/NavBar";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Find - Local AI Image Intelligence",
  description:
    "AI-powered image search and organization that runs entirely on your device",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-black text-[#f0f0f0] antialiased">
        <Providers>
          <nav className="sticky top-0 z-50 h-[var(--nav-height)] border-b border-[var(--frost)] bg-black/78 backdrop-blur-xl">
            <div className="container-shell px-0 py-4">
              <div className="flex items-center justify-between gap-4">
                <Link
                  href="/"
                  className="group flex shrink-0 items-center gap-3 text-2xl font-semibold text-[#f0f0f0] transition-colors hover:text-white"
                >
                  <span className="relative grid h-8 w-8 place-items-center rounded-md border border-[var(--frost)] bg-white/[0.03] p-1 transition-transform group-hover:scale-105">
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

          <div className="pointer-events-none fixed bottom-3 left-1/2 z-40 -translate-x-1/2 rounded-full border border-[var(--frost)] bg-black/55 px-3 py-1 text-[11px] font-medium text-[#5f6568] backdrop-blur-md">
            © 2026 Find. MIT License.
          </div>
        </Providers>
      </body>
    </html>
  );
}
