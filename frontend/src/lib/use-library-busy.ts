"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getGalleryCounts } from "@/lib/api";
import {
  isProcessingUpload,
  useUploadQueueStore,
} from "@/store/uploadQueueStore";

// Clustering runs as its own job once an image is indexed, so pages keep
// refreshing for a short while after the last image settles.
export const LIBRARY_SETTLE_MS = 30_000;

/**
 * True while images are being indexed (uploads from this tab, or anything
 * the server reports as processing) and for a short while after.
 */
export function useLibraryBusy(): boolean {
  const uploading = useUploadQueueStore((state) =>
    state.items.some(isProcessingUpload),
  );
  // Same key as the gallery's unfiltered counts, so both share one request.
  const counts = useQuery({
    queryKey: ["gallery-counts", false],
    queryFn: () => getGalleryCounts(),
    refetchInterval: (query) =>
      (query.state.data?.processing ?? 0) > 0 ? 5000 : false,
    // Uploads from another device show up when this tab is focused again.
    refetchOnWindowFocus: true,
  });
  const processing = uploading || (counts.data?.processing ?? 0) > 0;
  const [settling, setSettling] = useState(false);

  useEffect(() => {
    if (processing) {
      setSettling(true);
      return;
    }
    const timer = window.setTimeout(
      () => setSettling(false),
      LIBRARY_SETTLE_MS,
    );
    return () => window.clearTimeout(timer);
  }, [processing]);

  return processing || settling;
}
