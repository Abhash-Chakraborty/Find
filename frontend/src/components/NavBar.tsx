"use client";

import { Menu, Moon, Sun, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { getAppConfig } from "@/lib/api";

const navLinks = [
  { href: "/upload", label: "Upload" },
  { href: "/gallery", label: "Gallery" },
  { href: "/vault", label: "Vault" },
  { href: "/search", label: "Search" },
  { href: "/clusters", label: "Clusters" },
  { href: "/duplicates", label: "Duplicates" },
  { href: "/people", label: "People" },
];

type Theme = "light" | "dark";

export default function NavBar() {
  const pathname = usePathname();
  const previousPathname = useRef(pathname);

  // Prevent hydration mismatch for active nav links
  const [mounted, setMounted] = useState(false);

  // Theme state
  const [theme, setTheme] = useState<Theme>("light");
  const [isMockMode, setIsMockMode] = useState(false);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  useEffect(() => {
    setMounted(true);

    let initialTheme: Theme = "light";

    try {
      const savedTheme = localStorage.getItem("find-theme") as Theme | null;

      if (savedTheme === "light" || savedTheme === "dark") {
        // Use the user's previously saved preference
        initialTheme = savedTheme;
      } else {
        // No saved preference -> follow the operating system preference
        initialTheme = window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light";
      }
    } catch {
      // Fallback if localStorage is unavailable
      initialTheme = "light";
    }

    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(initialTheme);
    document.documentElement.dataset.theme = initialTheme;
    document.documentElement.style.colorScheme = initialTheme;

    setTheme(initialTheme);

    let cancelled = false;

    void getAppConfig()
      .then((config) => {
        if (!cancelled) {
          setIsMockMode(config.ml_mode === "mock");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setIsMockMode(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (previousPathname.current !== pathname) {
      previousPathname.current = pathname;
      setIsDrawerOpen(false);
    }
  }, [pathname]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsDrawerOpen(false);
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, []);

  const toggleTheme = () => {
    const nextTheme: Theme = theme === "light" ? "dark" : "light";

    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
    document.documentElement.style.colorScheme = nextTheme;

    localStorage.setItem("find-theme", nextTheme);
    setTheme(nextTheme);
  };

  const navContent = (isMobile = false) => (
    <>
      {navLinks.map(({ href, label }) => {
        const isActive = mounted && pathname === href;

        return (
          <Link
            key={href}
            href={href}
            onClick={() => isMobile && setIsDrawerOpen(false)}
            aria-current={isActive ? "page" : undefined}
            className={
              isActive
                ? `rounded-full bg-[color:var(--frost-soft)] px-3 py-1.5 text-sm font-medium text-[color:var(--near-white)] ${isMobile ? "w-full text-center py-3" : "sm:px-4"}`
                : `rounded-full px-3 py-1.5 text-sm font-medium text-[color:var(--silver)] transition hover:bg-[color:var(--frost-soft)] hover:text-[color:var(--near-white)] ${isMobile ? "w-full text-center py-3" : "sm:px-4"}`
            }
          >
            {label}
          </Link>
        );
      })}

      {!isMobile && isMockMode && (
        <div className="group relative flex shrink-0">
          <button
            type="button"
            className="rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] px-3 py-1.5 text-xs font-medium text-[color:var(--silver)] outline-none transition focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
            aria-label="Mock ML mode active"
            aria-describedby="mock-ml-mode-description"
          >
            Mock ML Mode
          </button>
          <div
            id="mock-ml-mode-description"
            role="tooltip"
            className="pointer-events-none absolute right-0 top-full z-50 mt-2 hidden w-64 rounded-lg border border-[var(--frost)] bg-[color:var(--void)] p-3 text-left text-xs leading-relaxed text-[color:var(--near-white)] shadow-xl group-focus-within:block group-hover:block"
          >
            Captions, OCR, embeddings, search, and clustering use mock-backed
            data in this environment.
          </div>
        </div>
      )}

      {!isMobile && (
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] text-[color:var(--near-white)] transition hover:scale-105 sm:ml-1"
        >
          {theme === "light" ? (
            <Moon size={18} strokeWidth={2.2} />
          ) : (
            <Sun size={18} strokeWidth={2.2} />
          )}
        </button>
      )}
    </>
  );

  return (
    <>
      <div className="flex items-center justify-end">
        <div className="hidden lg:flex items-center gap-2 rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] p-1">
          {navContent()}
        </div>

        <button
          type="button"
          onClick={() => setIsDrawerOpen(true)}
          className="flex lg:hidden h-10 w-10 items-center justify-center rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] text-[color:var(--near-white)] transition hover:bg-[color:var(--frost)]"
          aria-label="Open navigation menu"
        >
          <Menu size={24} />
        </button>
      </div>

      {mounted &&
        typeof document !== "undefined" &&
        createPortal(
          <>
            <button
              type="button"
              aria-label="Close navigation menu"
              className={`fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm transition-all duration-300 lg:hidden ${
                isDrawerOpen
                  ? "opacity-100 visible"
                  : "opacity-0 invisible pointer-events-none"
              }`}
              onClick={() => setIsDrawerOpen(false)}
            />
            <div
              className={`fixed right-0 top-0 z-[70] h-full w-[280px] border-l border-[var(--frost)] bg-[color:var(--void)] p-6 shadow-2xl transition-all duration-300 ease-in-out lg:hidden ${
                isDrawerOpen
                  ? "translate-x-0 visible"
                  : "translate-x-full invisible pointer-events-none"
              }`}
            >
              <div className="flex flex-col h-full">
                <div className="flex items-center justify-between mb-8">
                  <span className="text-xl font-bold tracking-tight text-[color:var(--near-white)]">
                    Menu
                  </span>
                  <button
                    type="button"
                    onClick={() => setIsDrawerOpen(false)}
                    className="h-10 w-10 flex items-center justify-center rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] text-[color:var(--near-white)] transition hover:bg-[color:var(--frost)]"
                    aria-label="Close navigation menu"
                  >
                    <X size={24} />
                  </button>
                </div>

                <nav className="flex flex-col gap-2">{navContent(true)}</nav>

                <div className="mt-auto pt-6 border-t border-[var(--frost)] flex flex-col gap-4">
                  {isMockMode && (
                    <div className="flex flex-col gap-2">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--silver)]">
                        Environment Status
                      </div>
                      <div className="rounded-xl border border-[var(--frost)] bg-[color:var(--frost-soft)] p-3">
                        <div className="flex items-center gap-2 text-xs font-semibold text-[color:var(--near-white)]">
                          <span className="h-2 w-2 rounded-full bg-[color:var(--blue)] animate-pulse" />
                          Mock ML Mode Active
                        </div>
                        <p className="mt-1 text-[11px] leading-relaxed text-[color:var(--silver)]">
                          OCR, embeddings, search, and clustering use
                          mock-backed data.
                        </p>
                      </div>
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={toggleTheme}
                    className="flex items-center justify-between rounded-xl border border-[var(--frost)] bg-[color:var(--frost-soft)] px-4 py-3 text-sm font-medium text-[color:var(--near-white)] transition hover:bg-[color:var(--frost)]"
                  >
                    <span className="flex items-center gap-3">
                      {theme === "light" ? (
                        <Moon size={18} strokeWidth={2} />
                      ) : (
                        <Sun size={18} strokeWidth={2} />
                      )}
                      {theme === "light" ? "Dark Mode" : "Light Mode"}
                    </span>
                    <span className="text-[10px] font-bold uppercase tracking-widest text-[color:var(--muted)]">
                      Toggle
                    </span>
                  </button>
                </div>
              </div>
            </div>
          </>,
          document.body,
        )}
    </>
  );
}
