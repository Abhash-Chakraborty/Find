"use client";

import { Archive, Heart, Images, Search, Settings, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  type Album,
  getAlbums,
  type SearchResult,
  searchImages,
} from "@/lib/api";

const DESTINATIONS = [
  {
    label: "Photos",
    detail: "Browse your library",
    href: "/timeline",
    icon: Images,
  },
  {
    label: "Favorites",
    detail: "Your favorite photos",
    href: "/timeline?liked=true",
    icon: Heart,
  },
  {
    label: "Archive",
    detail: "Archived photos",
    href: "/archive",
    icon: Archive,
  },
  {
    label: "Settings · Appearance",
    detail: "Light, dark, or system theme",
    href: "/settings#appearance",
    icon: Settings,
  },
  {
    label: "Settings · Local AI",
    detail: "AI mode and installed build",
    href: "/settings#ai-runtime-heading",
    icon: Settings,
  },
  {
    label: "Settings · Performance",
    detail: "CPU and GPU acceleration",
    href: "/settings#hardware",
    icon: Settings,
  },
  {
    label: "Settings · Privacy",
    detail: "Map and vault controls",
    href: "/settings#privacy",
    icon: Settings,
  },
] as const;

export function UniversalSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const normalized = query.trim().toLowerCase();
  const [albums, setAlbums] = useState<Album[]>([]);
  const [images, setImages] = useState<SearchResult[]>([]);

  useEffect(() => {
    let active = true;
    void getAlbums()
      .then((result) => {
        if (active) setAlbums(result.albums);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (normalized.length < 2) {
      setImages([]);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      void searchImages({ query: normalized, limit: 5, skip: 0 })
        .then((result) => {
          if (active) setImages(result.results);
        })
        .catch(() => {
          if (active) setImages([]);
        });
    }, 180);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [normalized]);

  const destinations = useMemo(() => {
    const base = normalized
      ? DESTINATIONS.filter((item) =>
          `${item.label} ${item.detail}`.toLowerCase().includes(normalized),
        )
      : DESTINATIONS.slice(0, 4);
    const albumMatches = albums
      .filter(
        (album) => !normalized || album.name.toLowerCase().includes(normalized),
      )
      .slice(0, 4)
      .map((album) => ({
        label: album.name,
        detail: `${album.asset_count} photos · Album`,
        href: `/albums/${album.id}`,
        icon: Images,
      }));
    return [...base, ...albumMatches];
  }, [albums, normalized]);

  const navigate = (href: string) => {
    setOpen(false);
    setQuery("");
    router.push(href);
  };

  return (
    <search
      ref={wrapperRef}
      className="relative hidden min-w-0 max-w-xl flex-1 md:block"
      onBlur={(event) => {
        if (!wrapperRef.current?.contains(event.relatedTarget as Node | null))
          setOpen(false);
      }}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (normalized)
            navigate(`/search?q=${encodeURIComponent(query.trim())}`);
        }}
      >
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-[color:var(--muted)]"
        />
        <input
          ref={inputRef}
          aria-label="Search everything"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search photos, albums and settings"
          className="h-10 w-full rounded-xl border border-[var(--frost)] bg-[color:var(--surface-soft)] pl-10 pr-12 text-sm outline-none transition placeholder:text-[color:var(--muted)] hover:border-[var(--frost-strong)] focus:border-[var(--frost-strong)] focus:ring-2 focus:ring-[color:var(--blue)]"
        />
        {query ? (
          <button
            type="button"
            title="Clear search"
            aria-label="Clear search"
            onClick={() => {
              setQuery("");
              inputRef.current?.focus();
            }}
            className="absolute right-2 top-2 icon-button h-6 w-6"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        ) : (
          <kbd className="pointer-events-none absolute right-3 top-2.5 rounded border border-[var(--frost)] px-1.5 text-[10px] text-[color:var(--muted)]">
            /
          </kbd>
        )}
      </form>

      {open && (
        <div
          className="absolute right-0 top-12 z-[90] max-h-[70vh] w-full min-w-[22rem] overflow-y-auto rounded-2xl border border-[var(--frost-strong)] bg-[color:var(--void)] p-2 shadow-2xl"
          role="dialog"
          aria-label="Universal search results"
        >
          {destinations.map((item) => {
            const Icon = item.icon;
            return (
              <button
                type="button"
                key={item.href}
                onClick={() => navigate(item.href)}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-[color:var(--surface-hover)]"
              >
                <Icon className="h-4 w-4 shrink-0 text-[color:var(--muted)]" />
                <span className="min-w-0">
                  <strong className="block truncate text-sm">
                    {item.label}
                  </strong>
                  <span className="block truncate text-xs text-[color:var(--muted)]">
                    {item.detail}
                  </span>
                </span>
              </button>
            );
          })}
          {images.map((result) => (
            <button
              type="button"
              key={result.media_id}
              onClick={() => navigate(`/gallery?media=${result.media_id}`)}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-[color:var(--surface-hover)]"
            >
              <Search className="h-4 w-4 text-[color:var(--muted)]" />
              <span className="min-w-0">
                <strong className="block truncate text-sm">
                  {result.metadata.filename}
                </strong>
                <span className="block truncate text-xs text-[color:var(--muted)]">
                  Photo · {Math.round(result.similarity * 100)}% match
                </span>
              </span>
            </button>
          ))}
          {normalized && (
            <button
              type="button"
              onClick={() =>
                navigate(`/search?q=${encodeURIComponent(query.trim())}`)
              }
              className="mt-1 w-full rounded-xl border border-[var(--frost)] px-3 py-2 text-left text-sm font-medium hover:bg-[color:var(--surface-hover)]"
            >
              Search all photos for “{query.trim()}”
            </button>
          )}
        </div>
      )}
    </search>
  );
}
