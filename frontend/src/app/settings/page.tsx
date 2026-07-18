"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Cpu,
  MapPinned,
  Palette,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
} from "lucide-react";
import { AiRuntimeSettings } from "@/components/ai-runtime-settings";
import { AppearanceSettings } from "@/components/appearance-settings";
import { HardwareAccelSettings } from "@/components/hardware-accel-settings";
import { MapPrivacySettings } from "@/components/map-privacy-settings";
import { TrashRetentionSettings } from "@/components/trash-retention-settings";
import { type AppSettings, getSettings, updateSettings } from "@/lib/api";

const SECTIONS = [
  { href: "#appearance", label: "Appearance", icon: Palette },
  { href: "#hardware", label: "Performance", icon: Cpu },
  { href: "#ai-runtime-heading", label: "Local AI", icon: Sparkles },
  { href: "#privacy", label: "Privacy", icon: MapPinned },
  { href: "#trash-retention", label: "Trash", icon: Trash2 },
] as const;

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });

  const save = useMutation({
    mutationFn: (patch: Partial<AppSettings>) => updateSettings(patch),
    onSuccess: (next) => {
      queryClient.setQueryData(["settings"], next);
      queryClient.invalidateQueries({ queryKey: ["hardware-report"] });
      queryClient.invalidateQueries({ queryKey: ["runtime-config"] });
      queryClient.invalidateQueries({ queryKey: ["map-markers"] });
    },
  });

  return (
    <main className="page-surface pb-20 pt-8 sm:pt-10 lg:pb-24 lg:pt-12">
      <div className="mx-auto w-full max-w-6xl">
        <header className="mb-7 border-b border-[color:var(--frost)] pb-5 sm:mb-8">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="text-sm font-semibold text-[color:var(--blue)]">
                  System
                </span>
                <span aria-hidden="true" className="text-[color:var(--muted)]">
                  /
                </span>
                <h1 className="section-heading text-4xl font-semibold tracking-[-0.035em]">
                  Settings
                </h1>
              </div>
              <p className="mt-2 text-sm text-[color:var(--silver)]">
                Appearance, local AI, privacy, and retention.
              </p>
            </div>
            <div className="min-h-8" aria-live="polite">
              {save.isPending && (
                <span className="inline-flex items-center gap-2 rounded-full border border-[color:var(--frost)] bg-[color:var(--surface-soft)] px-3 py-1.5 text-xs text-[color:var(--silver)]">
                  <RefreshCw
                    aria-hidden="true"
                    className="animate-spin"
                    size={13}
                  />
                  Saving changes
                </span>
              )}
              {save.isSuccess && !save.isPending && (
                <span className="inline-flex items-center gap-2 rounded-full border border-[color:var(--status-indexed-border)] bg-[color:var(--green-soft)] px-3 py-1.5 text-xs font-medium text-[color:var(--status-indexed-text)]">
                  <ShieldCheck aria-hidden="true" size={13} />
                  Settings saved
                </span>
              )}
            </div>
          </div>
        </header>

        <div className="grid gap-8 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-10">
          <aside className="lg:sticky lg:top-[calc(var(--nav-height)+2rem)] lg:self-start">
            <nav
              aria-label="Settings sections"
              className="rounded-2xl border border-[color:var(--frost)] bg-[color:var(--surface-soft)] p-2"
            >
              <div className="flex gap-1 overflow-x-auto lg:block lg:space-y-1">
                {SECTIONS.map(({ href, label, icon: Icon }) => (
                  <a
                    key={href}
                    href={href}
                    className="flex min-w-max items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-[color:var(--silver)] outline-none transition hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--near-white)] focus-visible:ring-2 focus-visible:ring-[color:var(--blue)] lg:min-w-0"
                  >
                    <Icon aria-hidden="true" size={16} />
                    {label}
                  </a>
                ))}
              </div>
            </nav>
            <div
              className="group relative mt-4 hidden rounded-2xl border border-[color:var(--frost)] bg-[color:var(--void)]/55 p-4 text-xs leading-5 text-[color:var(--muted)] lg:block"
              title="Dashboard controls only switch capabilities already included in your selected modular build. They never install packages or send your library elsewhere."
            >
              <Settings2
                aria-hidden="true"
                className="mb-2 text-[color:var(--silver)]"
                size={17}
              />
              About runtime controls
            </div>
          </aside>

          <div className="min-w-0">
            {settingsQuery.isPending ? (
              <div
                className="space-y-5"
                role="status"
                aria-label="Loading settings"
                aria-busy="true"
              >
                {[0, 1, 2].map((item) => (
                  <div
                    key={item}
                    className="h-48 animate-pulse rounded-2xl border border-[color:var(--frost)] bg-[color:var(--surface-soft)]"
                  />
                ))}
              </div>
            ) : settingsQuery.isError ? (
              <section
                role="alert"
                className="rounded-2xl border border-[color:var(--red)]/30 bg-[color:var(--red-soft)] p-6"
              >
                <h2 className="text-base font-semibold">
                  Settings could not load
                </h2>
                <p className="mt-2 text-sm leading-6 text-[color:var(--silver)]">
                  Your existing configuration is unchanged. Check the local API
                  and try again.
                </p>
                <button
                  type="button"
                  onClick={() => settingsQuery.refetch()}
                  className="mt-5 inline-flex h-10 items-center gap-2 rounded-xl bg-[color:var(--near-white)] px-4 text-sm font-semibold text-[color:var(--void)] outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--blue)]"
                >
                  <RefreshCw aria-hidden="true" size={15} />
                  Retry
                </button>
              </section>
            ) : (
              <div className="space-y-5 sm:space-y-6">
                <AppearanceSettings />
                <HardwareAccelSettings
                  value={settingsQuery.data.accel_mode}
                  pending={save.isPending}
                  onChange={(mode) => save.mutate({ accel_mode: mode })}
                />
                <AiRuntimeSettings
                  enabled={settingsQuery.data.ai_enabled}
                  pending={save.isPending}
                  onChange={(enabled) => save.mutate({ ai_enabled: enabled })}
                  mode={settingsQuery.data.ml_mode}
                  supportedModes={settingsQuery.data.supported_ml_modes}
                  onModeChange={(ml_mode) => save.mutate({ ml_mode })}
                />
                <div id="privacy" className="space-y-5 sm:space-y-6">
                  <MapPrivacySettings
                    enabled={settingsQuery.data.map_enabled}
                    pending={save.isPending}
                    onChange={(enabled) =>
                      save.mutate({ map_enabled: enabled })
                    }
                  />
                </div>
                <TrashRetentionSettings
                  value={settingsQuery.data.trash_retention_days}
                  pending={save.isPending}
                  onChange={(trash_retention_days) =>
                    save.mutate({ trash_retention_days })
                  }
                />
              </div>
            )}

            {save.isError && (
              <p
                className="mt-5 rounded-xl border border-[color:var(--red)]/30 bg-[color:var(--red-soft)] px-4 py-3 text-sm"
                data-testid="settings-save-error"
                role="alert"
              >
                Couldn&apos;t save settings. Your previous value remains active.
              </p>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
