import { ArrowRight, Image as ImageIcon, Lock, ScanSearch } from "lucide-react";
import Link from "next/link";

export default function HomePage() {
  return (
    <main className="home-shell">
      <section className="container-shell hero-viewport flex flex-col justify-center gap-8 py-8 md:gap-10 md:py-10">
        <div className="page-enter mx-auto flex max-w-4xl flex-col items-center justify-center text-center">
          <h1 className="display-heading mb-4 text-5xl sm:text-6xl lg:text-6xl xl:text-7xl">
            <span className="block sm:hidden">Your visual</span>
            <span className="block sm:hidden">memory,</span>
            <span className="block sm:hidden">indexed.</span>
            <span className="hidden sm:inline">
              Your visual memory,
              <br />
              indexed.
            </span>
          </h1>

          <p className="muted-copy mb-7 max-w-2xl text-sm leading-6 md:text-base">
            AI-powered image intelligence that runs entirely on your device.
            Fast, private, and beautiful.
          </p>

          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/upload"
              className="white-pill px-6 py-3 text-sm font-semibold"
            >
              Start uploading
              <ArrowRight className="h-4 w-4" />
            </Link>

            <Link
              href="/search"
              className="frost-button px-6 py-3 text-sm font-medium"
            >
              Search library
            </Link>
          </div>
        </div>

        <div className="delayed-enter grid gap-3 border-t border-[var(--frost)] pt-5 md:grid-cols-3">
          <div className="frost-panel card-hover flex min-w-0 items-center gap-4 rounded-2xl p-4">
            <Lock className="h-5 w-5 shrink-0 text-[color:var(--green)]" />
            <div>
              <h3 className="text-sm font-medium text-[color:var(--near-white)]">
                Private
              </h3>
              <p className="text-sm text-[color:var(--silver)]">
                100% local processing
              </p>
            </div>
          </div>

          <div className="frost-panel card-hover flex min-w-0 items-center gap-4 rounded-2xl p-4">
            <ScanSearch className="h-5 w-5 shrink-0 text-[color:var(--blue)]" />
            <div>
              <h3 className="text-sm font-medium text-[color:var(--near-white)]">
                Intelligent
              </h3>
              <p className="text-sm text-[color:var(--silver)]">
                Natural language search
              </p>
            </div>
          </div>

          <div className="frost-panel card-hover flex min-w-0 items-center gap-4 rounded-2xl p-4">
            <ImageIcon className="h-5 w-5 shrink-0 text-[color:var(--orange)]" />
            <div>
              <h3 className="text-sm font-medium text-[color:var(--near-white)]">
                Organized
              </h3>
              <p className="text-sm text-[color:var(--silver)]">
                Automatic clustering
              </p>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
