"use client";

/**
 * Settings page. Phase 5.1 ships the hardware-acceleration section wired to a
 * real backend: it loads the persisted accel mode (`GET /api/settings`) and
 * saves changes (`PUT /api/settings`). Additional groups (library/storage, ML,
 * sharing, appearance, advanced) land as their backends do — we avoid stubbing
 * groups with no persistence behind them (YAGNI).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HardwareAccelSettings } from "@/components/hardware-accel-settings";
import { type AccelMode, getSettings, updateSettings } from "@/lib/api";

export default function SettingsPage() {
  const queryClient = useQueryClient();

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });

  const save = useMutation({
    mutationFn: (mode: AccelMode) => updateSettings({ accel_mode: mode }),
    onSuccess: (next) => {
      queryClient.setQueryData(["settings"], next);
      // The hardware report depends on the persisted mode — refresh it so the
      // resolved plan + fallback notice reflect the new choice.
      queryClient.invalidateQueries({ queryKey: ["hardware-report"] });
    },
  });

  return (
    <main className="settings-page">
      <h1>Settings</h1>
      <HardwareAccelSettings
        value={settings?.accel_mode}
        onChange={(mode) => save.mutate(mode)}
      />
      {save.isError && (
        <p data-testid="settings-save-error" role="alert">
          Couldn't save settings. Please try again.
        </p>
      )}
    </main>
  );
}
