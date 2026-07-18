"use client";

/**
 * Share-link management for an album (frontend for Phase 4.3 backend).
 *
 * Lists existing links for the album, creates new ones (with optional
 * password, expiry, and download/EXIF options), shows the share URL once on
 * creation, and revokes links. The raw key is only ever returned by the create
 * call, so we surface it immediately for copying and never re-display it.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Link2, Loader2, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  createSharedLink,
  deleteSharedLink,
  getSharedLinks,
  type SharedLink,
} from "@/lib/api";

interface AlbumShareLinksProps {
  albumId: number;
}

export function AlbumShareLinks({ albumId }: AlbumShareLinksProps) {
  const queryClient = useQueryClient();
  const [password, setPassword] = useState("");
  const [allowDownload, setAllowDownload] = useState(true);
  const [createdUrl, setCreatedUrl] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["shared-links"],
    queryFn: getSharedLinks,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createSharedLink({
        album_id: albumId,
        password: password.trim() || undefined,
        allow_download: allowDownload,
      }),
    onSuccess: (link) => {
      queryClient.invalidateQueries({ queryKey: ["shared-links"] });
      setPassword("");
      setCreatedUrl(link.url ?? null);
      toast.success("Share link created");
    },
    onError: () => toast.error("Couldn't create share link"),
  });

  const revokeMutation = useMutation({
    mutationFn: (linkId: number) => deleteSharedLink(linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shared-links"] });
      toast.success("Share link revoked");
    },
    onError: () => toast.error("Couldn't revoke link"),
  });

  const copy = async (url: string) => {
    try {
      await navigator.clipboard?.writeText(url);
      toast.success("Link copied");
    } catch {
      toast.error("Couldn't copy");
    }
  };

  // Only links for THIS album.
  const links: SharedLink[] = (data?.shared_links ?? []).filter(
    (l) => l.album_id === albumId,
  );

  return (
    <section data-testid="album-share-links" aria-labelledby="share-heading">
      <h2 id="share-heading" className="mb-3 flex items-center gap-2 text-lg">
        <Link2 size={18} /> Share
      </h2>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Optional password"
          aria-label="Optional share password"
          className="rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] px-3 py-1.5 text-sm"
        />
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={allowDownload}
            onChange={(e) => setAllowDownload(e.target.checked)}
          />
          Allow download
        </label>
        <button
          type="button"
          data-testid="create-share-link"
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          className="inline-flex items-center gap-2 rounded-full border border-[var(--frost)] px-4 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          {createMutation.isPending ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Link2 size={16} />
          )}
          Create link
        </button>
      </div>

      {createdUrl && (
        <div
          data-testid="created-share-url"
          className="mb-4 flex items-center gap-2 rounded-xl border border-[var(--blue)] bg-[color:var(--frost-soft)] p-3 text-sm"
        >
          <code className="flex-1 truncate">{createdUrl}</code>
          <button
            type="button"
            aria-label="Copy share link"
            onClick={() => copy(createdUrl)}
            className="rounded-full p-1.5"
          >
            <Copy size={16} />
          </button>
        </div>
      )}

      {isLoading && (
        <div role="status" aria-label="Loading share links">
          <Loader2 className="animate-spin" />
        </div>
      )}

      {!isLoading && links.length === 0 && (
        <p data-testid="no-share-links" className="muted-copy text-sm">
          No share links yet.
        </p>
      )}

      <ul className="flex flex-col gap-2">
        {links.map((link) => (
          <li
            key={link.id}
            data-testid={`share-link-${link.id}`}
            className="flex items-center justify-between gap-3 rounded-xl border border-[var(--frost)] p-3 text-sm"
          >
            <span className="flex items-center gap-2">
              {link.has_password && (
                <span className="rounded-full bg-[color:var(--frost-soft)] px-2 py-0.5 text-xs">
                  Password
                </span>
              )}
              {!link.allow_download && (
                <span className="rounded-full bg-[color:var(--frost-soft)] px-2 py-0.5 text-xs">
                  View only
                </span>
              )}
              <span className="muted-copy text-xs">
                Created {link.created_at?.slice(0, 10) ?? "—"}
              </span>
            </span>
            <button
              type="button"
              aria-label="Revoke share link"
              data-testid={`revoke-share-${link.id}`}
              onClick={() => revokeMutation.mutate(link.id)}
              className="rounded-full p-1.5 text-[color:var(--silver)] hover:text-[color:var(--near-white)]"
            >
              <Trash2 size={16} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
