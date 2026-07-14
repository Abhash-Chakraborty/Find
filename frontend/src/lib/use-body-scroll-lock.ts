"use client";

import { useEffect } from "react";

let activeLocks = 0;
let previousOverflow = "";

/** Keeps the document stationary while one or more overlays are mounted. */
export function useBodyScrollLock() {
  useEffect(() => {
    if (activeLocks === 0) {
      previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    activeLocks += 1;

    return () => {
      activeLocks = Math.max(0, activeLocks - 1);
      if (activeLocks === 0) {
        document.body.style.overflow = previousOverflow;
      }
    };
  }, []);
}
