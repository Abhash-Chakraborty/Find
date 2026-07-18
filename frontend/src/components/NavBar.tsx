"use client";

import {
  Archive,
  Copy,
  Heart,
  Images,
  Library,
  LockKeyhole,
  type LucideIcon,
  Map as MapIcon,
  ScanSearch,
  Search,
  Settings,
  Trash2,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

type NavGroup = {
  label: string;
  items: NavItem[];
};

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Library",
    items: [
      { href: "/timeline", label: "Photos", icon: Images },
      { href: "/search", label: "Search", icon: Search },
      { href: "/map", label: "Map", icon: MapIcon },
      { href: "/people", label: "People", icon: Users },
    ],
  },
  {
    label: "Sharing",
    items: [
      { href: "/albums", label: "Albums", icon: Library },
      { href: "/timeline?liked=true", label: "Favorites", icon: Heart },
    ],
  },
  {
    label: "Utilities",
    items: [
      { href: "/duplicates", label: "Duplicates", icon: Copy },
      { href: "/clusters", label: "Clusters", icon: ScanSearch },
      { href: "/archive", label: "Archive", icon: Archive },
      { href: "/vault", label: "Vault", icon: LockKeyhole },
      { href: "/trash", label: "Trash", icon: Trash2 },
    ],
  },
  {
    label: "System",
    items: [{ href: "/settings", label: "Settings", icon: Settings }],
  },
];

function routePath(href: string) {
  return href.split("?")[0] ?? href;
}

function isCurrentRoute(pathname: string, href: string, search: string) {
  const path = routePath(href);
  if (path === "/timeline" && pathname === "/timeline") {
    const favoriteTimeline =
      new URLSearchParams(search).get("liked") === "true";
    return href.includes("liked=true") ? favoriteTimeline : !favoriteTimeline;
  }
  return pathname === path || pathname.startsWith(`${path}/`);
}

type NavBarProps = {
  onNavigate?: () => void;
  className?: string;
  collapsed?: boolean;
};

export default function NavBar({
  onNavigate,
  className,
  collapsed = false,
}: NavBarProps) {
  const pathname = usePathname();
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (pathname) setSearch(window.location.search);
  }, [pathname]);

  return (
    <nav aria-label="Main navigation" className={className}>
      <div className={collapsed ? "space-y-3" : "space-y-7"}>
        {NAV_GROUPS.map((group) => (
          <section key={group.label} aria-labelledby={`nav-${group.label}`}>
            <h2
              id={`nav-${group.label}`}
              className={`${collapsed ? "sr-only" : "mb-2 px-3"} text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--muted)]`}
            >
              {group.label}
            </h2>
            <ul className="space-y-1">
              {group.items.map((item) => {
                const active = isCurrentRoute(pathname, item.href, search);
                const Icon = item.icon;

                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      title={item.label}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={`group flex min-h-10 items-center rounded-xl py-2 text-sm font-medium outline-none transition focus-visible:ring-2 focus-visible:ring-[color:var(--blue)] ${collapsed ? "justify-center px-2" : "gap-3 px-3"} ${
                        active
                          ? "bg-[color:var(--near-white)] text-[color:var(--void)] shadow-sm"
                          : "text-[color:var(--silver)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--near-white)]"
                      }`}
                    >
                      <Icon
                        aria-hidden="true"
                        className={`h-[18px] w-[18px] shrink-0 ${
                          active
                            ? "text-[color:var(--void)]"
                            : "text-[color:var(--muted)] transition group-hover:text-[color:var(--near-white)]"
                        }`}
                      />
                      <span className={collapsed ? "sr-only" : undefined}>
                        {item.label}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </nav>
  );
}
