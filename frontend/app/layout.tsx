import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({ subsets: ["latin"] });

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
      <body className={inter.className}>
        <Providers>
          <nav className="border-b border-gray-100 bg-white sticky top-0 z-50">
            <div className="max-w-7xl mx-auto px-6 py-4">
              <div className="flex items-center justify-between">
                <Link href="/" className="text-xl font-light text-black">
                  Find
                </Link>

                <div className="flex gap-8">
                  <Link
                    href="/upload"
                    className="text-sm text-gray-500 hover:text-black transition-colors"
                  >
                    Upload
                  </Link>
                  <Link
                    href="/gallery"
                    className="text-sm text-gray-500 hover:text-black transition-colors"
                  >
                    Gallery
                  </Link>
                  <Link
                    href="/search"
                    className="text-sm text-gray-500 hover:text-black transition-colors"
                  >
                    Search
                  </Link>
                  <Link
                    href="/clusters"
                    className="text-sm text-gray-500 hover:text-black transition-colors"
                  >
                    Clusters
                  </Link>
                </div>
              </div>
            </div>
          </nav>

          {children}
        </Providers>
      </body>
    </html>
  );
}
