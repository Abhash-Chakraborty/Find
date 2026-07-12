"use client";

import { Menu, Moon, Search, Sun, Upload, UserRound, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useRef, useState } from "react";
import NavBar from "@/components/NavBar";

type Theme = "light" | "dark";

type AppShellProps = {
  children: ReactNode;
};

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function isShelllessRoute(pathname: string) {
  return (
    pathname === "/public" ||
    pathname.startsWith("/public/") ||
    pathname === "/auth" ||
    pathname.startsWith("/auth/")
  );
}

function applyTheme(theme: Theme) {
  document.documentElement.classList.remove("light", "dark");
  document.documentElement.classList.add(theme);
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>("light");
  const drawerRef = useRef<HTMLElement | null>(null);
  const drawerTriggerRef = useRef<HTMLButtonElement | null>(null);
  const shellless = isShelllessRoute(pathname);

  useEffect(() => {
    let initialTheme: Theme = "light";

    try {
      const saved = localStorage.getItem("find-theme");
      if (saved === "light" || saved === "dark") {
        initialTheme = saved;
      } else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
        initialTheme = "dark";
      }
    } catch {
      initialTheme = "light";
    }

    applyTheme(initialTheme);
    setTheme(initialTheme);
  }, []);

  useEffect(() => {
    const handleSearchShortcut = (event: KeyboardEvent) => {
      if (shellless) {
        return;
      }

      const target = event.target;
      const isTyping =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable);

      if (isTyping) {
        return;
      }

      const isCommandSearch =
        event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey);
      if (event.key === "/" || isCommandSearch) {
        event.preventDefault();
        router.push("/search");
      }
    };

    window.addEventListener("keydown", handleSearchShortcut);
    return () => window.removeEventListener("keydown", handleSearchShortcut);
  }, [router, shellless]);

  useEffect(() => {
    if (!drawerOpen) {
      return;
    }

    const drawer = drawerRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusable = drawer
      ? Array.from(drawer.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
      : [];
    focusable[0]?.focus();

    const handleDrawerKeys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setDrawerOpen(false);
        return;
      }

      if (event.key !== "Tab" || focusable.length === 0) {
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };

    window.addEventListener("keydown", handleDrawerKeys);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleDrawerKeys);
      drawerTriggerRef.current?.focus();
    };
  }, [drawerOpen]);

  if (shellless) {
    return <>{children}</>;
  }

  const toggleTheme = () => {
    const nextTheme: Theme = theme === "light" ? "dark" : "light";
    applyTheme(nextTheme);
    try {
      localStorage.setItem("find-theme", nextTheme);
    } catch {
      // Theme still applies for this session when storage is unavailable.
    }
    setTheme(nextTheme);
  };

  return (
    <div className="min-h-dvh bg-[color:var(--void)] text-[color:var(--near-white)]">
      <header className="fixed inset-x-0 top-0 z-50 flex h-[var(--nav-height)] items-center border-b border-[var(--frost)] bg-[color:var(--void)]/92 backdrop-blur-xl">
        <div className="flex h-full items-center gap-2 border-r border-transparent px-3 lg:w-[var(--sidebar-width)] lg:shrink-0 lg:border-[var(--frost)] lg:px-5">
          <button
            ref={drawerTriggerRef}
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="icon-button lg:hidden"
            aria-label="Open navigation menu"
            aria-expanded={drawerOpen}
            aria-controls="mobile-navigation"
          >
            <Menu className="h-5 w-5" />
          </button>

          <Link
            href="/timeline"
            className="group flex min-w-0 items-center gap-2 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
            aria-label="FIND. Photos"
          >
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-[var(--frost)] bg-[color:var(--near-white)] p-1 shadow-sm transition group-hover:scale-105 dark:bg-[color:var(--frost-soft)]">
              <Image
                src="/Find-Logo.svg"
                alt=""
                width={36}
                height={36}
                priority
              />
            </span>
            <span className="hidden truncate text-lg font-semibold tracking-tight sm:inline">
              FIND.
            </span>
          </Link>
        </div>

        <div className="flex min-w-0 flex-1 items-center justify-end gap-1.5 px-2 sm:gap-2 sm:px-4">
          <Link
            href="/search"
            aria-label="Search your library"
            aria-keyshortcuts="/ Control+K Meta+K"
            className="hidden h-10 min-w-0 max-w-md flex-1 items-center gap-3 rounded-xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-3 text-sm text-[color:var(--silver)] outline-none transition hover:border-[var(--frost-strong)] hover:text-[color:var(--near-white)] focus-visible:ring-2 focus-visible:ring-[color:var(--blue)] md:flex"
          >
            <Search className="h-4 w-4 shrink-0" />
            <span className="truncate">Search your library</span>
            <kbd className="ml-auto rounded-md border border-[var(--frost)] px-1.5 py-0.5 text-[10px] text-[color:var(--muted)]">
              /
            </kbd>
          </Link>

          <Link
            href="/search"
            aria-label="Search your library"
            className="icon-button md:hidden"
          >
            <Search className="h-4 w-4" />
          </Link>

          <Link
            href="/upload"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-[color:var(--near-white)] px-3 text-sm font-semibold text-[color:var(--void)] outline-none transition hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[color:var(--blue)] sm:px-4"
          >
            <Upload className="h-4 w-4" />
            <span className="hidden sm:inline">Upload</span>
          </Link>

          <button
            type="button"
            onClick={toggleTheme}
            className="icon-button"
            aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
          >
            {theme === "light" ? (
              <Moon className="h-4 w-4" />
            ) : (
              <Sun className="h-4 w-4" />
            )}
          </button>

          <Link href="/account" className="icon-button" aria-label="Account">
            <UserRound className="h-4 w-4" />
          </Link>
        </div>
      </header>

      <aside className="fixed bottom-0 left-0 top-[var(--nav-height)] z-40 hidden w-[var(--sidebar-width)] flex-col border-r border-[var(--frost)] bg-[color:var(--void)]/96 lg:flex">
        <NavBar className="app-shell-scrollbar min-h-0 flex-1 overflow-y-auto px-4 py-6" />
        <p className="border-t border-[var(--frost)] px-5 py-4 text-[10px] leading-4 text-[color:var(--muted)]">
          Copyright 2026 Find
          <br />
          AGPL-3.0 License
        </p>
      </aside>

      <button
        type="button"
        aria-label="Close navigation menu"
        onClick={() => setDrawerOpen(false)}
        className={`fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm transition lg:hidden ${
          drawerOpen
            ? "visible opacity-100"
            : "invisible pointer-events-none opacity-0"
        }`}
      />

      <aside
        ref={drawerRef}
        id="mobile-navigation"
        data-mobile-drawer
        role="dialog"
        aria-modal="true"
        aria-label="Navigation menu"
        aria-hidden={!drawerOpen}
        inert={!drawerOpen}
        className={`safe-bottom fixed inset-y-0 left-0 z-[70] flex w-[min(88vw,320px)] flex-col border-r border-[var(--frost)] bg-[color:var(--void)] shadow-2xl transition-transform duration-200 lg:hidden ${
          drawerOpen
            ? "visible translate-x-0"
            : "invisible pointer-events-none -translate-x-full"
        }`}
      >
        <div className="flex h-[var(--nav-height)] shrink-0 items-center justify-between border-b border-[var(--frost)] px-4">
          <span className="text-sm font-semibold">Browse Find</span>
          <button
            type="button"
            onClick={() => setDrawerOpen(false)}
            className="icon-button"
            aria-label="Close navigation menu"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <NavBar
          onNavigate={() => setDrawerOpen(false)}
          className="app-shell-scrollbar min-h-0 flex-1 overflow-y-auto px-4 py-5"
        />
        <p className="border-t border-[var(--frost)] px-5 pt-4 text-[10px] leading-4 text-[color:var(--muted)]">
          Copyright 2026 Find - AGPL-3.0 License
        </p>
      </aside>

      <main className="min-h-dvh min-w-0 pt-[var(--nav-height)] lg:pl-[var(--sidebar-width)]">
        {children}
      </main>
    </div>
  );
}
