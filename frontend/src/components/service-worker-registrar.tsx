"use client";

import { useEffect } from "react";

/**
 * Registers the service worker that provides the offline shell (issue #259).
 *
 * Renders nothing. Mounted once from the root layout.
 */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (!shouldRegisterServiceWorker()) {
      return;
    }

    // Registration is best-effort. A failure here means no offline shell, which
    // is a degraded experience -- not a broken app -- so it must never surface
    // as an error to the user.
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .catch((error) => {
        console.warn("Service worker registration failed", error);
      });
  }, []);

  return null;
}

/**
 * Three environments must be excluded, for different reasons:
 *
 * - Development: a cached shell across `next dev` rebuilds produces stale-asset
 *   bugs that look like application bugs.
 * - Tauri desktop: the shell is loaded from the bundle over a custom protocol,
 *   so there is no network to be offline from and nothing to cache.
 * - Non-secure contexts: the browser rejects registration anyway.
 */
function shouldRegisterServiceWorker(): boolean {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) {
    return false;
  }
  if (process.env.NODE_ENV !== "production") {
    return false;
  }
  if (!window.isSecureContext) {
    return false;
  }
  // Tauri serves the static export over tauri:// or asset://, never http(s).
  return (
    window.location.protocol === "https:" ||
    window.location.protocol === "http:"
  );
}
