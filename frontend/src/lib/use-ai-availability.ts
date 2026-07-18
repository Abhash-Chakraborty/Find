"use client";

import { useQuery } from "@tanstack/react-query";
import { getRuntimeConfig } from "@/lib/api";

export function useAiAvailability() {
  const runtime = useQuery({
    queryKey: ["runtime-config"],
    queryFn: getRuntimeConfig,
  });
  const aiUnavailable = runtime.data ? !runtime.data.ai_enabled : false;
  return {
    aiUnavailable,
    unavailableMessage: aiUnavailable
      ? "Local AI is disabled in this installed build. Enable an AI profile in Settings."
      : null,
    runtime,
  };
}
