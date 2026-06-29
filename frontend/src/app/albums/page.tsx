"use client";

/**
 * Albums list + create page (frontend for the Phase 4.2 backend).
 * Lists albums, creates a new one, and links into each album's detail page.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderPlus, Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { type Album, createAlbum, getAlbums } from "@/lib/api";
import { resolveMediaUrl } from "@/lib/media";

export default function AlbumsPage() {
  const queryClient = useQueryClient();
  const [newName, setNewName] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["albums"],
    queryFn: getAlbums,
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createAlbum({ name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["albums"] });
      setNewName("");
      toast.success("Album created");
    },
    onError: () => toast.error("Couldn't create album"),
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (name) {
      createMutation.mutate(name);
    }
  };

  const albums: Album[] = data?.albums ?? [];

  return (
    <main className="page-shell">
      <div className="container-shell py-10 md:py-14">
        <h1 className="section-heading mb-6 text-4xl font-medium">Albums</h1>

        <form onSubmit={handleCreate} className="mb-8 flex gap-2">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="New album name"
            aria-label="New album name"
            maxLength={255}
            className="flex-1 rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] px-4 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={!newName.trim() || createMutation.isPending}
            className="inline-flex items-center gap-2 rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)] px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {createMutation.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <FolderPlus size={16} />
            )}
            Create
          </button>
        </form>

        {isLoading && (
          <div role="status" aria-label="Loading albums">
            <Loader2 className="animate-spin" />
          </div>
        )}

        {!isLoading && isError && (
          <p data-testid="albums-error" role="alert" className="muted-copy">
            Couldn't load albums. Please try again.
          </p>
        )}

        {!isLoading && !isError && albums.length === 0 && (
          <p data-testid="albums-empty" className="muted-copy">
            No albums yet. Create your first one above.
          </p>
        )}

        <ul className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
          {albums.map((album) => (
            <li key={album.id}>
              <Link
                href={`/albums/${album.id}`}
                data-testid={`album-card-${album.id}`}
                className="block rounded-2xl border border-[var(--frost)] bg-[color:var(--frost-soft)] p-3 transition hover:border-[var(--blue)]"
              >
                <div className="mb-2 aspect-square overflow-hidden rounded-xl bg-[color:var(--surface-soft)]">
                  {album.cover_thumbnail_url && (
                    // biome-ignore lint/a11y/useAltText: cover thumbnail
                    <img
                      src={resolveMediaUrl(album.cover_thumbnail_url) ?? undefined}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  )}
                </div>
                <div className="text-sm font-medium">{album.name}</div>
                <div className="muted-copy text-xs">
                  {album.asset_count} photo{album.asset_count === 1 ? "" : "s"}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
