"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ImagePreviewModal } from "@/components/image-preview-modal";
import { getImageDetail } from "@/lib/api";

function safeReturnPath(value: string | null): string {
  if (!value?.startsWith("/") || value.startsWith("//")) {
    return "/timeline";
  }
  return value;
}

export default function ImagePage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const mediaId = Number(params?.id);
  const returnPath = safeReturnPath(searchParams.get("return"));
  const image = useQuery({
    queryKey: ["image-detail", mediaId],
    queryFn: () => getImageDetail(mediaId),
    enabled: Number.isFinite(mediaId) && mediaId > 0,
    retry: false,
  });

  if (image.isPending) {
    return (
      <main className="grid min-h-[calc(100dvh-var(--nav-height))] place-items-center">
        <div className="flex items-center gap-2 text-sm text-[color:var(--silver)]">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading photo
        </div>
      </main>
    );
  }

  if (image.isError || !image.data) {
    return (
      <main className="grid min-h-[calc(100dvh-var(--nav-height))] place-items-center px-6 text-center">
        <div>
          <h1 className="text-2xl font-semibold">Photo unavailable</h1>
          <p className="mt-2 text-sm text-[color:var(--silver)]">
            It may have been moved to the vault or permanently deleted.
          </p>
          <Link
            href={returnPath}
            className="frost-button mt-5 px-4 py-2 text-sm"
          >
            Return to library
          </Link>
        </div>
      </main>
    );
  }

  return (
    <ImagePreviewModal
      media={image.data}
      syncUrl={false}
      onClose={() => router.replace(returnPath, { scroll: false })}
      onDeleted={() => router.replace(returnPath, { scroll: false })}
    />
  );
}
