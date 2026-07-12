"use client";

/**
 * Public shared-album view (frontend for Phase 4.3 backend).
 *
 * Opened via a share URL `/public/shared/[key]`. Loads the album through the
 * share-scoped public endpoint, prompting for a password when the link
 * requires one (401). Only renders the share-scoped thumbnail/original URLs the
 * backend returns — never raw storage keys.
 */

import { useQuery } from "@tanstack/react-query";
import { Loader2, Lock } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import { TimelineMediaView } from "@/components/timeline-media-view";
import { getPublicSharedAlbum, type PublicSharedAlbum } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function withBase(url: string): string {
  return url.startsWith("/api/") ? `${API_BASE}${url}` : url;
}

export default function PublicSharedAlbumPage() {
  const params = useParams();
  const key = String(params?.key ?? "");
  const [password, setPassword] = useState("");
  const [submittedPassword, setSubmittedPassword] = useState<
    string | undefined
  >(undefined);

  const { data, isLoading, error } = useQuery<PublicSharedAlbum, unknown>({
    queryKey: ["public-shared", key, submittedPassword ?? null],
    queryFn: () => getPublicSharedAlbum({ key, password: submittedPassword }),
    enabled: key.length > 0,
    retry: false,
  });

  // A 401 means the link needs a (correct) password.
  const needsPassword =
    !!error &&
    typeof error === "object" &&
    (error as { response?: { status?: number } }).response?.status === 401;

  if (isLoading) {
    return (
      <main className="page-shell">
        <div role="status" aria-label="Loading shared album">
          <Loader2 className="animate-spin" />
        </div>
      </main>
    );
  }

  if (needsPassword) {
    return (
      <main className="page-shell">
        <div className="container-shell py-14">
          <form
            data-testid="password-gate"
            onSubmit={(e) => {
              e.preventDefault();
              setSubmittedPassword(password);
            }}
            className="mx-auto flex max-w-sm flex-col gap-3"
          >
            <h1 className="flex items-center gap-2 text-xl">
              <Lock size={18} /> This album is password protected
            </h1>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              aria-label="Album password"
              className="rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] px-4 py-2"
            />
            <button
              type="submit"
              className="rounded-full border border-[var(--frost)] px-4 py-2 text-sm font-medium"
            >
              Unlock
            </button>
          </form>
        </div>
      </main>
    );
  }

  if (error || !data) {
    return (
      <main className="page-shell">
        <div className="container-shell py-14 text-center">
          <p data-testid="share-not-found" className="muted-copy">
            This shared album is unavailable or has expired.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <div className="container-shell py-10 md:py-14">
        <h1 className="section-heading text-4xl font-medium">
          {data.album.name}
        </h1>
        {data.album.description && (
          <p className="muted-copy mt-1 text-sm">{data.album.description}</p>
        )}
        <p className="muted-copy mt-1 text-xs">{data.total} photos</p>

        <TimelineMediaView
          className="mt-6"
          items={data.items}
          getId={(item) => item.id}
          getDate={(item) => item.created_at}
          getWidth={(item) => item.width}
          getHeight={(item) => item.height}
          // Security boundary: both URLs come from the share response. The
          // timeline adapter never synthesizes a private `/api/image` route.
          getThumbnailUrl={(item) => withBase(item.thumbnail_url)}
          getOriginalUrl={(item) => (item.url ? withBase(item.url) : null)}
          getAlt={(item) => item.filename}
          getItemTestId={(item) => `shared-asset-${item.id}`}
          getOpenTestId={(item) => `open-shared-asset-${item.id}`}
          empty={<p className="muted-copy mt-6">This album has no photos.</p>}
        />
      </div>
    </main>
  );
}
