"use client";

import {
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Upload,
  UserRound,
  X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  type CSSProperties,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";
import NavBar from "@/components/NavBar";
import { UniversalSearch } from "@/components/universal-search";
import {
  UploadStatusRing,
  useUploadStatus,
} from "@/components/upload-status-indicator";
import {
  applyThemePreference,
  readThemePreference,
  THEME_CHANGE_EVENT,
} from "@/lib/theme";

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

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const drawerRef = useRef<HTMLElement | null>(null);
  const drawerTriggerRef = useRef<HTMLButtonElement | null>(null);
  const shellless = isShelllessRoute(pathname);
  const uploadStatus = useUploadStatus();

  useEffect(() => {
    const apply = () => applyThemePreference(readThemePreference());
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    apply();
    media?.addEventListener("change", apply);
    window.addEventListener(THEME_CHANGE_EVENT, apply);
    try {
      setSidebarCollapsed(
        localStorage.getItem("find-sidebar-collapsed") === "true",
      );
    } catch {
      setSidebarCollapsed(false);
    }
    return () => {
      media?.removeEventListener("change", apply);
      window.removeEventListener(THEME_CHANGE_EVENT, apply);
    };
  }, []);

  useEffect(() => {
    if (pathname) setDrawerOpen(false);
  }, [pathname]);

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

  const toggleSidebar = () => {
    const next = !sidebarCollapsed;
    setSidebarCollapsed(next);
    try {
      localStorage.setItem("find-sidebar-collapsed", String(next));
    } catch {
      // Keep the preference for this session when storage is unavailable.
    }
  };

  const shellStyle = {
    "--sidebar-width": sidebarCollapsed ? "76px" : "256px",
  } as CSSProperties;

  return (
    <div
      style={shellStyle}
      className="min-h-dvh bg-[color:var(--void)] text-[color:var(--near-white)]"
    >
      <header
        inert={drawerOpen}
        aria-hidden={drawerOpen || undefined}
        className="fixed inset-x-0 top-0 z-50 flex h-[var(--nav-height)] items-center border-b border-[var(--frost)] bg-[color:var(--void)]/92 backdrop-blur-xl"
      >
        <div className="flex h-full items-center gap-2 px-3 lg:w-[var(--sidebar-width)] lg:shrink-0 lg:px-4">
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
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-[var(--frost)] bg-[color:var(--near-white)] p-1 shadow-sm dark:bg-[color:var(--frost-soft)]">
              <Image
                src="/Find-Logo.svg"
                alt=""
                width={36}
                height={36}
                priority
              />
            </span>
            <span
              className={`${sidebarCollapsed ? "lg:hidden" : ""} hidden truncate text-lg font-semibold tracking-tight sm:inline`}
            >
              FIND.
            </span>
          </Link>
        </div>

        <div className="flex min-w-0 flex-1 items-center justify-end gap-1.5 px-2 sm:gap-2 sm:px-4">
          <UniversalSearch />

          <Link
            href="/search"
            aria-label="Search your library"
            title="Search photos, albums and settings"
            className="icon-button md:hidden"
          >
            <Search className="h-4 w-4" />
          </Link>

          <Link
            href="/upload"
            title={
              uploadStatus.active
                ? `${uploadStatus.percent}% upload and indexing progress`
                : "Upload photos"
            }
            aria-label={
              uploadStatus.active
                ? `Upload status: ${uploadStatus.percent}%`
                : "Upload"
            }
            className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-[color:var(--near-white)] px-3 text-sm font-semibold text-[color:var(--void)] outline-none transition hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[color:var(--blue)] sm:px-4"
          >
            {uploadStatus.active ? (
              <UploadStatusRing />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            <span className="hidden sm:inline">
              {uploadStatus.active ? `${uploadStatus.percent}%` : "Upload"}
            </span>
          </Link>

          <Link
            href="/account"
            title="Account"
            className="icon-button"
            aria-label="Account"
          >
            <UserRound className="h-4 w-4" />
          </Link>
        </div>
      </header>

      <aside
        inert={drawerOpen}
        aria-hidden={drawerOpen || undefined}
        className="fixed bottom-0 left-0 top-[var(--nav-height)] z-40 hidden w-[var(--sidebar-width)] flex-col border-r border-[var(--frost)] bg-[color:var(--void)]/96 transition-[width] lg:flex"
      >
        <NavBar
          collapsed={sidebarCollapsed}
          className={`app-shell-scrollbar min-h-0 flex-1 overflow-y-auto py-5 ${sidebarCollapsed ? "px-2" : "px-4"}`}
        />
        <div
          className={`flex items-center border-t border-[var(--frost)] p-3 text-[10px] text-[color:var(--muted)] ${sidebarCollapsed ? "justify-center" : "justify-between gap-2"}`}
        >
          {!sidebarCollapsed && (
            <span className="truncate">
              Copyright 2026 Find · AGPL-3.0 License
            </span>
          )}
          <span className="shrink-0">v1.1.3</span>
        </div>
        <button
          type="button"
          onClick={toggleSidebar}
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="m-2 mt-0 flex h-9 items-center justify-center gap-2 rounded-lg text-xs text-[color:var(--silver)] hover:bg-[color:var(--surface-hover)]"
        >
          {sidebarCollapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <>
              <PanelLeftClose className="h-4 w-4" />
              <span>Collapse</span>
            </>
          )}
        </button>
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

      <main
        inert={drawerOpen}
        aria-hidden={drawerOpen || undefined}
        className="min-h-dvh min-w-0 pt-[var(--nav-height)] transition-[padding] lg:pl-[var(--sidebar-width)]"
      >
        {children}
      </main>
    </div>
  );
}
