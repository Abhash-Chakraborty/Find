"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navLinks = [
  { href: "/upload", label: "Upload" },
  { href: "/gallery", label: "Gallery" },
  { href: "/search", label: "Search" },
  { href: "/clusters", label: "Clusters" },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <div className="flex min-w-0 items-center gap-1 overflow-x-auto rounded-full border border-[var(--frost)] bg-white/[0.03] p-1">
      {navLinks.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          aria-current={pathname === href ? "page" : undefined}
          className={
            pathname === href
              ? "rounded-full px-3 py-1.5 text-sm font-medium text-[#f0f0f0] bg-white/[0.12] sm:px-4"
              : "rounded-full px-3 py-1.5 text-sm font-medium text-[#a1a4a5] transition hover:bg-white/[0.08] hover:text-[#f0f0f0] sm:px-4"
          }
        >
          {label}
        </Link>
      ))}
    </div>
  );
}
