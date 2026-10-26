"use client";

import { useEffect, useState } from "react";

/**
 * Track browser connectivity.
 *
 * `navigator.onLine` only reports whether the device has *a* network
 * connection, not whether the Find backend is reachable -- a laptop on a wifi
 * network with the backend stopped still reads `true`. It is used here purely
 * as the trigger for retrying a queued upload, which is cheap and safe to
 * attempt optimistically. Anything that needs to know the backend is actually
 * up should ask the API instead.
 */
export function useOnlineStatus(): boolean {
  // Start optimistic so server render and first client render agree; the effect
  // corrects it immediately on mount. Reading navigator here would hydrate
  // mismatched on a machine that is genuinely offline.
  const [online, setOnline] = useState(true);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();

    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  return online;
}
