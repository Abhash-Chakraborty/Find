"use client";

import { Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
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

  // Prevent hydration mismatch for active nav links
  const [mounted, setMounted] = useState(false);

  // Theme state
  const [theme, setTheme] = useState<Theme>("light");
  const [isMockMode, setIsMockMode] = useState(false);

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

  const toggleTheme = () => {
    const nextTheme: Theme = theme === "light" ? "dark" : "light";

    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
    document.documentElement.style.colorScheme = nextTheme;

    localStorage.setItem("find-theme", nextTheme);
    setTheme(nextTheme);
  };

  return (
    <div className="flex min-w-0 items-center gap-2 overflow-visible rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] p-1">
      {navLinks.map(({ href, label }) => {
        const isActive = mounted && pathname === href;

        return (
          <Link
            key={href}
            href={href}
            aria-current={isActive ? "page" : undefined}
            className={
              isActive
                ? "rounded-full bg-[color:var(--frost-soft)] px-3 py-1.5 text-sm font-medium text-[color:var(--near-white)] sm:px-4"
                : "rounded-full px-3 py-1.5 text-sm font-medium text-[color:var(--silver)] transition hover:bg-[color:var(--frost-soft)] hover:text-[color:var(--near-white)] sm:px-4"
            }
          >
            {label}
          </Link>
        );
      })}

      {isMockMode && (
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

      <button
        type="button"
        onClick={toggleTheme}
        aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
        className="ml-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] text-[color:var(--near-white)] transition hover:scale-105"
      >
        {theme === "light" ? (
          <Moon size={18} strokeWidth={2.2} />
        ) : (
          <Sun size={18} strokeWidth={2.2} />
        )}
      </button>
    </div>
  );
}
